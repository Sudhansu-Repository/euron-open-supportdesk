"""Split sections into retrievable chunks of about ``target_tokens``.

Chunks follow sentence boundaries, carry their heading (retrieval matches on it, and the
answer cites it), and overlap by one sentence so an answer that spans a boundary is still
found. FAQ rows stay whole.
"""

from __future__ import annotations

from dataclasses import dataclass

from supportdesk.ai.providers.base import estimate_tokens
from supportdesk.ai.text import sentences
from supportdesk.knowledge.parsing import Document

TARGET_TOKENS = 220
MAX_TOKENS = 400
MAX_CHUNKS = 20_000


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    title: str
    heading: str | None
    text: str
    tokens: int
    anchor: str | None


def _split_long(sentence: str) -> list[str]:
    """A "sentence" longer than the hard limit (a table row dump, a code block) is cut."""
    limit = MAX_TOKENS * 4
    return [sentence[i : i + limit] for i in range(0, len(sentence), limit)]


def chunk_document(doc: Document, target_tokens: int = TARGET_TOKENS) -> list[ChunkDraft]:
    out: list[ChunkDraft] = []
    for section in doc.sections:
        if section.atomic:
            out.append(
                ChunkDraft(
                    len(out),
                    doc.title,
                    section.heading,
                    section.text,
                    estimate_tokens(section.text),
                    section.anchor,
                )
            )
            continue
        parts: list[str] = []
        for s in sentences(section.text):
            parts.extend(_split_long(s) if estimate_tokens(s) > MAX_TOKENS else [s])
        current: list[str] = []
        size = 0
        for part in parts:
            cost = estimate_tokens(part)
            if current and size + cost > target_tokens:
                text = " ".join(current)
                out.append(
                    ChunkDraft(
                        len(out),
                        doc.title,
                        section.heading,
                        text,
                        estimate_tokens(text),
                        section.anchor,
                    )
                )
                overlap = current[-1] if estimate_tokens(current[-1]) < target_tokens // 3 else None
                current, size = ([overlap], estimate_tokens(overlap)) if overlap else ([], 0)
            current.append(part)
            size += cost
        if current:
            text = " ".join(current)
            out.append(
                ChunkDraft(
                    len(out),
                    doc.title,
                    section.heading,
                    text,
                    estimate_tokens(text),
                    section.anchor,
                )
            )
        if len(out) > MAX_CHUNKS:
            break
    return out[:MAX_CHUNKS]


def embedding_text(title: str, heading: str | None, text: str) -> str:
    """What gets embedded: the heading path gives a short passage its topic."""
    head = f"{title} > {heading}" if heading and heading != title else title
    return f"{head}\n{text}"
