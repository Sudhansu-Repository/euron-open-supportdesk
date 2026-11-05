"""The customer portal: sign in by a one-time email link, then see and answer your tickets.

Asking for a link always answers the same way, whether or not the address is known, so the
form cannot be used to find out who is a customer. Links are single use, expire after 15
minutes and are stored only as peppered hashes. A redeemed link yields a portal token
(audience ``supportdesk-portal``) bound to the customer and organisation.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.core.container import Container
from supportdesk.core.errors import AuthenticationError, NotFoundError
from supportdesk.core.mail import send
from supportdesk.core.security import decode_token, hash_key_secret, issue_token
from supportdesk.customers.models import Customer, PortalToken
from supportdesk.org.models import Org

PORTAL_AUDIENCE = "supportdesk-portal"
LINK_TTL = timedelta(minutes=15)
SESSION_TTL = timedelta(days=7)


async def org_by_slug(session: AsyncSession, slug: str) -> Org:
    org = await session.scalar(select(Org).where(Org.slug == slug))
    if org is None:
        raise NotFoundError("This help center does not exist", code="org_not_found")
    return org


async def request_link(container: Container, session: AsyncSession, org: Org, email: str) -> None:
    email = email.strip().lower()
    customer = await session.scalar(
        select(Customer).where(
            Customer.org_id == org.id,
            func.lower(Customer.email) == email,
            Customer.merged_into_id.is_(None),
        )
    )
    # A first-time address gets a link too (the answer must not reveal who is a customer);
    # its customer record is created only when the link is redeemed.
    token = secrets.token_urlsafe(32)
    session.add(
        PortalToken(
            org_id=org.id,
            customer_id=customer.id if customer else None,
            email=email,
            token_hash=hash_key_secret(token, container.settings.token_pepper),
            expires_at=datetime.now(UTC) + LINK_TTL,
        )
    )
    await session.commit()
    link = f"{container.settings.public_url}/help/{org.slug}/signin?token={token}"
    await send(
        container.settings,
        email,
        f"Your {org.name} support sign-in link",
        f"Open this link to see your support conversations with {org.name}:\n\n{link}\n\n"
        "It works once and expires in 15 minutes. If you did not ask for it, ignore this email.",
        from_name=f"{org.name} Support",
    )


async def redeem(
    container: Container, session: AsyncSession, org: Org, token: str
) -> tuple[str, Customer]:
    token_hash = hash_key_secret(token, container.settings.token_pepper)
    now = datetime.now(UTC)
    row = await session.execute(
        update(PortalToken)
        .where(
            PortalToken.token_hash == token_hash,
            PortalToken.org_id == org.id,
            PortalToken.used_at.is_(None),
            PortalToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(PortalToken.customer_id, PortalToken.email)
    )
    found = row.first() if row is not None else None
    if found is None:
        raise AuthenticationError(
            "This sign-in link has expired or was already used. Ask for a new one",
            code="link_expired",
        )
    customer_id, email = found
    customer = await session.get(Customer, customer_id) if customer_id else None
    if customer is None:
        from supportdesk.customers.service import find_or_create

        customer = await find_or_create(session, org.id, email=email)
    await session.commit()
    jwt = issue_token(
        {"sub": str(customer.id), "org": str(org.id)},
        container.settings.session_secret,
        PORTAL_AUDIENCE,
        SESSION_TTL,
    )
    return jwt, customer


def read_portal(container: Container, token: str | None) -> tuple[uuid.UUID, uuid.UUID]:
    data = (
        decode_token(token or "", container.settings.session_secret, PORTAL_AUDIENCE)
        if token
        else None
    )
    if not data:
        raise AuthenticationError("Sign in again to see your tickets", code="portal_expired")
    try:
        return uuid.UUID(str(data["org"])), uuid.UUID(str(data["sub"]))
    except (KeyError, ValueError) as exc:
        raise AuthenticationError(
            "Sign in again to see your tickets", code="portal_expired"
        ) from exc
