from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import Response

from supportdesk.auth import service as auth_service
from supportdesk.auth.dependencies import Admin, Agent, CurrentUser
from supportdesk.auth.schemas import UserOut
from supportdesk.core.deps import ContainerDep, SessionDep
from supportdesk.core.events import commit, emit
from supportdesk.core.hub import org_topic
from supportdesk.users import service
from supportdesk.users.models import Invitation, User
from supportdesk.users.schemas import InvitationCreated, InvitationOut, InviteIn, MePatch, UserPatch

router = APIRouter(prefix="/api/v1", tags=["agents"])


@router.get("/users", response_model=list[UserOut], summary="Agents of this organisation")
async def list_users(actor: Agent, session: SessionDep) -> list[User]:
    return await service.list_users(session, actor.scope)


@router.patch(
    "/users/{user_id}", response_model=UserOut, summary="Change an agent's role, access or capacity"
)
async def update_user(
    user_id: uuid.UUID, body: UserPatch, actor: Admin, session: SessionDep
) -> User:
    return await service.update_user(session, actor, user_id, body)


@router.patch("/me", response_model=UserOut, summary="Change your name or availability")
async def update_me(
    body: MePatch, user: CurrentUser, session: SessionDep, container: ContainerDep
) -> User:
    updated = await service.update_me(session, user, body)
    emit(session, org_topic(user.org_id), {"type": "presence", "user_id": str(user.id)})
    await commit(container, session)
    return updated


@router.get("/invitations", response_model=list[InvitationOut], summary="Pending invitations")
async def list_invitations(actor: Admin, session: SessionDep) -> list[Invitation]:
    return await service.list_invitations(session, actor.scope)


@router.post(
    "/invitations",
    response_model=InvitationCreated,
    status_code=201,
    summary="Invite an agent by email (the link is also returned, once)",
)
async def invite(
    body: InviteIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> InvitationCreated:
    invitation, link = await auth_service.invite(
        session, container.settings, actor, body.email, body.role
    )
    return InvitationCreated.model_validate(
        {**InvitationOut.model_validate(invitation).model_dump(), "invite_url": link}
    )


@router.delete("/invitations/{invitation_id}", status_code=204, summary="Withdraw an invitation")
async def revoke(invitation_id: uuid.UUID, actor: Admin, session: SessionDep) -> Response:
    await service.revoke_invitation(session, actor, invitation_id)
    return Response(status_code=204)
