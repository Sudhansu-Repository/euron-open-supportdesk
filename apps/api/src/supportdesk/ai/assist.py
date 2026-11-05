"""AI help for people: reply drafts in the inbox, and the knowledge playground.

Drafts never reach the customer by themselves; an agent edits and sends them. The
playground runs the real engine on a test question (no conversation is created) and
shows the retrieved passages, their scores and what the policy would do.
"""

from __future__ import annotations

import contextlib
import uuid
from decimal import Decimal

from sqlalchemy import select

from supportdesk.ai import ledger
from supportdesk.ai.answer import extractive, validate
from supportdesk.ai.engine import Engine, Result, Turn
from supportdesk.ai.prompts import DRAFT_SYSTEM, format_sources
from supportdesk.ai.providers.base import ChatMessage, ProviderError
from supportdesk.ai.redact import redact
from supportdesk.ai.registry import runtime_for
from supportdesk.ai.text import truncate_tokens
from supportdesk.core.container import Container
from supportdesk.core.errors import AppError
from supportdesk.knowledge import retrieval
from supportdesk.org.service import load_settings
from supportdesk.tickets.models import Message, Ticket


async def draft(
    container: Container, org_id: uuid.UUID, ticket: Ticket, tone: str, instructions: str | None
) -> dict[str, object]:
    async with container.db.sessionmaker() as session:
        bundle = await load_settings(session, org_id)
        rows = (
            await session.execute(
                select(Message.author_type, Message.body)
                .where(
                    Message.ticket_id == ticket.id,
                    Message.kind == "reply",
                    Message.status == "sent",
                )
                .order_by(Message.created_at)
            )
        ).all()
    history = [(r.author_type, redact(r.body)[0]) for r in rows]
    question = next((t for role, t in reversed(history) if role == "customer"), ticket.subject)
    runtime = await runtime_for(container, org_id)
    vector = None
    with contextlib.suppress(ProviderError):  # full-text search still works without it
        vector = (await runtime.embedder.embed([question], kind="query"))[0]
    async with container.db.sessionmaker() as session:
        found = await retrieval.search(
            session, org_id, question, vector, runtime.embedder.name, top_k=runtime.config.top_k
        )
    threshold = bundle.policy.min_relevance
    passing = found.passing(threshold)
    if runtime.chat is None:
        answer = extractive(question, found.hits, threshold)
        body = answer.text or (
            "Thanks for getting in touch. I'm looking into this and will get back to you shortly."
        )
        return {
            "body": body,
            "citations": [h.citation() for h in answer.cited],
            "grounded": answer.grounded,
            "method": "extractive",
            "tokens": 0,
            "cost_usd": Decimal(0),
        }
    context = retrieval.within_budget(passing or found.hits[:2], runtime.config.context_tokens)
    system = DRAFT_SYSTEM.format(company=bundle.brand.company_name, tone=tone)
    if context:
        system += "\n\nSources:\n" + format_sources(context)
    convo = "\n".join(f"{r.upper()}: {t}" for r, t in history[-10:])
    user = (
        f"Conversation:\n<<<\n{truncate_tokens(convo, 2000)}\n>>>\n\nWrite the agent's next reply."
    )
    if instructions:
        user += f"\nThe agent's notes: {instructions}"
    from supportdesk.ai.triage import Triage

    result = Result("draft", (), Triage(), None)
    engine = Engine(container, bundle, runtime)
    try:
        text = await engine.call(
            result,
            "draft",
            [ChatMessage("system", system), ChatMessage("user", user)],
            model=runtime.config.model_for("answer"),
            max_tokens=500,
        )
    except ProviderError as exc:
        raise AppError(f"The AI provider failed: {exc}", code="ai_unavailable") from exc
    finally:
        async with container.db.sessionmaker() as session:
            for e in result.ledger:
                ledger.record(
                    session,
                    org_id,
                    ticket_id=ticket.id,
                    purpose=e.purpose,
                    provider=e.provider,
                    model=e.model,
                    input_tokens=e.input_tokens,
                    output_tokens=e.output_tokens,
                    cost_usd=e.cost_usd,
                    latency_ms=e.latency_ms,
                    status=e.status,
                    error=e.error,
                )
            await session.commit()
    if text is None:
        raise AppError(
            "The AI budget is spent for now. Raise it in Settings > AI budgets",
            code="budget_exhausted",
        )
    checked = validate(text, context, threshold) if context else None
    return {
        "body": checked.text if checked and checked.text else text.strip(),
        "citations": [h.citation() for h in checked.cited] if checked else [],
        "grounded": bool(checked and checked.grounded),
        "method": "model",
        "tokens": result.tokens,
        "cost_usd": result.cost,
    }


async def playground(container: Container, org_id: uuid.UUID, question: str) -> dict[str, object]:
    async with container.db.sessionmaker() as session:
        bundle = await load_settings(session, org_id)
    runtime = await runtime_for(container, org_id)
    engine = Engine(container, bundle, runtime)
    result = await engine.run(Turn(question=question, history=[], first_question=False))
    async with container.db.sessionmaker() as session:
        for e in result.ledger:
            ledger.record(
                session,
                org_id,
                purpose=e.purpose,
                provider=e.provider,
                model=e.model,
                input_tokens=e.input_tokens,
                output_tokens=e.output_tokens,
                cost_usd=e.cost_usd,
                cache=e.cache,
                latency_ms=e.latency_ms,
                status=e.status,
                error=e.error,
            )
        await session.commit()
    hits = result.retrieval.hits if result.retrieval else []
    return {
        "question": question,
        "action": result.action,
        "reasons": list(result.reasons),
        "answer": result.answer.text if result.answer else None,
        "grounded": bool(result.answer and result.answer.grounded),
        "method": result.answer.method if result.answer else None,
        "citations": [h.citation() for h in (result.answer.cited if result.answer else [])],
        "passages": [
            {
                **h.citation(),
                "text": h.text,
                "similarity": round(h.similarity, 3),
                "coverage": round(h.coverage, 3),
            }
            for h in hits
        ],
        "threshold": bundle.policy.min_relevance,
        "triage": result.meta()["triage"],
        "tokens": result.tokens,
        "cost_usd": result.cost,
        "timings_ms": result.meta()["timings_ms"],
        "provider": runtime.provider,
    }
