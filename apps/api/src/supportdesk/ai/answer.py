"""Turning retrieved passages into an answer, and deciding whether it is grounded.

Grounded means: the answer cites at least one retrieved passage that reached the policy's
relevance threshold. A model that forgets its citation markers is checked by overlap
instead (most of the answer's content words must appear in one passing passage). A model
that answers ``NO_ANSWER``, or whose text cannot be traced to a passing passage, has not
answered, whatever it wrote.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from supportdesk.ai.prompts import NO_ANSWER
from supportdesk.ai.text import content_words, coverage, sentences
from supportdesk.knowledge.retrieval import Hit

_MARKER = re.compile(r"\s?\[(\d{1,2})\]")
_FAQ = re.compile(r"^Q:\s*(?P<q>.+?)\nA:\s*(?P<a>.+)$", re.S)
OVERLAP_GROUNDING = 0.5


@dataclass(frozen=True)
class Answer:
    text: str
    grounded: bool
    cited: list[Hit] = field(default_factory=list)
    method: str = "model"  # model, extractive, cache


def extractive(question: str, hits: list[Hit], threshold: float) -> Answer:
    """The zero-model answer: the passage that best answers the question, quoted.

    For an FAQ row the answer half is returned as written. For prose, the two or three
    sentences of the best passage that cover the question best, in their original order.
    """
    passing = [h for h in hits if h.relevance >= threshold]
    if not passing:
        return Answer("", grounded=False, method="extractive")
    best = passing[0]
    faq = _FAQ.match(best.text.strip())
    if faq:
        return Answer(faq.group("a").strip(), grounded=True, cited=[best], method="extractive")
    parts = sentences(best.text)
    if len(parts) <= 3:
        return Answer(best.text.strip(), grounded=True, cited=[best], method="extractive")
    scored = sorted(range(len(parts)), key=lambda i: coverage(question, parts[i]), reverse=True)
    keep = sorted(scored[:3])
    # Include the sentence after the best one: steps and conditions usually follow it.
    if scored and scored[0] + 1 < len(parts) and scored[0] + 1 not in keep:
        keep = sorted([*keep[:2], scored[0] + 1])
    text = " ".join(parts[i] for i in keep)
    return Answer(text, grounded=True, cited=[best], method="extractive")


def validate(raw: str, hits: list[Hit], threshold: float) -> Answer:
    """Check a model's answer against the passages it was given (numbered from 1)."""
    text = raw.strip()
    if not text or text.upper().startswith(NO_ANSWER) or NO_ANSWER in text.upper()[:40]:
        return Answer("", grounded=False)
    numbers = [int(n) for n in _MARKER.findall(text)]
    cited = [hits[n - 1] for n in dict.fromkeys(numbers) if 1 <= n <= len(hits)]
    clean = _MARKER.sub("", text).strip()
    passing_cited = [h for h in cited if h.relevance >= threshold]
    if passing_cited:
        return Answer(clean, grounded=True, cited=passing_cited)
    if not numbers:
        answer_words = content_words(clean)
        best: Hit | None = None
        best_share = 0.0
        for hit in hits:
            if hit.relevance < threshold or not answer_words:
                continue
            present = set(content_words(f"{hit.title} {hit.heading or ''} {hit.text}"))
            share = sum(1 for w in answer_words if w in present) / len(answer_words)
            if share > best_share:
                best, best_share = hit, share
        if best is not None and best_share >= OVERLAP_GROUNDING:
            return Answer(clean, grounded=True, cited=[best])
    return Answer(clean, grounded=False, cited=cited)
