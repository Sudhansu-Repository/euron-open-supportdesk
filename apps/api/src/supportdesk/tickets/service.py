"""Conversation lifecycle: open, reply, hand over, assign, resolve, reopen.

Every change writes a ``TicketEvent`` (the conversation's history), emits live events for
agents and the customer, and dispatches webhooks, all in the caller's transaction. A
customer message and its ``ai.reply`` job are written together, so an accepted message
always gets its AI turn or a handoff (AC12).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.audit.service import Actor, audit
from supportdesk.channels.models import Inbox
from supportdesk.core import jobs
from supportdesk.core.db import OrgScope
from supportdesk.core.errors import AppError, NotFoundError
from supportdesk.core.events import emit
from supportdesk.core.hub import org_topic, ticket_topic
from supportdesk.customers.models import Customer
from supportdesk.integrations.service import dispatch
from supportdesk.org.models import Org
from supportdesk.tickets import routing, sla
from supportdesk.tickets.models import PRIORITIES, STATUSES, Message, Ticket, TicketEvent

AI_REPLY = "ai.reply"
MAIL_REPLY = "mail.reply"


def _now() -> datetime:
    return datetime.now(UTC)


async def next_number(session: AsyncSession, org_id: uuid.UUID) -> int:
    number = await session.scalar(
        update(Org)
        .where(Org.id == org_id)
        .values(ticket_seq=Org.ticket_seq + 1)
        .returning(Org.ticket_seq)
    )
    return int(number or 0)


def event(
    session: AsyncSession,
    ticket: Ticket,
    type_: str,
    actor_type: str,
    actor_id: uuid.UUID | None = None,
    **data: Any,
) -> None:
    session.add(
        TicketEvent(
            org_id=ticket.org_id,
            ticket_id=ticket.id,
            type=type_,
            actor_type=actor_type,
            actor_id=actor_id,
            data=data,
        )
    )


def announce(session: AsyncSession, ticket: Ticket, message: Message | None = None) -> None:
    """Tell agents (org topic) and the customer's open widget or portal (ticket topic)."""
    if message is not None:
        emit(
            session,
            org_topic(ticket.org_id),
            {"type": "message.created", "ticket_id": str(ticket.id)},
        )
        if message.kind == "reply" and message.status == "sent":
            emit(
                session,
                ticket_topic(ticket.id),
                {"type": "message.created", "message_id": str(message.id)},
            )
    emit(session, org_topic(ticket.org_id), {"type": "ticket.updated", "ticket_id": str(ticket.id)})
    emit(session, ticket_topic(ticket.id), {"type": "ticket.updated", "status": ticket.status})


def ticket_payload(ticket: Ticket) -> dict[str, Any]:
    return {
        "id": str(ticket.id),
        "number": ticket.number,
        "subject": ticket.subject,
        "status": ticket.status,
        "priority": ticket.priority,
        "category": ticket.category,
        "channel": ticket.channel,
        "handled_by": ticket.handled_by,
        "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
        "customer_id": str(ticket.customer_id),
    }


def message_payload(message: Message) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "ticket_id": str(message.ticket_id),
        "author_type": message.author_type,
        "kind": message.kind,
        "body": message.body,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


async def get_ticket(
    session: AsyncSession, scope: OrgScope, ticket_id: uuid.UUID, *, lock: bool = False
) -> Ticket:
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.org_id == scope.org_id)
    if lock:
        stmt = stmt.with_for_update()
    ticket = await session.scalar(stmt)
    if ticket is None:
        raise NotFoundError("Conversation not found", code="ticket_not_found")
    return ticket


def _subject(subject: str | None, body: str) -> str:
    if subject and subject.strip():
        return subject.strip()[:300]
    first = body.strip().splitlines()[0] if body.strip() else ""
    return (first[:117] + "...") if len(first) > 120 else (first or "New conversation")


async def open_ticket(
    session: AsyncSession,
    inbox: Inbox,
    customer: Customer,
    body: str,
    *,
    subject: str | None = None,
    email_message_id: str | None = None,
    priority: str | None = None,
    author: Actor | None = None,
    ai: bool | None = None,
) -> tuple[Ticket, Message]:
    """A new conversation with its first customer message. The AI takes it first when
    the inbox allows; otherwise it goes straight to people."""
    now = _now()
    ai_first = (inbox.ai_enabled if ai is None else ai) and (author is None or ai is True)
    ticket = Ticket(
        org_id=inbox.org_id,
        number=await next_number(session, inbox.org_id),
        inbox_id=inbox.id,
        channel=inbox.channel,
        customer_id=customer.id,
        subject=_subject(subject, body),
        status="open",
        priority=priority if priority in PRIORITIES else "normal",
        handled_by="ai" if ai_first else "human",
        team_id=inbox.team_id,
        reply_token=secrets.token_hex(12),
        last_message_at=now,
        last_customer_message_at=now,
    )
    session.add(ticket)
    await session.flush()
    message = Message(
        org_id=ticket.org_id,
        ticket_id=ticket.id,
        author_type="customer",
        author_id=customer.id,
        kind="reply",
        status="sent",
        body=body,
        email_message_id=email_message_id,
        sent_at=now,
    )
    session.add(message)
    await session.flush()
    event(session, ticket, "created", "customer", customer.id, channel=ticket.channel)
    if ai_first:
        await jobs.enqueue(
            session,
            AI_REPLY,
            {"message_id": str(message.id)},
            org_id=ticket.org_id,
            dedupe_key=f"ai:{message.id}",
            max_attempts=3,
        )
    else:
        await sla.start_clock(session, ticket, now)
        await routing.assign(session, ticket)
    await dispatch(session, ticket.org_id, "ticket.created", {"ticket": ticket_payload(ticket)})
    await dispatch(session, ticket.org_id, "message.created", {"message": message_payload(message)})
    announce(session, ticket, message)
    return ticket, message


async def add_customer_message(
    session: AsyncSession,
    ticket: Ticket,
    customer: Customer,
    body: str,
    *,
    email_message_id: str | None = None,
) -> Message:
    now = _now()
    message = Message(
        org_id=ticket.org_id,
        ticket_id=ticket.id,
        author_type="customer",
        author_id=customer.id,
        kind="reply",
        status="sent",
        body=body,
        email_message_id=email_message_id,
        sent_at=now,
    )
    session.add(message)
    await session.flush()
    if ticket.status in ("resolved", "closed"):
        ticket.reopened_count += 1
        ticket.resolved_at = None
        ticket.closed_at = None
        ticket.ai_resolved = False
        event(session, ticket, "reopened", "customer", customer.id)
        if ticket.handled_by == "human":
            await sla.start_clock(session, ticket, now, restart=True)
    ticket.status = "open"
    ticket.ai_answered_at = None
    ticket.last_message_at = now
    ticket.last_customer_message_at = now
    if ticket.handled_by == "ai":
        await jobs.enqueue(
            session,
            AI_REPLY,
            {"message_id": str(message.id)},
            org_id=ticket.org_id,
            dedupe_key=f"ai:{message.id}",
            max_attempts=3,
        )
    await dispatch(session, ticket.org_id, "message.created", {"message": message_payload(message)})
    announce(session, ticket, message)
    return message


async def agent_reply(
    session: AsyncSession,
    actor: Actor,
    ticket: Ticket,
    body: str,
    *,
    note: bool = False,
    status: str | None = None,
) -> Message:
    """A person writes to the customer (or an internal note). Replying takes the
    conversation from the AI: from then on people own it."""
    now = _now()
    message = Message(
        org_id=ticket.org_id,
        ticket_id=ticket.id,
        author_type="agent",
        author_id=actor.id,
        kind="note" if note else "reply",
        status="sent",
        body=body,
        sent_at=now,
    )
    session.add(message)
    await session.flush()
    if not note:
        if ticket.handled_by == "ai":
            ticket.handled_by = "human"
            event(session, ticket, "taken_over", "agent", actor.id)
        ticket.ai_resolved = False
        ticket.pending_approval = False
        ticket.first_response_at = ticket.first_response_at or now
        ticket.human_replied_at = ticket.human_replied_at or now
        ticket.last_message_at = now
        if ticket.assignee_id is None and actor.id is not None and actor.role != "api":
            ticket.assignee_id = actor.id
            event(session, ticket, "assigned", "agent", actor.id, assignee_id=str(actor.id))
        await _set_status(session, actor, ticket, status or "pending")
        sla.refresh(ticket)
        await email_customer(session, ticket, message)
        await dispatch(
            session, ticket.org_id, "message.created", {"message": message_payload(message)}
        )
    else:
        event(session, ticket, "note", "agent", actor.id)
    audit(session, actor, "ticket.note" if note else "ticket.replied", "ticket", ticket.id)
    announce(session, ticket, message)
    return message


async def email_customer(session: AsyncSession, ticket: Ticket, message: Message) -> None:
    """Send a reply by email too: always on the email channel, and on the widget and the
    portal when the customer left an address (they may have closed the page; their email
    reply threads back into this conversation)."""
    if ticket.channel != "email":
        from supportdesk.customers.service import contact_address

        customer = await session.get(Customer, ticket.customer_id)
        if customer is None or not contact_address(customer):
            return
    await jobs.enqueue(
        session,
        MAIL_REPLY,
        {"message_id": str(message.id)},
        org_id=ticket.org_id,
        dedupe_key=f"mail:{message.id}",
    )


async def _set_status(session: AsyncSession, actor: Actor, ticket: Ticket, status: str) -> None:
    if status not in STATUSES:
        raise AppError(f"Unknown status {status!r}", code="invalid_status")
    if status == ticket.status:
        return
    now = _now()
    previous = ticket.status
    ticket.status = status
    if status == "resolved":
        ticket.resolved_at = now
        ticket.pending_approval = False
    elif status == "closed":
        ticket.closed_at = now
        ticket.resolved_at = ticket.resolved_at or now
    elif previous in ("resolved", "closed"):
        ticket.reopened_count += 1
        ticket.resolved_at = None
        ticket.closed_at = None
        ticket.ai_resolved = False
    event(session, ticket, "status", actor.role, actor.id, before=previous, after=status)
    if status == "resolved":
        await dispatch(
            session, ticket.org_id, "ticket.resolved", {"ticket": ticket_payload(ticket)}
        )


async def update_ticket(
    session: AsyncSession,
    actor: Actor,
    ticket: Ticket,
    *,
    status: str | None = None,
    priority: str | None = None,
    category: str | bool | None = False,
    tags: list[str] | None = None,
    assignee_id: uuid.UUID | bool | None = False,
    team_id: uuid.UUID | bool | None = False,
    subject: str | None = None,
) -> Ticket:
    """Agent edits. ``category``, ``assignee_id`` and ``team_id`` use ``False`` for
    "unchanged" because ``None`` (or an empty category) means "clear"."""
    changed: list[str] = []
    if status is not None and status != ticket.status:
        await _set_status(session, actor, ticket, status)
        changed.append("status")
    if priority is not None and priority != ticket.priority:
        if priority not in PRIORITIES:
            raise AppError(f"Unknown priority {priority!r}", code="invalid_priority")
        event(
            session,
            ticket,
            "priority",
            actor.role,
            actor.id,
            before=ticket.priority,
            after=priority,
        )
        ticket.priority = priority
        await sla.reprioritise(session, ticket)
        changed.append("priority")
    if category is not False:
        category = (category or "").strip() or None  # type: ignore[union-attr]  # "" clears it
    if category is not False and category != ticket.category:
        event(
            session,
            ticket,
            "category",
            actor.role,
            actor.id,
            before=ticket.category,
            after=category,
        )
        ticket.category = category
        changed.append("category")
    if tags is not None:
        cleaned = sorted({t.strip().lower()[:40] for t in tags if t.strip()})[:20]
        if cleaned != sorted(ticket.tags or []):
            ticket.tags = cleaned
            changed.append("tags")
    if subject is not None and subject.strip() and subject != ticket.subject:
        ticket.subject = subject.strip()[:300]
        changed.append("subject")
    if team_id is not False:
        await routing.check_team(session, actor.scope, team_id)  # type: ignore[arg-type]
        ticket.team_id = team_id  # type: ignore[assignment]
        changed.append("team")
    if assignee_id is not False:
        await routing.check_assignee(session, actor.scope, assignee_id)  # type: ignore[arg-type]
        if assignee_id != ticket.assignee_id:
            ticket.assignee_id = assignee_id  # type: ignore[assignment]
            if assignee_id is not None and ticket.handled_by == "ai":
                ticket.handled_by = "human"
                await sla.start_clock(session, ticket, _now())
            event(
                session,
                ticket,
                "assigned",
                actor.role,
                actor.id,
                assignee_id=str(assignee_id) if assignee_id else None,
            )
            changed.append("assignee")
    if changed:
        audit(session, actor, "ticket.updated", "ticket", ticket.id, fields=changed)
        await dispatch(
            session,
            ticket.org_id,
            "ticket.updated",
            {"ticket": ticket_payload(ticket), "changed": changed},
        )
        announce(session, ticket)
    return ticket


async def escalate(
    session: AsyncSession,
    ticket: Ticket,
    reasons: list[str],
    *,
    summary: str | None = None,
    actor_type: str = "ai",
) -> None:
    """Hand the conversation to people: reasons recorded, SLA clock started, routed to an
    available agent. Idempotent: a conversation people already own is left alone except
    for new reasons."""
    now = _now()
    new_reasons = [r for r in reasons if r not in (ticket.escalation_reasons or [])]
    if ticket.handled_by == "human" and not new_reasons:
        return
    ticket.escalation_reasons = [*(ticket.escalation_reasons or []), *new_reasons]
    if summary:
        ticket.summary = summary
    if ticket.handled_by == "ai":
        ticket.handled_by = "human"
        ticket.escalated_at = now
        ticket.ai_answered_at = None
        if ticket.status in ("pending", "resolved", "closed"):
            ticket.status = "open"
        await sla.start_clock(session, ticket, now)
        await routing.assign(session, ticket)
    event(session, ticket, "escalated", actor_type, None, reasons=new_reasons or reasons)
    await dispatch(
        session,
        ticket.org_id,
        "ticket.escalated",
        {
            "ticket": ticket_payload(ticket),
            "reasons": ticket.escalation_reasons,
            "summary": ticket.summary,
        },
    )
    announce(session, ticket)


async def _locked_message(session: AsyncSession, message_id: uuid.UUID) -> Message:
    row = await session.scalar(
        select(Message)
        .where(Message.id == message_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise NotFoundError("Message not found")
    return row


async def approve(
    session: AsyncSession, actor: Actor, message: Message, body: str | None = None
) -> Message:
    """Send an AI answer that was held for approval (optionally edited first)."""
    ticket = await get_ticket(session, actor.scope, message.ticket_id, lock=True)
    # Re-read under a lock, after the ticket lock: two agents deciding at once must see
    # each other's decision, not a stale copy loaded before the lock.
    message = await _locked_message(session, message.id)
    if message.status not in ("pending", "draft") or message.author_type != "ai":
        raise AppError(
            "Only an AI answer waiting for approval or a draft can be sent", code="not_pending"
        )
    now = _now()
    if body is not None and body.strip() and body.strip() != message.body:
        message.ai_meta = {**message.ai_meta, "edited_by": str(actor.id)}
        message.body = body.strip()
    message.status = "sent"
    message.kind = "reply"
    message.sent_at = now
    message.ai_meta = {**message.ai_meta, "approved_by": str(actor.id)}
    ticket.pending_approval = False
    ticket.first_response_at = ticket.first_response_at or now
    ticket.human_replied_at = ticket.human_replied_at or now
    ticket.last_message_at = now
    if ticket.assignee_id is None and actor.id is not None:
        ticket.assignee_id = actor.id
    await _set_status(session, actor, ticket, "pending")
    sla.refresh(ticket)
    event(session, ticket, "approved", "agent", actor.id, message_id=str(message.id))
    await email_customer(session, ticket, message)
    audit(session, actor, "ai.approved", "message", message.id)
    await dispatch(session, ticket.org_id, "message.created", {"message": message_payload(message)})
    announce(session, ticket, message)
    return message


async def reject(session: AsyncSession, actor: Actor, message: Message) -> None:
    ticket = await get_ticket(session, actor.scope, message.ticket_id, lock=True)
    message = await _locked_message(session, message.id)
    if message.status not in ("pending", "draft"):
        raise AppError("This answer is not waiting for a decision", code="not_pending")
    message.status = "rejected" if message.status == "pending" else "discarded"
    ticket.pending_approval = await pending_count(session, ticket.id) > 0
    event(session, ticket, "rejected", "agent", actor.id, message_id=str(message.id))
    audit(session, actor, "ai.rejected", "message", message.id)
    announce(session, ticket)


async def pending_count(session: AsyncSession, ticket_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.ticket_id == ticket_id, Message.status == "pending")
        )
        or 0
    )


async def customer_resolves(session: AsyncSession, ticket: Ticket, customer: Customer) -> None:
    """The customer says the answer solved it. With no person involved it counts as an
    AI resolution."""
    if ticket.status in ("resolved", "closed"):
        return
    previous = ticket.status
    ticket.status = "resolved"
    ticket.resolved_at = _now()
    ticket.ai_resolved = ticket.handled_by == "ai" and ticket.human_replied_at is None
    event(
        session,
        ticket,
        "status",
        "customer",
        customer.id,
        before=previous,
        after="resolved",
        ai_resolved=ticket.ai_resolved,
    )
    await dispatch(session, ticket.org_id, "ticket.resolved", {"ticket": ticket_payload(ticket)})
    announce(session, ticket)


async def rate(session: AsyncSession, ticket: Ticket, score: int, comment: str | None) -> None:
    if ticket.status not in ("resolved", "closed"):
        raise AppError("Rate a conversation once it is resolved", code="not_resolved")
    if not 1 <= score <= 5:
        raise AppError("A rating is from 1 to 5", code="invalid_rating")
    ticket.csat_score = score
    ticket.csat_comment = (comment or "").strip()[:2000] or None
    event(session, ticket, "rated", "customer", ticket.customer_id, score=score)
    announce(session, ticket)
