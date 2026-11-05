"""Who is calling: an agent (session cookie or bearer session token) or an integration
(an ``sdk_`` API key, for the REST API under ``/api/v1``).

Cookie-authenticated mutations must carry ``X-SupportDesk-CSRF: 1``. Browsers cannot add a
custom header to a cross-site request without a CORS preflight, which the allowlist
refuses, so this blocks CSRF without server-side token state.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.audit.service import Actor
from supportdesk.auth.models import RevokedSession
from supportdesk.core.deps import ContainerDep, SessionDep, client_ip
from supportdesk.core.errors import AuthenticationError, PermissionDeniedError
from supportdesk.core.security import (
    SessionClaims,
    constant_time_equals,
    decode_session,
    hash_key_secret,
    parse_api_key,
)
from supportdesk.users.models import User

SESSION_COOKIE = "sd_session"
CSRF_HEADER = "x-supportdesk-csrf"
ROLE_RANK = {"agent": 0, "admin": 1, "owner": 2}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SEEN_EVERY = timedelta(minutes=1)


async def is_revoked(session: AsyncSession, claims: SessionClaims) -> bool:
    """A signed-out session stays refused until it would have expired anyway (a primary
    key lookup in Postgres: durable, and never evicted like a cache entry)."""
    if not claims.jti:
        return False
    return await session.get(RevokedSession, claims.jti) is not None


async def revoke(session: AsyncSession, claims: SessionClaims) -> None:
    if not claims.jti or claims.expires_at is None:
        return
    now = datetime.now(UTC)
    await session.execute(delete(RevokedSession).where(RevokedSession.expires_at < now))
    if claims.expires_at > now:
        await session.execute(
            insert(RevokedSession)
            .values(jti=claims.jti, expires_at=claims.expires_at)
            .on_conflict_do_nothing()
        )


def session_token(request: Request) -> tuple[str | None, bool]:
    """The session token and whether it came from the cookie."""
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else None
    if token:
        return token, False
    cookie = request.cookies.get(SESSION_COOKIE)
    return cookie, cookie is not None


async def current_user(request: Request, container: ContainerDep, session: SessionDep) -> User:
    token, via_cookie = session_token(request)
    if not token or token.startswith("sdk_"):
        raise AuthenticationError("Sign in to continue", code="not_signed_in")
    claims = decode_session(token, container.settings.session_secret)
    if claims is None or await is_revoked(session, claims):
        raise AuthenticationError("Your session expired. Sign in again", code="session_expired")
    user = await session.get(User, claims.user_id)
    if user is None or user.disabled or user.session_version != claims.session_version:
        raise AuthenticationError("Your session expired. Sign in again", code="session_expired")
    if (
        via_cookie
        and request.method not in _SAFE_METHODS
        and request.headers.get(CSRF_HEADER) != "1"
    ):
        raise PermissionDeniedError("Missing CSRF header", code="csrf_required")
    now = datetime.now(UTC)
    if user.last_seen_at is None or now - user.last_seen_at > SEEN_EVERY:
        await session.execute(update(User).where(User.id == user.id).values(last_seen_at=now))
        await session.commit()
    request.state.actor = Actor(user.org_id, user.id, user.email, user.role, client_ip(request))
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_role(role: str) -> Callable[..., Coroutine[Any, Any, Actor]]:
    async def dependency(request: Request, user: CurrentUser) -> Actor:
        if ROLE_RANK.get(user.role, -1) < ROLE_RANK[role]:
            raise PermissionDeniedError(
                f"This action needs the {role} role", code="insufficient_role"
            )
        actor: Actor = request.state.actor
        return actor

    return dependency


Agent = Annotated[Actor, Depends(require_role("agent"))]
Admin = Annotated[Actor, Depends(require_role("admin"))]
Owner = Annotated[Actor, Depends(require_role("owner"))]


async def _api_key_actor(
    request: Request, container: ContainerDep, session: SessionDep, raw: str
) -> Actor:
    from supportdesk.integrations.models import ApiKey

    parsed = parse_api_key(raw)
    if parsed is None:
        raise AuthenticationError("The API key is malformed", code="invalid_api_key")
    prefix, secret = parsed
    key = await session.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    expected = hash_key_secret(secret, container.settings.token_pepper)
    if (
        key is None
        or key.revoked_at is not None
        or not constant_time_equals(key.secret_hash, expected)
    ):
        raise AuthenticationError("The API key is invalid or revoked", code="invalid_api_key")
    now = datetime.now(UTC)
    if key.last_used_at is None or now - key.last_used_at > SEEN_EVERY:
        key.last_used_at = now
        await session.commit()
    actor = Actor(key.org_id, None, f"api-key:{key.name}", "api", client_ip(request))
    request.state.actor = actor
    request.state.api_scope = key.scope
    return actor


def integration(scope: str) -> Callable[..., Coroutine[Any, Any, Actor]]:
    """An API key with at least ``scope`` (read < write), or a signed-in agent."""

    async def dependency(request: Request, container: ContainerDep, session: SessionDep) -> Actor:
        token, _ = session_token(request)
        if token and token.startswith("sdk_"):
            actor = await _api_key_actor(request, container, session, token)
            if scope == "write" and request.state.api_scope != "write":
                raise PermissionDeniedError("This API key is read-only", code="insufficient_scope")
            return actor
        await current_user(request, container, session)
        actor_: Actor = request.state.actor
        return actor_

    return dependency


ApiRead = Annotated[Actor, Depends(integration("read"))]
ApiWrite = Annotated[Actor, Depends(integration("write"))]
