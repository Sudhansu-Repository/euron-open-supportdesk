"""Inboxes and the website widget.

The widget's public key only says which inbox a visitor writes to. Three things protect
it: the browser's Origin must be in the inbox's allowed origins (checked on every call,
not only in CORS); each visitor holds a signed token bound to their customer record and
inbox; and messages are rate limited per visitor and per address. When identity
verification is on, a visitor claiming to be a known customer must present
``HMAC-SHA256(identity secret, external_id)`` computed by the company's backend, so nobody
can read another customer's conversations by typing their id.
"""

from __future__ import annotations

import hmac
import secrets
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.audit.service import Actor, audit
from supportdesk.channels.models import CHANNELS, Inbox
from supportdesk.core.container import Container
from supportdesk.core.db import OrgScope
from supportdesk.core.errors import (
    AppError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
)
from supportdesk.core.security import decode_token, hash_key_secret, hmac_hex, issue_token

WIDGET_AUDIENCE = "supportdesk-widget"
VISITOR_TTL = timedelta(days=30)
IDENTITY_CONTEXT = "inbox:{inbox_id}:identity"

DEFAULT_APPEARANCE: dict[str, Any] = {
    "title": "Support",
    "greeting": (
        "Hi! Ask us anything. Our assistant answers right away, and a teammate is a click away."
    ),
    "color": "#4f46e5",
    "position": "right",
    "suggestions": [],
    "launcher_label": "Help",
}


def new_public_key() -> str:
    return "pk_" + secrets.token_urlsafe(18)


async def create_default_inboxes(session: AsyncSession, org_id: uuid.UUID) -> None:
    session.add_all(
        [
            Inbox(
                org_id=org_id,
                name="Website chat",
                channel="widget",
                public_key=new_public_key(),
                appearance=dict(DEFAULT_APPEARANCE),
                allowed_origins=[],
            ),
            Inbox(org_id=org_id, name="Email", channel="email"),
            Inbox(org_id=org_id, name="Customer portal", channel="portal"),
            Inbox(org_id=org_id, name="API", channel="api", ai_enabled=False),
        ]
    )


async def inbox_for_channel(session: AsyncSession, org_id: uuid.UUID, channel: str) -> Inbox:
    inbox = await session.scalar(
        select(Inbox)
        .where(Inbox.org_id == org_id, Inbox.channel == channel, Inbox.active.is_(True))
        .order_by(Inbox.created_at)
        .limit(1)
    )
    if inbox is None:
        raise NotFoundError(f"No active {channel} inbox", code="inbox_not_found")
    return inbox


async def get_inbox(session: AsyncSession, scope: OrgScope, inbox_id: uuid.UUID) -> Inbox:
    inbox = await session.get(Inbox, inbox_id)
    if inbox is None or inbox.org_id != scope.org_id:
        raise NotFoundError("Inbox not found")
    return inbox


def normalize_origin(origin: str) -> str:
    parts = urlsplit(origin.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"{origin!r} is not an origin like https://www.example.com")
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname.lower()}{port}"


async def create_inbox(session: AsyncSession, actor: Actor, name: str, channel: str) -> Inbox:
    if channel not in CHANNELS:
        raise AppError(f"Channel is one of {', '.join(CHANNELS)}", code="invalid_channel")
    inbox = Inbox(
        org_id=actor.org_id,
        name=name,
        channel=channel,
        public_key=new_public_key() if channel == "widget" else None,
        appearance=dict(DEFAULT_APPEARANCE) if channel == "widget" else {},
    )
    session.add(inbox)
    await session.flush()
    audit(session, actor, "inbox.created", "inbox", inbox.id, channel=channel)
    await session.commit()
    return inbox


async def update_inbox(
    container: Container,
    session: AsyncSession,
    actor: Actor,
    inbox_id: uuid.UUID,
    data: dict[str, Any],
) -> tuple[Inbox, str | None]:
    """Apply an edit. Returns the inbox and, when one was just generated, the identity
    secret or inbound email token (shown once)."""
    inbox = await get_inbox(session, actor.scope, inbox_id)
    revealed: str | None = None
    if data.get("name"):
        inbox.name = data["name"]
    if "allowed_origins" in data and data["allowed_origins"] is not None:
        try:
            inbox.allowed_origins = sorted(
                {normalize_origin(o) for o in data["allowed_origins"] if o.strip()}
            )
        except ValueError as exc:
            raise AppError(str(exc), code="invalid_origin") from exc
    if data.get("appearance") is not None:
        inbox.appearance = {**DEFAULT_APPEARANCE, **data["appearance"]}
    for flag in ("ai_enabled", "active", "identity_required"):
        if data.get(flag) is not None:
            setattr(inbox, flag, bool(data[flag]))
    if "team_id" in data:
        from supportdesk.tickets.routing import check_team

        await check_team(session, actor.scope, data["team_id"])
        inbox.team_id = data["team_id"]
    if data.get("email_address") is not None:
        inbox.email_address = data["email_address"].strip().lower() or None
    if data.get("rotate_identity_secret"):
        secret = "ids_" + secrets.token_urlsafe(24)
        inbox.identity_secret_sealed = await container.sealer.seal(
            secret, IDENTITY_CONTEXT.format(inbox_id=inbox.id)
        )
        revealed = secret
    if data.get("rotate_inbound_token"):
        token = "inb_" + secrets.token_urlsafe(24)
        inbox.inbound_secret_hash = hash_key_secret(token, container.settings.token_pepper)
        revealed = token
    if inbox.identity_required and inbox.identity_secret_sealed is None:
        raise AppError(
            "Generate an identity secret before requiring verification", code="no_identity_secret"
        )
    audit(session, actor, "inbox.updated", "inbox", inbox.id)
    await session.commit()
    return inbox, revealed


async def widget_inbox(session: AsyncSession, public_key: str) -> Inbox:
    inbox = await session.scalar(
        select(Inbox).where(
            Inbox.public_key == public_key, Inbox.channel == "widget", Inbox.active.is_(True)
        )
    )
    if inbox is None:
        raise NotFoundError("This chat widget is not active", code="widget_not_found")
    return inbox


def check_origin(inbox: Inbox, origin: str | None, app_origin: str | None = None) -> None:
    """Who may talk to a widget inbox.

    The widget is an iframe served from the app's own origin, so its calls carry the app
    origin; which sites may *embed* that iframe is enforced by the browser through the
    frame page's ``frame-ancestors`` policy (see ``frame_ancestors``). A site calling the
    API directly (its own chat UI) must be listed. An inbox with no allowed origins
    accepts any site, which is handy while trying it out.
    """
    if not inbox.allowed_origins:
        return
    if not origin:
        # Browsers send Origin on every cross-origin request and on every POST; a request
        # without one is a same-origin GET (the widget frame polling its own origin) or
        # not from a browser at all, where the header could be forged anyway.
        return
    try:
        normalized = normalize_origin(origin)
    except ValueError:
        normalized = ""
    if app_origin and normalized == normalize_origin(app_origin):
        return
    if normalized not in inbox.allowed_origins:
        raise PermissionDeniedError(
            "This website is not allowed to use this chat widget. Add it under Settings > Inboxes",
            code="origin_not_allowed",
        )


async def verify_identity(
    container: Container, inbox: Inbox, external_id: str | None, signature: str | None
) -> bool:
    """True when the visitor proved who they are. Raises when proof is required or wrong."""
    if not external_id:
        if inbox.identity_required:
            raise AuthenticationError(
                "This chat needs a signed-in customer", code="identity_required"
            )
        return False
    if inbox.identity_secret_sealed is None:
        if inbox.identity_required:
            raise AuthenticationError(
                "Identity verification is misconfigured", code="identity_required"
            )
        return False
    secret = await container.sealer.open(
        inbox.identity_secret_sealed, IDENTITY_CONTEXT.format(inbox_id=inbox.id)
    )
    expected = hmac_hex(secret, external_id)
    if not signature or not hmac.compare_digest(expected, signature.strip().lower()):
        raise AuthenticationError(
            "The customer's identity signature is wrong", code="identity_invalid"
        )
    return True


def visitor_token(container: Container, inbox: Inbox, customer_id: uuid.UUID) -> str:
    return issue_token(
        {"sub": str(customer_id), "inbox": str(inbox.id), "org": str(inbox.org_id)},
        container.settings.session_secret,
        WIDGET_AUDIENCE,
        VISITOR_TTL,
    )


def read_visitor(container: Container, token: str | None) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """(org id, inbox id, customer id) from a visitor token, or 401."""
    data = (
        decode_token(token or "", container.settings.session_secret, WIDGET_AUDIENCE)
        if token
        else None
    )
    if not data:
        raise AuthenticationError(
            "Your chat session expired. Reload the page", code="visitor_expired"
        )
    try:
        return (
            uuid.UUID(str(data["org"])),
            uuid.UUID(str(data["inbox"])),
            uuid.UUID(str(data["sub"])),
        )
    except (KeyError, ValueError) as exc:
        raise AuthenticationError(
            "Your chat session expired. Reload the page", code="visitor_expired"
        ) from exc


def frame_ancestors(inbox: Inbox) -> list[str]:
    """The sites allowed to embed the widget frame (CSP frame-ancestors)."""
    return list(inbox.allowed_origins) or ["*"]
