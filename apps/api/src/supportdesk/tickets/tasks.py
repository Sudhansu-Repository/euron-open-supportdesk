"""Periodic upkeep of conversations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from supportdesk.core.container import Container
from supportdesk.core.events import publish_pending
from supportdesk.core.jobs import prune
from supportdesk.core.tasks import periodic
from supportdesk.integrations.service import dispatch
from supportdesk.tickets import service
from supportdesk.tickets.models import Message, Ticket

# An AI answer the customer did not follow up on for this long counts as a resolution.
AUTO_RESOLVE_AFTER = timedelta(hours=24)
BATCH = 200


@periodic("sla.scan", every_s=60)
async def sla_scan(container: Container) -> int:
    """Flag conversations whose earliest SLA target has passed."""
    now = datetime.now(UTC)
    async with container.db.sessionmaker() as session:
        rows = (
            await session.execute(
                update(Ticket)
                .where(
                    Ticket.status.in_(("open", "pending")),
                    Ticket.sla_breached.is_(False),
                    Ticket.sla_next_due_at.is_not(None),
                    Ticket.sla_next_due_at < now,
                )
                .values(sla_breached=True)
                .returning(Ticket.id, Ticket.org_id)
            )
        ).all()
        for ticket_id, org_id in rows:
            session.add(_event(ticket_id, org_id))
            from supportdesk.core.events import emit
            from supportdesk.core.hub import org_topic

            emit(
                session, org_topic(org_id), {"type": "ticket.updated", "ticket_id": str(ticket_id)}
            )
        await session.commit()
        await publish_pending(container, session)
        return len(rows)


def _event(ticket_id: object, org_id: object) -> object:
    from supportdesk.tickets.models import TicketEvent

    return TicketEvent(
        org_id=org_id, ticket_id=ticket_id, type="sla_breached", actor_type="system", data={}
    )


@periodic("tickets.auto_resolve", every_s=300)
async def auto_resolve(container: Container) -> int:
    """AI answered and the customer went quiet: resolved by AI."""
    cutoff = datetime.now(UTC) - AUTO_RESOLVE_AFTER
    async with container.db.sessionmaker() as session:
        tickets = (
            await session.scalars(
                select(Ticket)
                .where(
                    Ticket.handled_by == "ai",
                    Ticket.status == "pending",
                    Ticket.ai_answered_at < cutoff,
                )
                .limit(BATCH)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for ticket in tickets:
            # A conversation where the AI only exchanged greetings resolved nothing: it is
            # closed without counting as an AI resolution.
            answered = await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.ticket_id == ticket.id,
                    Message.author_type == "ai",
                    Message.status == "sent",
                    Message.ai_meta["method"].astext != "smalltalk",
                )
            )
            ticket.status = "resolved" if answered else "closed"
            ticket.resolved_at = datetime.now(UTC)
            ticket.closed_at = None if answered else ticket.resolved_at
            ticket.ai_resolved = bool(answered) and ticket.human_replied_at is None
            service.event(
                session,
                ticket,
                "status",
                "system",
                None,
                before="pending",
                after=ticket.status,
                auto=True,
                ai_resolved=ticket.ai_resolved,
            )
            await dispatch(
                session,
                ticket.org_id,
                "ticket.resolved",
                {"ticket": service.ticket_payload(ticket)},
            )
            service.announce(session, ticket)
        await session.commit()
        await publish_pending(container, session)
        return len(tickets)


@periodic("jobs.prune", every_s=3600)
async def prune_jobs(container: Container) -> int:
    """Retention: finished jobs after two days, retired answer cache entries."""
    from supportdesk.ai import cache

    async with container.db.sessionmaker() as session:
        return await prune(session, timedelta(days=2)) + await cache.prune(session)
