"""Small, deterministic text tools shared by triage, retrieval, grounding and caching.

Words are runs of letters, digits and combining marks (Unicode categories L, M, N), so
scripts whose vowels are combining marks (Devanagari, Tamil, Bengali) stay whole; Python's
``\\w`` splits them. English words get a light suffix stemmer, enough for "refunds" to
match "refund" without a dependency.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

STOPWORDS = frozenset(
    [
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "hi",
        "hello",
        "hey",
        "please",
        "thanks",
        "thank",
        "thx",
        "regards",
        "dear",
        "can't",
        "cannot",
        "i'm",
        "i've",
        "i'd",
        "im",
        "ive",
        "id",
        "get",
        "got",
        "want",
        "need",
        "would",
        "like",
        "could",
        "also",
        "still",
        "really",
        "just",
    ]
)

_SENTENCE = re.compile(r"(?<=[.!?।。])\s+|\n{2,}|\n(?=[-*•]\s)")


def _is_word_char(ch: str) -> bool:
    return unicodedata.category(ch)[0] in ("L", "M", "N")


def words(text: str) -> list[str]:
    """Lower-case words, in order."""
    out: list[str] = []
    current: list[str] = []
    for ch in unicodedata.normalize("NFKC", text.lower()):
        if _is_word_char(ch) or (ch == "'" and current):
            current.append(ch)
        elif current:
            out.append("".join(current).strip("'"))
            current = []
    if current:
        out.append("".join(current).strip("'"))
    return [w for w in out if w]


def stem(word: str) -> str:
    """A light English suffix stemmer; other scripts pass through."""
    if not word.isascii() or len(word) <= 3:
        return word
    for suffix, keep in (
        ("ational", "ate"),
        ("ization", "ize"),
        ("ations", "ate"),
        ("ation", "ate"),
        ("iness", "y"),
        ("ments", "ment"),
        ("ies", "y"),
        ("ing", ""),
        ("edly", ""),
        ("ed", ""),
        ("es", ""),
        ("s", ""),
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            base = word[: -len(suffix)] + keep
            if suffix in ("ing", "ed") and len(base) > 3 and base[-1] == base[-2]:
                base = base[:-1]  # "shipping" -> "ship", "cancelled" -> "cancel"
            if suffix == "s" and word.endswith("ss"):
                return word  # "address", "access"
            return base
    return word


def content_words(text: str) -> list[str]:
    """Stemmed words without stopwords or single characters (except digits)."""
    return [stem(w) for w in words(text) if w not in STOPWORDS and (len(w) > 1 or w.isdigit())]


def coverage(question: str, passage: str) -> float:
    """The share of the question's content words found in the passage (0 to 1)."""
    asked = set(content_words(question))
    if not asked:
        return 0.0
    present = set(content_words(passage))
    return len(asked & present) / len(asked)


def sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE.split(text.strip())]
    return [p for p in parts if p]


def normalize_question(text: str) -> str:
    """The canonical form of a question for the exact answer cache: case, punctuation,
    spacing and stopwords do not make "How do I reset my password?" a different question
    from "how to reset password"."""
    return " ".join(content_words(text))


def question_hash(text: str) -> str:
    return hashlib.sha256(normalize_question(text).encode()).hexdigest()


def truncate_tokens(text: str, max_tokens: int) -> str:
    """Cut text to roughly ``max_tokens`` (four characters per token), at a word edge."""
    limit = max_tokens * 4
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.8 else cut).rstrip() + " ..."


_TOKEN = re.compile(r"[^\W_]+(?:[-.][^\W_]+)*", re.UNICODE)
# Capitalised words that are not names (sentence starts are skipped anyway).
_COMMON_CAPS = frozenset({"i", "i'm", "ok", "hi", "hello", "please", "thanks"})


def entities(text: str) -> frozenset[str]:
    """The specific things a question is about: numbers, codes and capitalised names
    ("plan B", "order 4512", "Garmin"). Two questions that embed almost identically but
    name different things must not share a cached answer."""
    found: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        for i, token in enumerate(_TOKEN.findall(sentence)):
            lowered = token.lower()
            if any(ch.isdigit() for ch in token) or (
                i > 0 and token[:1].isupper() and lowered not in _COMMON_CAPS
            ):
                found.add(lowered)
    return frozenset(found)
