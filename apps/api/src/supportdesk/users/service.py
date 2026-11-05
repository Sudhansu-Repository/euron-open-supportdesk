"""Agents: listing, roles, access and capacity. Owners keep the organisation reachable:
the last owner cannot be demoted or disabled, and only owners manage owners."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.audit.service import Actor, audit
from supportdesk.core.db import OrgScope
from supportdesk.core.errors import AppError, NotFoundError, PermissionDeniedError
from supportdesk.users.models import Invitation, User
from supportdesk.users.schemas import MePatch, UserPatch


async def list_users(session: AsyncSession, scope: OrgScope) -> list[User]:
    rows = await session.scalars(
        select(User).where(User.org_id == scope.org_id).order_by(User.name)
    )
    return list(rows.all())


async def _owners(session: AsyncSession, org_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.org_id == org_id, User.role == "owner", User.disabled.is_(False))
        )
        or 0
    )


async def update_user(
    session: AsyncSession, actor: Actor, user_id: uuid.UUID, data: UserPatch
) -> User:
    user = await session.get(User, user_id, with_for_update=True)
    if user is None or user.org_id != actor.org_id:
        raise NotFoundError("Agent not found")
    touches_owner = user.role == "owner" or data.role == "owner"
    if touches_owner and actor.role != "owner":
        raise PermissionDeniedError("Only owners can change owners", code="owner_only")
    losing_owner = user.role == "owner" and ((data.role and data.role != "owner") or data.disabled)
    if losing_owner and await _owners(session, actor.org_id) <= 1:
        raise AppError("The organisation needs at least one active owner", code="last_owner")
    if data.name is not None:
        user.name = data.name
    if data.role is not None:
        user.role = data.role
    if data.capacity is not None:
        user.capacity = data.capacity
    if data.disabled is not None:
        if user.id == actor.id and data.disabled:
            raise AppError("You cannot disable your own account", code="self_disable")
        user.disabled = data.disabled
        if data.disabled:
            user.session_version += 1
            user.availability = "offline"
    if data.role is not None:
        user.session_version += 1  # a new role takes effect on the next sign-in
    audit(session, actor, "user.updated", "user", user.id, **data.model_dump(exclude_unset=True))
    await session.commit()
    return user


async def update_me(session: AsyncSession, user: User, data: MePatch) -> User:
    if data.name is not None:
        user.name = data.name
    if data.availability is not None:
        user.availability = data.availability
    await session.commit()
    return user


async def list_invitations(session: AsyncSession, scope: OrgScope) -> list[Invitation]:
    rows = await session.scalars(
        select(Invitation)
        .where(Invitation.org_id == scope.org_id, Invitation.accepted_at.is_(None))
        .order_by(Invitation.created_at.desc())
    )
    return list(rows.all())


async def revoke_invitation(session: AsyncSession, actor: Actor, invitation_id: uuid.UUID) -> None:
    invitation = await session.get(Invitation, invitation_id)
    if invitation is None or invitation.org_id != actor.org_id:
        raise NotFoundError("Invitation not found")
    await session.delete(invitation)
    audit(session, actor, "user.invitation_revoked", "invitation", invitation_id)
    await session.commit()
