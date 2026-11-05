"""Read side of the inbox: lists, counts and the conversation view.

A list page costs three queries whatever its size: the tickets (keyset on
``last_message_at, id``), their customers, and the last visible message of each
(``DISTINCT ON``). No per-row lookups.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, func, or_, select, text, tuple_
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.core.db import OrgScope
from supportdesk.core.schemas import decode_cursor, encode_cursor
from supportdesk.customers.models import Customer
from supportdesk.tickets import sla
from supportdesk.tickets.models import Attachment, Message, Ticket, TicketEvent
from supportdesk.tickets.schemas import (
    AttachmentOut,
    CustomerBrief,
    EventOut,
    MessageOut,
    PortalTicket,
    PortalTicketDetail,
    PublicCitation,
    PublicMessage,
    TicketDetail,
    TicketOut,
    ViewCounts,
)
from supportdesk.users.models import User

OPEN = ("open", "pending")


def _view(stmt: Select[Any], view: str, user_id: uuid.UUID | None) -> Select[Any]:
    if view == "mine":
        return stmt.where(Ticket.assignee_id == user_id, Ticket.status.in_(OPEN))
    if view == "unassigned":
        return stmt.where(
            Ticket.assignee_id.is_(None), Ticket.handled_by == "human", Ticket.status.in_(OPEN)
        )
    if view == "ai":
        return stmt.where(Ticket.handled_by == "ai")
    if view == "approvals":
        return stmt.where(Ticket.pending_approval.is_(True))
    if view == "escalated":
        return stmt.where(Ticket.escalated_at.is_not(None), Ticket.status.in_(OPEN))
    if view == "sla":
        soon = datetime.now(UTC) + timedelta(hours=2)
        return stmt.where(
            Ticket.status.in_(OPEN),
            or_(
                Ticket.sla_breached.is_(True),
                and_(Ticket.sla_next_due_at.is_not(None), Ticket.sla_next_due_at < soon),
            ),
        )
    if view == "resolved":
        return stmt.where(Ticket.status.in_(("resolved", "closed")))
    return stmt


async def list_tickets(
    session: AsyncSession,
    scope: OrgScope,
    *,
    view: str = "all",
    user_id: uuid.UUID | None = None,
    status: str | None = None,
    priority: str | None = None,
    channel: str | None = None,
    category: str | None = None,
    assignee_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    tag: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = 30,
) -> tuple[list[TicketOut], str | None]:
    stmt: Select[Any] = select(Ticket).where(Ticket.org_id == scope.org_id)
    stmt = _view(stmt, view, user_id)
    if status:
        stmt = stmt.where(Ticket.status == status)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if channel:
        stmt = stmt.where(Ticket.channel == channel)
    if category:
        stmt = stmt.where(Ticket.category == category)
    if assignee_id:
        stmt = stmt.where(Ticket.assignee_id == assignee_id)
    if customer_id:
        stmt = stmt.where(Ticket.customer_id == customer_id)
    if tag:
        stmt = stmt.where(Ticket.tags.contains([tag.lower()]))
    if q and q.strip():
        query = func.plainto_tsquery("simple", q.strip()[:200])
        number = q.strip().lstrip("#")
        in_messages = select(Message.ticket_id).where(
            Message.org_id == scope.org_id, Message.search.op("@@")(query)
        )
        conditions: list[ColumnElement[bool]] = [
            Ticket.search.op("@@")(query),
            Ticket.id.in_(in_messages),
        ]
        if number.isdigit() and len(number) < 10:
            conditions.append(Ticket.number == int(number))
        stmt = stmt.where(or_(*conditions))
    decoded = decode_cursor(cursor)
    if decoded and "|" in decoded:
        at, _, tid = decoded.partition("|")
        # A malformed cursor reads as "from the start" rather than an error.
        with contextlib.suppress(ValueError):
            stmt = stmt.where(
                tuple_(Ticket.last_message_at, Ticket.id)
                < (datetime.fromisoformat(at), uuid.UUID(tid))
            )
    rows = list(
        (
            await session.scalars(
                stmt.order_by(Ticket.last_message_at.desc(), Ticket.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    more = len(rows) > limit
    rows = rows[:limit]
    items = await to_out(session, rows)
    next_cursor = (
        encode_cursor(f"{rows[-1].last_message_at.isoformat()}|{rows[-1].id}")
        if more and rows
        else None
    )
    return items, next_cursor


async def to_out(session: AsyncSession, rows: list[Ticket]) -> list[TicketOut]:
    if not rows:
        return []
    customers = {
        c.id: c
        for c in (
            await session.scalars(
                select(Customer).where(Customer.id.in_({t.customer_id for t in rows}))
            )
        ).all()
    }
    previews = {
        r.ticket_id: (r.body, r.author_type)
        for r in (
            await session.execute(
                select(Message.ticket_id, Message.body, Message.author_type)
                .ext(distinct_on(Message.ticket_id))
                .where(
                    Message.ticket_id.in_([t.id for t in rows]),
                    Message.kind == "reply",
                    Message.status == "sent",
                )
                .order_by(Message.ticket_id, Message.created_at.desc())
            )
        ).all()
    }
    now = datetime.now(UTC)
    out = []
    for t in rows:
        c = customers[t.customer_id]
        body, author = previews.get(t.id, ("", None))
        item = TicketOut.model_validate(
            {
                **{
                    k: getattr(t, k)
                    for k in TicketOut.model_fields
                    if hasattr(t, k) and k != "customer"
                },
                "customer": CustomerBrief.model_validate(c),
                "preview": " ".join(body.split())[:160],
                "preview_author": author,
                "sla_state": sla.state(t, now) if t.handled_by == "human" else "none",
            }
        )
        out.append(item)
    return out


async def detail(
    session: AsyncSession, ticket: Ticket, *, include_internal: bool = True
) -> TicketDetail:
    base = (await to_out(session, [ticket]))[0]
    # Messages appear when they reached the customer: an answer approved later sorts
    # after the handoff line written with it.
    stmt = (
        select(Message)
        .where(Message.ticket_id == ticket.id)
        .order_by(
            func.coalesce(Message.sent_at, Message.created_at), Message.created_at, Message.id
        )
    )
    if not include_internal:
        stmt = stmt.where(Message.kind == "reply", Message.status == "sent")
    messages = list((await session.scalars(stmt)).all())
    agent_ids = {m.author_id for m in messages if m.author_type == "agent" and m.author_id}
    names = (
        {
            u.id: u.name
            for u in (await session.scalars(select(User).where(User.id.in_(agent_ids)))).all()
        }
        if agent_ids
        else {}
    )
    events = (
        list(
            (
                await session.scalars(
                    select(TicketEvent)
                    .where(TicketEvent.ticket_id == ticket.id)
                    .order_by(TicketEvent.id)
                )
            ).all()
        )
        if include_internal
        else []
    )
    attachments = list(
        (
            await session.scalars(
                select(Attachment)
                .where(Attachment.ticket_id == ticket.id)
                .order_by(Attachment.created_at)
            )
        ).all()
    )
    return TicketDetail.model_validate(
        {
            **base.model_dump(),
            **{
                k: getattr(ticket, k)
                for k in (
                    "summary",
                    "language",
                    "csat_score",
                    "csat_comment",
                    "first_response_at",
                    "human_replied_at",
                    "resolved_at",
                    "escalated_at",
                    "first_response_due_at",
                    "resolution_due_at",
                    "reopened_count",
                    "ai_cost_usd",
                    "ai_tokens",
                )
            },
            "messages": [
                MessageOut.model_validate(
                    {
                        **{k: getattr(m, k) for k in MessageOut.model_fields if hasattr(m, k)},
                        "author_name": names.get(m.author_id) if m.author_id else None,
                        "ai_meta": m.ai_meta if include_internal else {},
                    }
                )
                for m in messages
            ],
            "events": [EventOut.model_validate(e) for e in events],
            "attachments": [AttachmentOut.model_validate(a) for a in attachments],
        }
    )


async def view_counts(
    session: AsyncSession, scope: OrgScope, user_id: uuid.UUID | None
) -> ViewCounts:
    soon = datetime.now(UTC) + timedelta(hours=2)
    row = (
        await session.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE status IN ('open','pending')) AS "all",
                  count(*) FILTER (WHERE assignee_id = :uid AND status IN ('open','pending')) AS mine,
                  count(*) FILTER (WHERE assignee_id IS NULL AND handled_by = 'human' AND status IN ('open','pending')) AS unassigned,
                  count(*) FILTER (WHERE handled_by = 'ai' AND status IN ('open','pending')) AS ai,
                  count(*) FILTER (WHERE pending_approval) AS approvals,
                  count(*) FILTER (WHERE escalated_at IS NOT NULL AND status IN ('open','pending')) AS escalated,
                  count(*) FILTER (WHERE status IN ('open','pending') AND (sla_breached OR sla_next_due_at < :soon)) AS sla
                FROM tickets WHERE org_id = :org
                """
            ),
            {"org": scope.org_id, "uid": user_id, "soon": soon},
        )
    ).one()
    return ViewCounts.model_validate(dict(row._mapping))


def public_messages(detail: TicketDetail) -> list[PublicMessage]:
    """The customer-visible messages of a conversation, through the whitelist."""
    return [
        PublicMessage(
            id=m.id,
            author_type=m.author_type,
            author_name=m.author_name,
            body=m.body,
            citations=[
                PublicCitation(title=c.title, heading=c.heading, url=c.url) for c in m.citations
            ],
            feedback=m.feedback,
            created_at=m.created_at,
        )
        for m in detail.messages
        if m.kind == "reply" and m.status == "sent"
    ]


def portal_ticket(item: TicketOut) -> PortalTicket:
    return PortalTicket(
        id=item.id,
        number=item.number,
        subject=item.subject,
        status=item.status,
        channel=item.channel,
        preview=item.preview,
        last_message_at=item.last_message_at,
        created_at=item.created_at,
    )


async def portal_detail(session: AsyncSession, ticket: Ticket) -> PortalTicketDetail:
    detail = await detail_for(session, ticket)
    return PortalTicketDetail(
        **portal_ticket(detail).model_dump(),
        csat_score=detail.csat_score,
        messages=public_messages(detail),
    )


async def detail_for(session: AsyncSession, ticket: Ticket) -> TicketDetail:
    return await detail(session, ticket, include_internal=False)
