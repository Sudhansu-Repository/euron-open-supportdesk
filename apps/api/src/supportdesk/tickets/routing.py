"""Who gets a conversation that people now own.

Least-loaded first among the team's agents who are online, enabled and under capacity;
ties go round-robin after the last agent this team assigned. The team row is locked for
the decision, so two conversations escalated at the same moment do not both land on the
same "least loaded" agent. With nobody available the conversation stays in the team's
unassigned queue, where the inbox shows it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.core.db import OrgScope
from supportdesk.core.errors import AppError
from supportdesk.org.models import Team, TeamMember
from supportdesk.tickets.models import Ticket
from supportdesk.users.models import User


def choose(
    candidates: list[tuple[uuid.UUID, int, int]], last_assigned: uuid.UUID | None
) -> uuid.UUID | None:
    """Pick from (user id, open conversations, capacity), ordered by user id."""
    available = [(uid, load) for uid, load, cap in candidates if load < cap]
    if not available:
        return None
    lowest = min(load for _, load in available)
    tied = sorted(uid for uid, load in available if load == lowest)
    if last_assigned is not None:
        after = [uid for uid in tied if uid > last_assigned]
        if after:
            return after[0]
    return tied[0]


async def assign(session: AsyncSession, ticket: Ticket) -> uuid.UUID | None:
    if ticket.assignee_id is not None:
        return ticket.assignee_id
    team: Team | None = None
    if ticket.team_id is not None:
        team = await session.scalar(select(Team).where(Team.id == ticket.team_id).with_for_update())
    users = select(User.id, User.capacity).where(
        User.org_id == ticket.org_id, User.disabled.is_(False), User.availability == "online"
    )
    if team is not None:
        users = users.where(
            User.id.in_(select(TeamMember.user_id).where(TeamMember.team_id == team.id))
        )
    rows = (await session.execute(users)).all()
    if not rows:
        return None
    loads = dict(
        (
            await session.execute(
                select(Ticket.assignee_id, func.count())
                .where(
                    Ticket.org_id == ticket.org_id,
                    Ticket.assignee_id.in_([r[0] for r in rows]),
                    Ticket.status.in_(("open", "pending")),
                )
                .group_by(Ticket.assignee_id)
            )
        )
        .tuples()
        .all()
    )
    chosen = choose(
        [(uid, int(loads.get(uid, 0)), cap) for uid, cap in rows],
        team.last_assigned_user_id if team is not None else None,
    )
    if chosen is None:
        return None
    ticket.assignee_id = chosen
    if team is not None:
        team.last_assigned_user_id = chosen
    from supportdesk.tickets.service import event

    event(session, ticket, "assigned", "system", None, assignee_id=str(chosen), routed=True)
    return chosen


async def check_assignee(session: AsyncSession, scope: OrgScope, user_id: uuid.UUID | None) -> None:
    if user_id is None:
        return
    found = await session.scalar(
        select(User.id).where(
            User.id == user_id, User.org_id == scope.org_id, User.disabled.is_(False)
        )
    )
    if found is None:
        raise AppError("Assign to an active agent of this organisation", code="unknown_assignee")


async def check_team(session: AsyncSession, scope: OrgScope, team_id: uuid.UUID | None) -> None:
    if team_id is None:
        return
    found = await session.scalar(
        select(Team.id).where(Team.id == team_id, Team.org_id == scope.org_id)
    )
    if found is None:
        raise AppError("Unknown team", code="unknown_team")
