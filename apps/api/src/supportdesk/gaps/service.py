"""Knowledge gaps: what customers ask that the knowledge base does not answer.

Questions are recorded when the AI had no grounded answer or a customer marked an answer
unhelpful. The ``gaps.cluster`` task groups them greedily by embedding: a question joins
the open gap whose centroid is within ``JOIN_SIMILARITY``, else starts a new one. A gap's
title is its most representative question. An agent turns a gap into an article: the
draft comes from the replies people sent on those conversations (or a model when one is
configured), and publishing it closes the gap and lets the AI answer next time.
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.audit.service import Actor, audit
from supportdesk.core.container import Container
from supportdesk.core.db import OrgScope
from supportdesk.core.errors import AppError, NotFoundError
from supportdesk.core.tasks import periodic
from supportdesk.gaps.models import GapQuestion, KnowledgeGap
from supportdesk.knowledge.retrieval import calibrate
from supportdesk.tickets.models import Message, Ticket

# A question joins a gap when its calibrated similarity to the gap's centroid reaches this
# (calibration per embedder, as in retrieval: about 0.73 raw cosine for bge-small).
log = logging.getLogger("supportdesk.gaps")
JOIN_SIMILARITY = 0.6
BATCH = 200


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def mean(vectors: list[list[float]]) -> list[float]:
    n = len(vectors)
    return [sum(col) / n for col in zip(*vectors, strict=True)]


async def record_question(
    session: AsyncSession,
    ticket: Ticket,
    message: Message,
    question: str,
    reason: str,
    vector: list[float] | None,
) -> None:
    """Idempotent per customer message (unique message_id)."""
    await session.execute(
        insert(GapQuestion)
        .values(
            id=uuid.uuid4(),
            org_id=ticket.org_id,
            ticket_id=ticket.id,
            message_id=message.id,
            question=question[:2000],
            reason=reason,
            embedding=vector,
            dims=len(vector) if vector else 0,
        )
        .on_conflict_do_nothing(index_elements=["message_id"])
    )


async def cluster_org(container: Container, session: AsyncSession, org_id: uuid.UUID) -> int:
    questions = list(
        (
            await session.scalars(
                select(GapQuestion)
                .where(GapQuestion.org_id == org_id, GapQuestion.gap_id.is_(None))
                .order_by(GapQuestion.created_at)
                .limit(BATCH)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    if not questions:
        return 0
    from supportdesk.ai.registry import runtime_for

    embedder = (await runtime_for(container, org_id)).embedder
    embedder_name = embedder.name
    missing = [q for q in questions if q.embedding is None]
    if missing:
        vectors = await embedder.embed([q.question for q in missing], kind="query")
        for q, v in zip(missing, vectors, strict=True):
            q.embedding, q.dims = v, len(v)
    gaps = list(
        (
            await session.scalars(
                select(KnowledgeGap).where(
                    KnowledgeGap.org_id == org_id, KnowledgeGap.status.in_(("open", "drafted"))
                )
            )
        ).all()
    )
    members: dict[uuid.UUID, list[list[float]]] = {}
    for q in questions:
        vec = [float(x) for x in q.embedding]
        best, best_sim = None, 0.0
        for gap in gaps:
            if gap.centroid is None or gap.dims != len(vec):
                continue
            sim = calibrate(cosine(vec, [float(x) for x in gap.centroid]), embedder_name)
            if sim > best_sim:
                best, best_sim = gap, sim
        if best is None or best_sim < JOIN_SIMILARITY:
            best = KnowledgeGap(
                org_id=org_id,
                title=q.question[:300],
                status="open",
                question_count=0,
                centroid=vec,
                dims=len(vec),
            )
            session.add(best)
            await session.flush()
            gaps.append(best)
        q.gap_id = best.id
        best.question_count += 1
        best.last_seen_at = datetime.now(UTC)
        members.setdefault(best.id, []).append(vec)
        n = best.question_count
        old = [float(x) for x in best.centroid] if best.centroid is not None else vec
        best.centroid = [(o * (n - 1) + v) / n for o, v in zip(old, vec, strict=True)]
    await session.commit()
    return len(questions)


@periodic("gaps.cluster", every_s=60)
async def cluster_task(container: Container) -> int:
    async with container.db.sessionmaker() as session:
        orgs = (
            await session.scalars(
                select(GapQuestion.org_id).where(GapQuestion.gap_id.is_(None)).distinct().limit(50)
            )
        ).all()
    done = 0
    for org_id in orgs:
        # Each organisation on its own session and time budget: one tenant's slow or
        # broken embedder must not stop clustering for the others.
        try:
            async with container.db.sessionmaker() as org_session:
                done += await asyncio.wait_for(
                    cluster_org(container, org_session, org_id), timeout=60
                )
        except Exception as exc:
            log.warning(
                "gap clustering failed", extra={"org_id": str(org_id), "error": type(exc).__name__}
            )
    return done


async def get_gap(session: AsyncSession, scope: OrgScope, gap_id: uuid.UUID) -> KnowledgeGap:
    gap = await session.get(KnowledgeGap, gap_id)
    if gap is None or gap.org_id != scope.org_id:
        raise NotFoundError("Knowledge gap not found")
    return gap


async def examples(session: AsyncSession, gap_id: uuid.UUID, limit: int = 10) -> list[GapQuestion]:
    return list(
        (
            await session.scalars(
                select(GapQuestion)
                .where(GapQuestion.gap_id == gap_id)
                .order_by(GapQuestion.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


async def resolving_replies(session: AsyncSession, gap_id: uuid.UUID, limit: int = 5) -> list[str]:
    """What people answered on the conversations behind this gap."""
    ticket_ids = select(GapQuestion.ticket_id).where(GapQuestion.gap_id == gap_id)
    rows = await session.scalars(
        select(Message.body)
        .where(
            Message.ticket_id.in_(ticket_ids),
            Message.author_type == "agent",
            Message.kind == "reply",
            Message.status == "sent",
        )
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return list(rows.all())


async def draft_article(
    container: Container, session: AsyncSession, actor: Actor, gap_id: uuid.UUID
) -> dict[str, str]:
    """A title and body for an article closing this gap. From the agents' replies,
    rewritten by the model when one is configured; quoted as they are otherwise."""
    from supportdesk.ai.prompts import ARTICLE_SYSTEM, NO_ANSWER
    from supportdesk.ai.providers.base import ChatMessage, ProviderError
    from supportdesk.ai.registry import runtime_for

    gap = await get_gap(session, actor.scope, gap_id)
    asked = [q.question for q in await examples(session, gap.id, 5)]
    replies = await resolving_replies(session, gap.id)
    title = gap.title.rstrip("?").strip()
    title = title[:1].upper() + title[1:]
    # With no agent reply there is nothing true to draft from: an empty body, never a
    # placeholder that could be published by mistake.
    body = "\n\n".join(replies)
    source = "agent_replies" if replies else "none"
    runtime = await runtime_for(container, actor.org_id)
    if runtime.chat is not None and replies:
        from supportdesk.ai.engine import Engine, Result
        from supportdesk.ai.ledger import record_entry
        from supportdesk.ai.redact import redact
        from supportdesk.ai.triage import Triage
        from supportdesk.org.service import load_settings

        prompt = redact(
            "Questions:\n"
            + "\n".join(f"- {q}" for q in asked)
            + "\n\nAgent replies:\n"
            + "\n\n".join(replies)
        )[0]
        # Through the engine: the call is reserved against the hard budget like any other.
        engine = Engine(container, await load_settings(session, actor.org_id), runtime)
        result = Result("draft", (), Triage(), None)
        try:
            text = await engine.call(
                result,
                "article",
                [
                    ChatMessage("system", ARTICLE_SYSTEM.format(no_answer=NO_ANSWER)),
                    ChatMessage("user", prompt),
                ],
                model=runtime.config.model_for("answer"),
                max_tokens=400,
            )
        except ProviderError:
            text = None  # the replies themselves are a fine draft
        for entry in result.ledger:
            record_entry(session, actor.org_id, None, entry)
        text = (text or "").strip()
        if text and NO_ANSWER not in text[:20]:
            head, _, rest = text.partition("\n")
            title = head.lstrip("# ").strip()[:300] or title
            body = rest.strip() or body
            source = "model"
    if gap.status == "open":
        gap.status = "drafted"
    audit(session, actor, "gap.drafted", "gap", gap.id)
    await session.commit()
    return {"title": title, "body": body, "source": source}


async def set_status(
    session: AsyncSession, actor: Actor, gap_id: uuid.UUID, status: str
) -> KnowledgeGap:
    if status not in ("open", "dismissed"):
        raise AppError("A gap can be reopened or dismissed", code="invalid_status")
    gap = await get_gap(session, actor.scope, gap_id)
    gap.status = status
    audit(session, actor, f"gap.{status}", "gap", gap.id)
    await session.commit()
    return gap


async def close_with_article(
    session: AsyncSession, scope: OrgScope, gap_id: uuid.UUID, article_id: uuid.UUID
) -> None:
    await session.execute(
        update(KnowledgeGap)
        .where(KnowledgeGap.id == gap_id, KnowledgeGap.org_id == scope.org_id)
        .values(status="resolved", article_id=article_id)
    )


async def open_count(session: AsyncSession, scope: OrgScope) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(KnowledgeGap)
            .where(
                KnowledgeGap.org_id == scope.org_id, KnowledgeGap.status.in_(("open", "drafted"))
            )
        )
        or 0
    )
