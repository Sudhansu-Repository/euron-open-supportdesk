"""Rule triage, and the merge that only adds caution."""

from __future__ import annotations

import pytest

from supportdesk.ai.triage import detect_language, merge, rule_triage

CATS = ["billing", "technical", "account", "shipping", "general"]


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("I want my money back for this order", "refund"),
        ("Please cancel my subscription today", "cancellation"),
        ("I need to change my email address on the account", "account_change"),
        ("You charged me twice this month", "billing_dispute"),
        ("My lawyer will be in touch", "legal"),
        ("I think my account was hacked", "security"),
        ("Delete my data under GDPR", "data_deletion"),
    ],
)
def test_sensitive_intents(text: str, intent: str) -> None:
    t = rule_triage(text, CATS, [])
    assert intent in t.sensitive and t.priority in ("high", "urgent")


@pytest.mark.parametrize(
    "text",
    ["Can I talk to a real person?", "human please", "agent", "I want to speak with someone"],
)
def test_wants_human(text: str) -> None:
    assert rule_triage(text, CATS, []).wants_human


def test_neutral_question_is_not_sensitive_and_gets_a_category() -> None:
    t = rule_triage("How long does shipping take for my order?", CATS, [])
    assert (
        t.sensitive == ()
        and t.category == "shipping"
        and t.sentiment == "neutral"
        and t.priority == "normal"
    )


def test_frustration_raises_sentiment_and_priority() -> None:
    t = rule_triage("This is ridiculous and USELESS, WORST APP EVER!!!", CATS, [])
    assert t.sentiment == "negative" and t.priority == "high"


def test_urgency() -> None:
    assert rule_triage("URGENT: production is down, can't log in", CATS, []).priority == "urgent"


def test_custom_keywords() -> None:
    assert (
        "custom"
        in rule_triage(
            "I want to talk about the chargeback form", CATS, ["chargeback form"]
        ).sensitive
    )


def test_merge_only_adds_caution() -> None:
    rules = rule_triage("I want a refund", CATS, [])
    calm = merge(
        rules,
        {
            "sensitive_intents": [],
            "priority": "low",
            "sentiment": "positive",
            "category": "billing",
        },
        CATS,
        ["refund", "legal"],
    )
    assert "refund" in calm.sensitive and calm.priority == "high"
    worried = merge(
        rule_triage("hello", CATS, []),
        {
            "sensitive_intents": ["legal", "made-up"],
            "priority": "urgent",
            "sentiment": "negative",
            "wants_human": True,
        },
        CATS,
        ["refund", "legal"],
    )
    assert worried.sensitive == ("legal",) and worried.priority == "urgent" and worried.wants_human


def test_merge_ignores_unknown_categories() -> None:
    t = merge(rule_triage("my invoice is wrong", CATS, []), {"category": "space-travel"}, CATS, [])
    assert t.category == "billing"


@pytest.mark.parametrize(
    ("text", "lang"),
    [("नमस्ते, मेरा ऑर्डर कहाँ है?", "hi"), ("Hello there", "en"), ("Здравствуйте, где мой заказ", "ru")],
)
def test_language(text: str, lang: str) -> None:
    assert detect_language(text) == lang


def test_the_model_cannot_move_a_message_into_an_auto_resolved_category() -> None:
    rules = rule_triage("What are the payment terms on my invoice and billing statement?", CATS, [])
    assert rules.category == "billing"
    auto = ["technical", "general"]  # billing needs a person
    steered = merge(rules, {"category": "general"}, CATS, [], auto)
    assert steered.category == "billing"
    allowed = merge(
        rule_triage("my app crashes on start", CATS, []), {"category": "general"}, CATS, [], auto
    )
    assert allowed.category == "general"  # refining between auto categories is fine
