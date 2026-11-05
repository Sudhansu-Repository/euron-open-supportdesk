"""Token Saver caches: reuse an answer the AI already sent.

* exact: the normalised question (case, punctuation and stopwords removed) hashed, looked
  up in the KV store (Redis or memory) and then in Postgres;
* semantic: the question's embedding against previous questions, cosine similarity at or
  above the organisation's threshold.

Both are keyed on the organisation's knowledge version, which every knowledge change
bumps, so an answer can never outlive the documents it came from. Only answers that were
grounded and sent are stored; one a customer marked unhelpful is disabled for good.
Caches are used only for the first question of a conversation, where the answer cannot
depend on earlier turns.
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import orjson
from sqlalchemy import text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.ai.models import AnswerCache
from supportdesk.ai.redact import redact
from supportdesk.ai.text import entities, question_hash
from supportdesk.core.kv import KV
from supportdesk.knowledge.models import INDEXED_DIMS
from supportdesk.observability.metrics import DEPENDENCY_ERRORS


@dataclass(frozen=True)
class CachedAnswer:
    id: uuid.UUID
    answer: str
    citations: list[dict[str, Any]]
    tokens: int
    cost_usd: Decimal
    kind: str  # exact or semantic
    similarity: float = 1.0


def _kv_key(org_id: uuid.UUID, kb_version: int, qhash: str) -> str:
    return f"sd:ac:{org_id}:{kb_version}:{qhash}"


async def lookup_exact(
    session: AsyncSession, kv: KV, org_id: uuid.UUID, kb_version: int, question: str, ttl_s: int
) -> CachedAnswer | None:
    qhash = question_hash(question)
    try:
        raw = await kv.get(_kv_key(org_id, kb_version, qhash))
    except Exception:
        raw = None  # a cache outage is a miss, never an error
        DEPENDENCY_ERRORS.labels("kv", "get").inc()
    if raw:
        data = orjson.loads(raw)
        entry_id = uuid.UUID(data["id"])
        # The KV copy saves the full row read, but a primary-key check still confirms the
        # entry exists and was not disabled (by an "unhelpful" vote in any process).
        alive = await session.scalar(
            text("SELECT 1 FROM answer_cache WHERE id = :id AND NOT disabled"), {"id": entry_id}
        )
        if alive:
            return CachedAnswer(
                entry_id,
                data["answer"],
                data["citations"],
                data["tokens"],
                Decimal(data["cost"]),
                "exact",
            )
    row = (
        await session.execute(
            text(
                "SELECT id, answer, citations, tokens, cost_usd FROM answer_cache "
                "WHERE org_id = :org AND kb_version = :v AND question_hash = :h AND NOT disabled "
                "AND created_at > now() - make_interval(secs => :ttl)"
            ),
            {"org": org_id, "v": kb_version, "h": qhash, "ttl": ttl_s},
        )
    ).first()
    if row is None:
        return None
    return CachedAnswer(row.id, row.answer, row.citations, row.tokens, row.cost_usd, "exact")


async def lookup_semantic(
    session: AsyncSession,
    org_id: uuid.UUID,
    kb_version: int,
    vector: list[float],
    threshold: float,
    ttl_s: int,
    question: str,
) -> CachedAnswer | None:
    """The nearest earlier question above the threshold that names the same things.

    Embeddings place "What does plan A cost?" and "What does plan B cost?" almost on top of
    each other, so a near neighbour is only reused when both questions mention the same
    entities (numbers, codes, capitalised names); otherwise it is a miss, not a wrong answer.
    """
    wanted = entities(redact(question)[0])
    dims = len(vector)
    if dims not in INDEXED_DIMS:
        return None
    literal = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
    rows = (
        await session.execute(
            text(
                f"SELECT id, question, answer, citations, tokens, cost_usd, "  # noqa: S608 dims is an int from INDEXED_DIMS; values are bound
                f"1 - (embedding::vector({dims}) <=> CAST(:q AS vector({dims}))) AS sim "
                f"FROM answer_cache WHERE org_id = :org AND kb_version = :v AND dims = {dims} "
                f"AND NOT disabled AND created_at > now() - make_interval(secs => :ttl) ORDER BY embedding::vector({dims}) <=> CAST(:q AS vector({dims})) LIMIT 5"  # noqa: E501
            ),
            {"q": literal, "org": org_id, "v": kb_version, "ttl": ttl_s},
        )
    ).all()
    for row in rows:
        if float(row.sim) < threshold:
            break
        if entities(row.question) == wanted:
            return CachedAnswer(
                row.id,
                row.answer,
                row.citations,
                row.tokens,
                row.cost_usd,
                "semantic",
                float(row.sim),
            )
    return None


async def store(
    session: AsyncSession,
    kv: KV,
    org_id: uuid.UUID,
    kb_version: int,
    question: str,
    vector: list[float] | None,
    answer: str,
    citations: list[dict[str, Any]],
    category: str | None,
    tokens: int,
    cost_usd: Decimal,
    ttl_s: int,
) -> None:
    # Lookups hash the redacted question, and secrets must never be persisted: store the
    # redacted text too.
    question = redact(question)[0]
    qhash = question_hash(question)
    entry_id = uuid.uuid4()
    result = await session.execute(
        insert(AnswerCache)
        .values(
            id=entry_id,
            org_id=org_id,
            kb_version=kb_version,
            question_hash=qhash,
            question=question[:2000],
            embedding=vector,
            dims=len(vector) if vector else 0,
            answer=answer,
            citations=citations,
            category=category,
            tokens=tokens,
            cost_usd=cost_usd,
        )
        .on_conflict_do_nothing(constraint="uq_answer_cache_q")
        .returning(AnswerCache.id)
    )
    if result.scalar_one_or_none() is None:
        return  # an entry exists already (possibly disabled): never shadow it in the KV
    payload = orjson.dumps(
        {
            "id": str(entry_id),
            "answer": answer,
            "citations": citations,
            "tokens": tokens,
            "cost": str(cost_usd),
        }
    )
    # Postgres holds the entry; the KV copy is only a faster path, so its failure is ignored.
    with contextlib.suppress(Exception):
        await kv.set(_kv_key(org_id, kb_version, qhash), payload, ttl_s)


async def hit(session: AsyncSession, entry_id: uuid.UUID) -> None:
    await session.execute(
        update(AnswerCache)
        .where(AnswerCache.id == entry_id)
        .values(hits=AnswerCache.hits + 1, last_hit_at=datetime.now(UTC))
    )


async def disable(
    session: AsyncSession,
    kv: KV,
    org_id: uuid.UUID,
    kb_version: int,
    question: str,
    answer_text: str,
) -> None:
    """A customer said this answer did not help: stop reusing it, in Postgres and the KV."""
    question = redact(question)[0]
    await session.execute(
        update(AnswerCache)
        .where(AnswerCache.org_id == org_id, AnswerCache.answer == answer_text)
        .values(disabled=True)
    )
    # The KV entry expires with its TTL anyway; Postgres already refuses it.
    with contextlib.suppress(Exception):
        await kv.delete(_kv_key(org_id, kb_version, question_hash(question)))


async def prune(session: AsyncSession, older_than_days: int = 365) -> int:
    """Delete entries of retired knowledge versions, and anything past the longest TTL."""
    result = await session.execute(
        text(
            "DELETE FROM answer_cache a USING orgs o WHERE a.org_id = o.id AND "
            "(a.kb_version < o.kb_version OR a.created_at < now() - make_interval(days => :d))"
        ),
        {"d": older_than_days},
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)
