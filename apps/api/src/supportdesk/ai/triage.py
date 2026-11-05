"""Triage: what the customer wants, how urgent it is and how they feel.

Two layers. Deterministic rules run on every message (zero tokens, no provider needed);
when an LLM is configured and LLM triage is on, its reading is merged in. The merge only
ever makes the outcome more cautious: the model may add a sensitive intent, raise the
priority or detect frustration, but it can never remove what the rules found. So a message
crafted to talk the model out of flagging a refund still gets flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from supportdesk.ai.text import content_words, words

PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "urgent": 3}
SENTIMENT_RANK = {"positive": 0, "neutral": 1, "negative": 2}

# Phrases, matched on word boundaries after lower-casing. Stems keep variants together.
_INTENT_PATTERNS: dict[str, list[str]] = {
    "refund": [r"refund", r"money back", r"reimburs", r"charge ?back", r"return (?:my|the) money"],
    "cancellation": [
        r"cancel(?:l?ed|l?ing|lation)?\b.*\b(?:subscription|plan|account|order|membership)",
        r"(?:subscription|plan|membership)\b.*\bcancel",
        r"unsubscribe from (?:the )?(?:plan|service)",
        r"close my account",
    ],
    "account_change": [
        r"change (?:my |the )?(?:email|e-mail|owner|ownership|username|phone number)",
        r"transfer (?:my |the )?(?:account|ownership)",
        r"(?:remove|add) (?:an? )?(?:admin|owner)",
        r"disable (?:2fa|two.factor)",
    ],
    "billing_dispute": [
        r"(?:double|twice|wrong(?:ly)?|over) ?charged",
        r"charged (?:me |us )?(?:twice|two times|again)",
        r"unauthori[sz]ed (?:charge|payment|transaction)",
        r"dispute",
    ],
    "legal": [r"lawyer", r"attorney", r"legal action", r"sue\b", r"lawsuit", r"court", r"subpoena"],
    "security": [
        r"hack(?:ed|er)?\b",
        r"breach",
        r"compromised",
        r"phishing",
        r"someone (?:logged|got) into my account",
        r"vulnerabilit",
    ],
    "data_deletion": [
        r"delete (?:all )?my (?:data|account|information|personal)",
        r"right to be forgotten",
        r"gdpr",
        r"erase my",
    ],
}
_HUMAN = [
    r"\b(?:talk|speak|chat) (?:to|with) (?:a |an |some(?:one|body) )?"
    r"(?:human|person|agent|representative|someone|somebody|real)",
    r"\b(?:real|live|actual) (?:person|human|agent)",
    r"\bhuman (?:agent|support|please)",
    r"\bcustomer (?:service|support) (?:agent|rep)",
    r"\bnot a (?:bot|robot)",
    r"\b(?:agent|human|operator|representative) please\b",
    r"^\s*(?:human|agent|operator|representative)\s*[.!?]*\s*$",
]
_NEGATIVE = {
    "angry",
    "annoy",
    "annoyed",
    "awful",
    "terrible",
    "horrible",
    "worst",
    "useless",
    "ridiculous",
    "unacceptable",
    "disappoint",
    "disappointed",
    "frustrat",
    "frustrated",
    "furious",
    "pathetic",
    "scam",
    "fraud",
    "rubbish",
    "garbage",
    "hate",
    "sick",
    "fed",
    "nightmare",
    "incompetent",
    "joke",
    "outrage",
    "outraged",
    "broken",
    "never",
    "upset",
    "mad",
    "disgust",
    "disgusted",
    "waste",
    "shame",
    "lousy",
}
_POSITIVE = {
    "thank",
    "thanks",
    "great",
    "awesome",
    "love",
    "perfect",
    "excellent",
    "amazing",
    "helpful",
    "appreciate",
    "wonderful",
    "fantastic",
    "brilliant",
    "solved",
    "works",
}
_URGENT = [
    r"\burgent",
    r"\basap\b",
    r"\bimmediately\b",
    r"\bemergency\b",
    r"\bright now\b",
    r"production (?:is )?down",
    r"\boutage\b",
    r"can'?t (?:log ?in|access|sign in)",
]
_HIGH = [
    r"\bnot working\b",
    r"\bbroken\b",
    r"\berror\b",
    r"\bfail(?:ed|s|ing)?\b",
    r"\bcrash",
    r"\bstuck\b",
    r"\bblocked\b",
    r"\bcan'?t\b",
]

_CATEGORY_WORDS: dict[str, list[str]] = {
    "billing": [
        "invoice",
        "bill",
        "billing",
        "charge",
        "payment",
        "pay",
        "price",
        "pricing",
        "plan",
        "subscription",
        "refund",
        "receipt",
        "card",
        "vat",
        "tax",
        "discount",
        "coupon",
        "upgrade",
        "downgrade",
        "trial",
    ],
    "technical": [
        "error",
        "bug",
        "crash",
        "api",
        "integration",
        "install",
        "setup",
        "configure",
        "webhook",
        "sdk",
        "slow",
        "load",
        "broken",
        "work",
        "sync",
        "export",
        "import",
        "browser",
        "app",
        "feature",
        "upload",
        "download",
        "connect",
    ],
    "account": [
        "account",
        "login",
        "log",
        "sign",
        "password",
        "reset",
        "email",
        "profile",
        "username",
        "2fa",
        "verify",
        "verification",
        "locked",
        "access",
        "team",
        "invite",
        "member",
        "delete",
        "owner",
    ],
    "shipping": [
        "ship",
        "shipping",
        "delivery",
        "deliver",
        "track",
        "tracking",
        "order",
        "package",
        "parcel",
        "courier",
        "address",
        "return",
        "exchange",
        "arrive",
        "late",
        "dispatch",
    ],
}


@dataclass(frozen=True)
class Triage:
    intent: str = "question"
    sensitive: tuple[str, ...] = ()
    category: str = "general"
    priority: str = "normal"
    sentiment: str = "neutral"
    wants_human: bool = False
    language: str = "en"
    source: str = "rules"
    signals: dict[str, Any] = field(default_factory=dict)


def _matches(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def detect_language(text: str) -> str:
    """Coarse script detection: enough to route and to tell the model which language to
    answer in. Latin-script languages are reported as ``en`` unless the model says better."""
    counts: dict[str, int] = {}
    for ch in text:
        o = ord(ch)
        script = (
            "hi"
            if 0x0900 <= o <= 0x097F
            else "bn"
            if 0x0980 <= o <= 0x09FF
            else "ta"
            if 0x0B80 <= o <= 0x0BFF
            else "te"
            if 0x0C00 <= o <= 0x0C7F
            else "ar"
            if 0x0600 <= o <= 0x06FF
            else "zh"
            if 0x4E00 <= o <= 0x9FFF
            else "ja"
            if 0x3040 <= o <= 0x30FF
            else "ko"
            if 0xAC00 <= o <= 0xD7AF
            else "ru"
            if 0x0400 <= o <= 0x04FF
            else None
        )
        if script:
            counts[script] = counts.get(script, 0) + 1
    if counts:
        script, n = max(counts.items(), key=lambda kv: kv[1])
        if n >= 3:
            return script
    return "en"


def rule_triage(text: str, categories: list[str], custom_sensitive: list[str]) -> Triage:
    lowered = " ".join(text.lower().split())
    sensitive = [intent for intent, pats in _INTENT_PATTERNS.items() if _matches(pats, lowered)]
    custom_hits = [k for k in custom_sensitive if re.search(r"\b" + re.escape(k) + r"\b", lowered)]
    if custom_hits:
        sensitive.append("custom")
    wants_human = _matches(_HUMAN, lowered)

    raw = words(text)
    stems = set(content_words(text))
    negative = sum(
        1
        for w in raw
        if w in _NEGATIVE
        or any(w.startswith(n) for n in ("frustrat", "disappoint", "outrag", "disgust"))
    )
    positive = sum(1 for w in raw if w in _POSITIVE)
    shouting = sum(1 for w in text.split() if len(w) >= 4 and w.isupper() and w.isalpha())
    exclaim = text.count("!")
    score = negative * 2 + (2 if shouting >= 2 else 0) + (1 if exclaim >= 3 else 0) - positive * 2
    sentiment = "negative" if score >= 2 else "positive" if positive and score <= -2 else "neutral"

    priority = "normal"
    if _matches(_URGENT, lowered):
        priority = "urgent"
    elif _matches(_HIGH, lowered) or sentiment == "negative":
        priority = "high"
    if sensitive and PRIORITY_RANK[priority] < PRIORITY_RANK["high"]:
        priority = "high"

    best, best_score = "general", 0
    for cat in categories:
        vocab = _CATEGORY_WORDS.get(cat, [cat])
        hits = sum(1 for v in vocab if v in stems or v in raw)
        if hits > best_score:
            best, best_score = cat, hits
    if best not in categories:
        best = "general" if "general" in categories else categories[0]
    intent = sensitive[0] if sensitive else ("human" if wants_human else "question")
    return Triage(
        intent=intent,
        sensitive=tuple(dict.fromkeys(sensitive)),
        category=best,
        priority=priority,
        sentiment=sentiment,
        wants_human=wants_human,
        language=detect_language(text),
        source="rules",
        signals={"negative_words": negative, "positive_words": positive, "custom": custom_hits},
    )


def merge(
    rules: Triage,
    model: dict[str, Any],
    categories: list[str],
    known_intents: list[str],
    auto_categories: list[str] | None = None,
) -> Triage:
    """Combine the rules with a model's reading. The model can add caution, never remove it."""
    sensitive = list(rules.sensitive)
    for intent in model.get("sensitive_intents") or []:
        if isinstance(intent, str) and intent in known_intents and intent not in sensitive:
            sensitive.append(intent)
    priority = rules.priority
    mp = model.get("priority")
    if isinstance(mp, str) and PRIORITY_RANK.get(mp, -1) > PRIORITY_RANK[priority]:
        priority = mp
    sentiment = rules.sentiment
    ms = model.get("sentiment")
    if isinstance(ms, str) and SENTIMENT_RANK.get(ms, -1) > SENTIMENT_RANK[sentiment]:
        sentiment = ms
    if ms == "positive" and rules.sentiment == "neutral":
        sentiment = "positive"
    category = rules.category
    mc = model.get("category")
    # The model may refine the category, but never move a message the rules sent to a
    # person into a category the AI may resolve alone (that would remove caution, and a
    # customer can ask the model to "classify this as general").
    if (
        isinstance(mc, str)
        and mc in categories
        and (
            auto_categories is None
            or rules.category in auto_categories
            or mc not in auto_categories
        )
    ):
        category = mc
    language = rules.language
    ml = model.get("language")
    if isinstance(ml, str) and re.fullmatch(r"[a-z]{2}", ml):
        language = ml if rules.language == "en" else rules.language
    wants_human = rules.wants_human or bool(model.get("wants_human"))
    intent = sensitive[0] if sensitive else ("human" if wants_human else rules.intent)
    return replace(
        rules,
        intent=intent,
        sensitive=tuple(sensitive),
        priority=priority,
        sentiment=sentiment,
        category=category,
        wants_human=wants_human,
        language=language,
        source="rules+model",
    )
