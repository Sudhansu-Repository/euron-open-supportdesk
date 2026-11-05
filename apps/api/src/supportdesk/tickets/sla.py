"""Service levels: first response and resolution targets per priority, in calendar time.

The clocks run while people own a conversation (the AI answers in seconds; SLAs measure
the team). ``sla_next_due_at`` holds the earliest unmet target so the inbox can sort by
urgency with one index; the worker's scan flags breaches.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.tickets.models import SlaPolicy, Ticket

# A conversation is "at risk" in the last fifth of its window.
AT_RISK_SHARE = 0.2


async def policy_for(session: AsyncSession, ticket: Ticket) -> SlaPolicy | None:
    return await session.scalar(
        select(SlaPolicy).where(
            SlaPolicy.org_id == ticket.org_id,
            SlaPolicy.priority == ticket.priority,
            SlaPolicy.enabled.is_(True),
        )
    )


def refresh(ticket: Ticket) -> None:
    """Recompute the earliest unmet target."""
    dues = []
    if ticket.first_response_due_at and ticket.human_replied_at is None:
        dues.append(ticket.first_response_due_at)
    if ticket.resolution_due_at and ticket.resolved_at is None:
        dues.append(ticket.resolution_due_at)
    ticket.sla_next_due_at = min(dues) if dues and ticket.status in ("open", "pending") else None


async def start_clock(
    session: AsyncSession, ticket: Ticket, start: datetime, *, restart: bool = False
) -> None:
    policy = await policy_for(session, ticket)
    if policy is None:
        ticket.first_response_due_at = ticket.resolution_due_at = None
        refresh(ticket)
        return
    if restart or ticket.first_response_due_at is None:
        ticket.first_response_due_at = start + timedelta(minutes=policy.first_response_minutes)
        if restart:
            ticket.human_replied_at = None
            ticket.sla_breached = False  # a new clock: the old breach is in the history
    if restart or ticket.resolution_due_at is None:
        ticket.resolution_due_at = start + timedelta(minutes=policy.resolution_minutes)
    refresh(ticket)


async def reprioritise(session: AsyncSession, ticket: Ticket) -> None:
    """A new priority moves the targets, measured from when the clock started."""
    if ticket.handled_by != "human":
        return
    started = ticket.escalated_at or ticket.created_at or datetime.now(UTC)
    policy = await policy_for(session, ticket)
    if policy is None:
        return
    ticket.first_response_due_at = started + timedelta(minutes=policy.first_response_minutes)
    ticket.resolution_due_at = started + timedelta(minutes=policy.resolution_minutes)
    refresh(ticket)


def state(ticket: Ticket, now: datetime | None = None) -> str:
    """ok, at_risk, breached or none, for badges."""
    if ticket.sla_breached:
        return "breached"
    due = ticket.sla_next_due_at
    if due is None:
        return "none"
    now = now or datetime.now(UTC)
    if due <= now:
        return "breached"
    start = ticket.escalated_at or ticket.created_at
    if start is not None and (due - now) <= (due - start) * AT_RISK_SHARE:
        return "at_risk"
    return "ok"
