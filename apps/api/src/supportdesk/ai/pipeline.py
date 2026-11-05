"""The ``ai.reply`` job: the AI's turn after a customer message.

1. Read the conversation (short session; no transaction held across model calls).
2. Run the engine: triage, gate, cache, retrieval, answer, grounding, decision.
3. Write the outcome in one fenced transaction: the AI message (unique per customer
   message, so a redelivered job cannot answer twice), ticket fields, the handoff, ledger
   rows, the answer cache, knowledge gaps, then live events after commit.

A provider failure is retried while attempts remain (the customer waits a few seconds);
on the last attempt, or when a retry cannot help, the conversation goes to a person with
``ai_unavailable``. If the job itself dies (worker crash on every attempt), ``on_dead``
still hands it over, so an accepted message is never left unanswered.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.ai import cache, ledger, policy
from supportdesk.ai.engine import Engine, Result, Turn
from supportdesk.ai.registry import runtime_for
from supportdesk.ai.triage import PRIORITY_RANK
from supportdesk.channels.models import Inbox
from supportdesk.core import jobs
from supportdesk.core.events import publish_pending
from supportdesk.customers.models import Customer
from supportdesk.customers.service import contact_address
from supportdesk.integrations.service import dispatch
from supportdesk.observability import metrics
from supportdesk.org.service import load_settings
from supportdesk.tickets import service as tickets
from supportdesk.tickets.models import Message, Ticket

log = logging.getLogger("supportdesk.ai")

HANDOFF = "I'm connecting you with a teammate who can help with this. They'll reply right here."
HANDOFF_EMAIL = (
    "I'm connecting you with a teammate who can help with this. They'll reply here and by email."
)
APPROVAL = "Thanks! A teammate is checking this and will reply shortly."
ACK = "Thanks for reaching out! A teammate will reply soon."


def _handoff_text(reasons: tuple[str, ...], has_email: bool, approval: bool) -> str:
    if approval:
        return APPROVAL
    if policy.AI_OFF in reasons:
        return ACK
    return HANDOFF_EMAIL if has_email else HANDOFF


async def _load(
    ctx: jobs.JobContext, message_id: uuid.UUID
) -> tuple[Message, Ticket, Customer, Inbox, Turn] | None:
    async with ctx.container.db.sessionmaker() as session:
        message = await session.get(Message, message_id)
        if message is None:
            return None
        ticket = await session.get(Ticket, message.ticket_id)
        if ticket is None or ticket.handled_by != "ai":
            return None
        answered = await session.scalar(
            select(Message.id).where(
                Message.reply_to_id == message.id, Message.author_type.in_(("ai", "system"))
            )
        )
        if answered is not None:
            return None
        customer = await session.get(Customer, ticket.customer_id)
        inbox = await session.get(Inbox, ticket.inbox_id)
        assert customer is not None
        assert inbox is not None
        rows = (
            await session.execute(
                select(
                    Message.author_type,
                    Message.body,
                    Message.feedback,
                    Message.kind,
                    Message.status,
                )
                .where(
                    Message.ticket_id == ticket.id,
                    Message.created_at <= message.created_at,
                    Message.id != message.id,
                )
                .order_by(Message.created_at)
            )
        ).all()
    history = [
        (r.author_type, r.body)
        for r in rows
        if r.kind == "reply" and r.status == "sent" and r.author_type in ("customer", "ai", "agent")
    ]
    ai_turns = sum(1 for r in rows if r.author_type == "ai" and r.status == "sent")
    unhelpful = sum(1 for r in rows if r.author_type == "ai" and r.feedback == "unhelpful")
    turn = Turn(
        question=message.body,
        history=history,
        ai_turns=ai_turns,
        unhelpful=unhelpful,
        vip=customer.vip,
        inbox_ai_enabled=inbox.ai_enabled,
        first_question=not any(r.author_type in ("ai", "agent") for r in rows),
        ticket_id=ticket.id,
    )
    return message, ticket, customer, inbox, turn


async def reply(ctx: jobs.JobContext) -> None:
    container = ctx.container
    message_id = uuid.UUID(ctx.payload["message_id"])
    loaded = await _load(ctx, message_id)
    if loaded is None:
        return  # people own it now, or it was already answered: nothing to do
    message, ticket, customer, inbox, turn = loaded
    async with container.db.sessionmaker() as session:
        bundle = await load_settings(session, ticket.org_id)
    runtime = await runtime_for(container, ticket.org_id)
    engine = Engine(container, bundle, runtime)
    result = await engine.run(turn)

    if result.retryable and not ctx.last_attempt:
        await _record_ledger(ctx, ticket, result)
        raise jobs.RetryLaterError(result.provider_error or "AI provider unavailable")

    summary = None
    if result.action in ("escalate", "draft", "approval") and not result.smalltalk:
        summary = await engine.summarize(
            result, [*turn.history, ("customer", turn.question)], list(result.reasons)
        )
    await _write(
        ctx,
        message,
        ticket,
        customer,
        inbox,
        bundle.org.kb_version,
        bundle.token_saver.cache_ttl_hours,
        turn,
        result,
        summary,
    )
    metrics.ai_decisions.labels(
        result.action, (result.answer.method if result.answer else "none")
    ).inc()


async def _record_ledger(ctx: jobs.JobContext, ticket: Ticket, result: Result) -> None:
    async with ctx.container.db.sessionmaker() as session:
        for entry in result.ledger:
            ledger.record_entry(session, ticket.org_id, ticket.id, entry)
        await session.commit()


async def _write(
    ctx: jobs.JobContext,
    message: Message,
    ticket_in: Ticket,
    customer: Customer,
    inbox: Inbox,
    kb_version: int,
    cache_ttl_hours: int,
    turn: Turn,
    result: Result,
    summary: str | None,
) -> None:
    async with ctx.fenced() as session:
        ticket = await session.get(Ticket, ticket_in.id, with_for_update=True)
        assert ticket is not None
        if ticket.handled_by != "ai":
            # A person took over while the AI was thinking: their reply wins, but the calls
            # already made still count (the budget was charged for them).
            for entry in result.ledger:
                ledger.record_entry(session, ticket.org_id, ticket.id, entry)
            ticket.ai_tokens += result.tokens
            ticket.ai_cost_usd = (ticket.ai_cost_usd or Decimal(0)) + result.cost
            return
        await _apply(
            ctx,
            session,
            message,
            ticket,
            customer,
            kb_version,
            cache_ttl_hours,
            turn,
            result,
            summary,
        )
    await publish_pending(ctx.container, session)


async def _apply(
    ctx: jobs.JobContext,
    session: AsyncSession,
    message: Message,
    ticket: Ticket,
    customer: Customer,
    kb_version: int,
    cache_ttl_hours: int,
    turn: Turn,
    result: Result,
    summary: str | None,
) -> None:
    container = ctx.container
    now = datetime.now(UTC)
    t = result.triage
    if not result.smalltalk:
        ticket.category = ticket.category or t.category
        ticket.sentiment = t.sentiment
        ticket.intent = t.intent
        ticket.language = t.language
        if PRIORITY_RANK.get(t.priority, 1) > PRIORITY_RANK.get(ticket.priority, 1):
            ticket.priority = t.priority
    for entry in result.ledger:
        ledger.record_entry(session, ticket.org_id, ticket.id, entry)
    ticket.ai_tokens += result.tokens
    ticket.ai_cost_usd = (ticket.ai_cost_usd or Decimal(0)) + result.cost
    if result.cache_hit is not None:
        await cache.hit(session, result.cache_hit.id)
    meta = result.meta()
    citations = (
        [h.citation() for h in result.answer.cited]
        if result.answer and result.answer.cited
        else (result.cache_hit.citations if result.cache_hit else [])
    )

    if result.action == "send" and result.answer is not None:
        ai_message = Message(
            org_id=ticket.org_id,
            ticket_id=ticket.id,
            author_type="ai",
            kind="reply",
            status="sent",
            body=result.answer.text,
            citations=citations,
            reply_to_id=message.id,
            ai_meta=meta,
            sent_at=now,
        )
        session.add(ai_message)
        ticket.status = "pending"
        ticket.ai_answered_at = now
        if not result.smalltalk:
            # "Hi!" back is not a response to anything: it neither counts as the first
            # response nor (see tickets.tasks.auto_resolve) as an AI resolution.
            ticket.first_response_at = ticket.first_response_at or now
        ticket.last_message_at = now
        tickets.event(
            session, ticket, "ai.answered", "ai", None, method=meta["method"], cache=meta["cache"]
        )
        await session.flush()
        if (
            turn.first_question
            and result.cache_hit is None
            and result.answer.method == "model"
            and result.answer.grounded
        ):
            await cache.store(
                session,
                container.kv,
                ticket.org_id,
                kb_version,
                turn.question,
                result.question_vector,
                result.answer.text,
                citations,
                t.category,
                result.tokens,
                result.cost,
                cache_ttl_hours * 3600,
            )
        if ticket.channel == "email":
            # On the widget the customer is reading live; email only when they wrote by email.
            await tickets.email_customer(session, ticket, ai_message)
        await dispatch(
            session,
            ticket.org_id,
            "message.created",
            {"message": tickets.message_payload(ai_message)},
        )
        tickets.announce(session, ticket, ai_message)
        return

    approval = result.action == "approval"
    if result.action in ("draft", "approval") and result.answer is not None:
        session.add(
            Message(
                org_id=ticket.org_id,
                ticket_id=ticket.id,
                author_type="ai",
                kind="reply" if approval else "draft",
                status="pending" if approval else "draft",
                body=result.answer.text,
                citations=citations,
                reply_to_id=message.id,
                ai_meta=meta,
            )
        )
        ticket.pending_approval = ticket.pending_approval or approval
    else:
        # Record the decision itself on the conversation (no answer was written).
        tickets.event(
            session,
            ticket,
            "ai.decision",
            "ai",
            None,
            **{k: v for k, v in meta.items() if k != "timings_ms"},
        )
    handoff = Message(
        org_id=ticket.org_id,
        ticket_id=ticket.id,
        author_type="system",
        kind="reply",
        status="sent",
        body=_handoff_text(result.reasons, bool(contact_address(customer)), approval),
        reply_to_id=message.id,
        ai_meta={"handoff": True, "reasons": list(result.reasons)},
        sent_at=now,
    )
    session.add(handoff)
    ticket.last_message_at = now
    await session.flush()
    await tickets.escalate(session, ticket, list(result.reasons), summary=summary)
    if policy.NO_ANSWER in result.reasons and policy.SENSITIVE not in result.reasons:
        from supportdesk.gaps.service import record_question

        await record_question(
            session, ticket, message, turn.question, "no_answer", result.question_vector
        )
    tickets.announce(session, ticket, handoff)


async def handover_after_failure(ctx: jobs.JobContext, error: str) -> None:
    """The job could not complete at all: a person takes the conversation."""
    message_id = uuid.UUID(ctx.payload["message_id"])
    container = ctx.container
    async with container.db.sessionmaker() as session:
        message = await session.get(Message, message_id)
        if message is None:
            return
        ticket = await session.get(Ticket, message.ticket_id, with_for_update=True)
        if ticket is None or ticket.handled_by != "ai":
            return
        existing = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.reply_to_id == message.id, Message.author_type.in_(("ai", "system")))
        )
        if existing:
            return
        customer = await session.get(Customer, ticket.customer_id)
        session.add(
            Message(
                org_id=ticket.org_id,
                ticket_id=ticket.id,
                author_type="system",
                kind="reply",
                status="sent",
                body=HANDOFF_EMAIL if customer and contact_address(customer) else HANDOFF,
                reply_to_id=message.id,
                ai_meta={"handoff": True, "reasons": [policy.AI_UNAVAILABLE], "error": error[:300]},
                sent_at=datetime.now(UTC),
            )
        )
        await tickets.escalate(session, ticket, [policy.AI_UNAVAILABLE])
        await session.commit()
        await publish_pending(container, session)
    log.warning(
        "AI turn failed, handed over", extra={"ticket_id": str(ticket.id), "error": error[:200]}
    )


jobs.handles(tickets.AI_REPLY, on_dead=handover_after_failure)(reply)
