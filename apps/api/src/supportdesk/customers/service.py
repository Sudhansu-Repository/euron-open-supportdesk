"""Customers: found or created by email or external id, edited by agents, merged."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.audit.service import Actor, audit
from supportdesk.core.db import OrgScope
from supportdesk.core.errors import AppError, NotFoundError
from supportdesk.customers.models import Customer
from supportdesk.tickets.models import Ticket


def visitor_name() -> str:
    return f"Visitor {secrets.randbelow(9000) + 1000}"


async def get_customer(session: AsyncSession, scope: OrgScope, customer_id: uuid.UUID) -> Customer:
    customer = await session.get(Customer, customer_id)
    if customer is None or customer.org_id != scope.org_id:
        raise NotFoundError("Customer not found", code="customer_not_found")
    while customer.merged_into_id is not None:
        nxt = await session.get(Customer, customer.merged_into_id)
        if nxt is None:
            break
        customer = nxt
    return customer


async def get_token_customer(
    session: AsyncSession, scope: OrgScope, customer_id: uuid.UUID
) -> Customer:
    """The customer a widget or portal token names. Merges are NOT followed: a visitor
    token for a record an agent merged into someone else's must not open that person's
    conversations (the visitor starts over instead)."""
    from supportdesk.core.errors import AuthenticationError

    customer = await session.get(Customer, customer_id)
    if customer is None or customer.org_id != scope.org_id or customer.merged_into_id is not None:
        raise AuthenticationError("Your session expired. Reload the page", code="visitor_expired")
    return customer


def contact_address(customer: Customer) -> str | None:
    """Where replies can be emailed: the customer's email, or an address they typed into
    the widget (unverified: used for sending, never to match identity)."""
    if customer.email:
        return customer.email
    value = (customer.attributes or {}).get("contact_email")
    return value if isinstance(value, str) and "@" in value else None


async def _find(
    session: AsyncSession, org_id: uuid.UUID, email: str | None, external_id: str | None
) -> Customer | None:
    customer: Customer | None = None
    if external_id:
        customer = await session.scalar(
            select(Customer).where(
                Customer.org_id == org_id,
                Customer.external_id == external_id,
                Customer.merged_into_id.is_(None),
            )
        )
    if customer is None and email:
        customer = await session.scalar(
            select(Customer).where(
                Customer.org_id == org_id,
                func.lower(Customer.email) == email,
                Customer.merged_into_id.is_(None),
            )
        )
    return customer


async def find_or_create(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    email: str | None = None,
    name: str | None = None,
    external_id: str | None = None,
    attributes: dict[str, Any] | None = None,
    verified_id_only: bool = False,
) -> Customer:
    """The live customer with this external id or email (case-insensitive), or a new one.
    Details provided now fill in what was missing; they never overwrite what agents set.

    ``verified_id_only``: the caller proved only the external id (a widget identity
    signature covers the id, not the email), so the email must never pick an existing
    customer: matching on it would hand a signed-in user someone else's record."""
    email = email.strip().lower() if email else None
    customer = await _find(session, org_id, None if verified_id_only else email, external_id)
    if verified_id_only and customer is None and email:
        # A new verified customer whose email already belongs to someone else keeps the
        # email out of the identity fields (it stays an unverified contact).
        taken = await _find(session, org_id, email, None)
        if taken is not None:
            attributes = {**(attributes or {}), "contact_email": email}
            email = None
    if customer is None:
        customer = Customer(
            org_id=org_id,
            email=email,
            external_id=external_id,
            name=(name or (email.split("@")[0] if email else None) or visitor_name())[:200],
            attributes=attributes or {},
        )
        try:
            # A savepoint: two requests creating the same customer at once (an email
            # thread and the widget, or parallel API calls) must not fail one of them.
            async with session.begin_nested():
                session.add(customer)
                await session.flush()
        except IntegrityError:
            existing = await _find(session, org_id, email, external_id)
            if existing is None:
                raise
            customer = existing
    else:
        if email and not customer.email:
            customer.email = email
        if external_id and not customer.external_id:
            customer.external_id = external_id
        if name and (customer.name.startswith("Visitor ") or not customer.name):
            customer.name = name[:200]
        if attributes:
            customer.attributes = {**customer.attributes, **attributes}
    customer.last_seen_at = datetime.now(UTC)
    return customer


async def update_customer(
    session: AsyncSession,
    actor: Actor,
    customer_id: uuid.UUID,
    *,
    name: str | None,
    email: str | None,
    vip: bool | None,
    attributes: dict[str, Any] | None,
) -> Customer:
    customer = await get_customer(session, actor.scope, customer_id)
    if email is not None:
        email = email.strip().lower() or None
        if email and email != customer.email:
            clash = await session.scalar(
                select(Customer.id).where(
                    Customer.org_id == actor.org_id,
                    func.lower(Customer.email) == email,
                    Customer.id != customer.id,
                    Customer.merged_into_id.is_(None),
                )
            )
            if clash is not None:
                raise AppError(
                    "Another customer has this email. Merge them instead",
                    code="email_taken",
                    details={"customer_id": str(clash)},
                )
        customer.email = email
    if name is not None and name.strip():
        customer.name = name.strip()[:200]
    if vip is not None:
        customer.vip = vip
    if attributes is not None:
        customer.attributes = attributes
    audit(session, actor, "customer.updated", "customer", customer.id)
    await session.commit()
    return customer


async def merge(
    session: AsyncSession, actor: Actor, keep_id: uuid.UUID, drop_id: uuid.UUID
) -> Customer:
    if keep_id == drop_id:
        raise AppError("Choose two different customers", code="same_customer")
    keep = await get_customer(session, actor.scope, keep_id)
    drop = await get_customer(session, actor.scope, drop_id)
    await session.execute(
        update(Ticket).where(Ticket.customer_id == drop.id).values(customer_id=keep.id)
    )
    email, external_id = drop.email, drop.external_id
    # Retire the dropped record first: the unique indexes cover live customers only.
    drop.merged_into_id = keep.id
    drop.email = None
    drop.external_id = None
    await session.flush()
    keep.email = keep.email or email
    keep.external_id = keep.external_id or external_id
    keep.vip = keep.vip or drop.vip
    keep.attributes = {**drop.attributes, **keep.attributes}
    audit(session, actor, "customer.merged", "customer", keep.id, merged=str(drop.id))
    await session.commit()
    return keep
