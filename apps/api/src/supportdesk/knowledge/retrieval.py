"""Hybrid retrieval: vector similarity and full-text search, fused by reciprocal rank.

Vectors find paraphrases ("I can't get in" for a passage about resetting a password);
full text finds exact terms (error codes, product names) that embeddings blur. Each
returns its top candidates; reciprocal rank fusion orders the union without having to
calibrate the two scores against each other.

The *relevance* used by the grounding gate is separate and explainable: the larger of the
calibrated cosine similarity and the share of the question's content words the passage
contains. A passage must reach the policy's ``min_relevance`` to be cited.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.ai.text import content_words, coverage
from supportdesk.knowledge.models import INDEXED_DIMS

RRF_K = 60

# Cosine similarity is calibrated per embedder family to 0..1: below the floor counts as
# unrelated, above the ceiling as an exact paraphrase. bge models crowd unrelated text
# around 0.5, so their floor is high.
CALIBRATION = {
    "local:BAAI/bge-small-en-v1.5": (0.55, 0.85),
    "local:BAAI/bge-base-en-v1.5": (0.55, 0.85),
    "hash:v1": (0.05, 0.75),
}
DEFAULT_CALIBRATION = (0.35, 0.8)


@dataclass(frozen=True)
class Hit:
    chunk_id: uuid.UUID
    source_id: uuid.UUID | None
    article_id: uuid.UUID | None
    title: str
    heading: str | None
    url: str | None
    text: str
    tokens: int
    similarity: float
    coverage: float
    relevance: float
    fused: float

    def citation(self) -> dict[str, object]:
        return {
            "chunk_id": str(self.chunk_id),
            "source_id": str(self.source_id) if self.source_id else None,
            "article_id": str(self.article_id) if self.article_id else None,
            "title": self.title,
            "heading": self.heading,
            "url": self.url,
            "relevance": round(self.relevance, 3),
        }


@dataclass(frozen=True)
class Retrieval:
    hits: list[Hit]
    ms: float

    @property
    def best(self) -> float:
        return max((h.relevance for h in self.hits), default=0.0)

    def passing(self, threshold: float) -> list[Hit]:
        return [h for h in self.hits if h.relevance >= threshold]


def calibrate(similarity: float, embedder: str) -> float:
    lo, hi = CALIBRATION.get(embedder, DEFAULT_CALIBRATION)
    return max(0.0, min(1.0, (similarity - lo) / (hi - lo)))


def tsquery(question: str) -> str:
    """An OR query of the question's content words, sanitized to safe lexemes."""
    terms = [w for w in dict.fromkeys(content_words(question)) if re.fullmatch(r"[a-z0-9]+", w)]
    return " | ".join(terms[:24])


_COLUMNS = "id, source_id, article_id, title, heading, url, text, tokens"


async def search(
    session: AsyncSession,
    org_id: uuid.UUID,
    question: str,
    query_vector: list[float] | None,
    embedder: str,
    *,
    top_k: int = 5,
    candidates: int = 30,
) -> Retrieval:
    started = time.perf_counter()
    rows: dict[uuid.UUID, dict[str, Any]] = {}
    ranks: dict[uuid.UUID, float] = {}

    if query_vector is not None and len(query_vector) in INDEXED_DIMS:
        dims = len(query_vector)
        literal = "[" + ",".join(f"{v:.6f}" for v in query_vector) + "]"
        # The cast to vector(N) matches the partial expression index for that size.
        result = await session.execute(
            text(
                f"SELECT {_COLUMNS}, 1 - (embedding::vector({dims}) <=> CAST(:q AS vector({dims}))) AS sim "  # noqa: S608, E501 dims is an int from INDEXED_DIMS; values are bound
                f"FROM kb_chunks WHERE org_id = :org AND dims = {dims} AND embed_model = :model "
                f"ORDER BY embedding::vector({dims}) <=> CAST(:q AS vector({dims})) LIMIT :n"
            ),
            {"q": literal, "org": org_id, "model": embedder, "n": candidates},
        )
        for rank, row in enumerate(result.mappings()):
            rows[row["id"]] = dict(row)
            ranks[row["id"]] = ranks.get(row["id"], 0.0) + 1.0 / (RRF_K + rank + 1)

    q = tsquery(question)
    if q:
        result = await session.execute(
            text(
                f"SELECT {_COLUMNS}, ts_rank_cd(search, query) AS lex "  # noqa: S608 dims is an int from INDEXED_DIMS; values are bound
                "FROM kb_chunks, to_tsquery('english', :q) AS query "
                "WHERE org_id = :org AND search @@ query ORDER BY lex DESC LIMIT :n"
            ),
            {"q": q, "org": org_id, "n": candidates},
        )
        for rank, row in enumerate(result.mappings()):
            entry = rows.setdefault(row["id"], dict(row))
            entry.setdefault("sim", None)
            ranks[row["id"]] = ranks.get(row["id"], 0.0) + 1.0 / (RRF_K + rank + 1)

    hits: list[Hit] = []
    for chunk_id, fused in sorted(ranks.items(), key=lambda kv: kv[1], reverse=True)[:top_k]:
        data = rows[chunk_id]
        sim = data.get("sim")
        similarity = calibrate(float(sim), embedder) if sim is not None else 0.0
        passage = f"{data['title']} {data['heading'] or ''} {data['text']}"
        cov = coverage(question, passage)
        hits.append(
            Hit(
                chunk_id=chunk_id,
                source_id=data["source_id"],
                article_id=data["article_id"],
                title=str(data["title"]),
                heading=data["heading"],
                url=data["url"],
                text=str(data["text"]),
                tokens=int(data["tokens"]),
                similarity=similarity,
                coverage=cov,
                relevance=max(similarity, cov),
                fused=fused,
            )
        )
    # Fusion picks the candidates; within them, the most relevant leads the prompt.
    hits.sort(key=lambda h: (h.relevance, h.fused), reverse=True)
    return Retrieval(hits, (time.perf_counter() - started) * 1000)


def within_budget(hits: list[Hit], max_tokens: int) -> list[Hit]:
    """The best hits whose text fits the prompt's context budget (short context)."""
    chosen: list[Hit] = []
    used = 0
    for hit in hits:
        if used + hit.tokens > max_tokens and chosen:
            break
        chosen.append(hit)
        used += hit.tokens
    return chosen
