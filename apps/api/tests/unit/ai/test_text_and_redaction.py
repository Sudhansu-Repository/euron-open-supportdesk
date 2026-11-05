"""Text tools, redaction, and the answer grounding checks."""

from __future__ import annotations

import uuid

import pytest

from supportdesk.ai.answer import extractive, validate
from supportdesk.ai.engine import smalltalk_reply
from supportdesk.ai.providers.base import estimate_tokens, normalize
from supportdesk.ai.providers.hash_embed import HashEmbedder
from supportdesk.ai.redact import redact
from supportdesk.ai.text import (
    content_words,
    coverage,
    normalize_question,
    question_hash,
    sentences,
    stem,
    truncate_tokens,
    words,
)
from supportdesk.knowledge.retrieval import Hit


def hit(text: str, relevance: float = 0.9, title: str = "FAQ", heading: str | None = None) -> Hit:
    return Hit(
        uuid.uuid4(),
        None,
        None,
        title,
        heading,
        None,
        text,
        50,
        relevance,
        relevance,
        relevance,
        0.1,
    )


@pytest.mark.parametrize(
    ("word", "stemmed"),
    [
        ("refunds", "refund"),
        ("shipping", "ship"),
        ("cancelled", "cancel"),
        ("address", "address"),
        ("integration", "integrate"),
        ("bus", "bus"),
    ],
)
def test_stem(word: str, stemmed: str) -> None:
    assert stem(word) == stemmed


def test_words_keep_indic_vowel_signs_whole() -> None:
    assert words("मेरा ऑर्डर") == ["मेरा", "ऑर्डर"]


def test_question_normalisation_ignores_case_punctuation_and_stopwords() -> None:
    assert normalize_question("How do I reset my password?") == normalize_question(
        "how to reset password"
    )
    assert question_hash("Reset password!") == question_hash("reset   PASSWORD")


def test_coverage_and_sentences() -> None:
    assert coverage("reset password", "To reset your password, open settings.") == 1.0
    assert coverage("", "x") == 0.0
    assert sentences("One. Two! Three?\n\n- four") == ["One.", "Two!", "Three?", "- four"]
    assert content_words("Hi, can you help me?") == ["help"]


def test_truncate_tokens_cuts_at_a_word() -> None:
    text = "word " * 1000
    out = truncate_tokens(text, 10)
    assert out.endswith(" ...") and len(out) <= 48


def test_estimate_and_normalize() -> None:
    assert estimate_tokens("") == 0 and estimate_tokens("a" * 35) == 10
    assert abs(sum(v * v for v in normalize([3.0, 4.0])) - 1) < 1e-9


def test_redaction_removes_cards_and_secrets_only() -> None:
    text = (
        "My card is 4242 4242 4242 4242, order 1234567890123, key sk-abcdefghijklmnopqrstuv, "
        "password: hunter2 and AKIAIOSFODNN7EXAMPLE"
    )
    out, n = redact(text)
    assert "4242" not in out and "hunter2" not in out and "sk-abc" not in out and "AKIA" not in out
    assert "1234567890123" in out  # fails the Luhn check: an order number, not a card
    assert n == 4


@pytest.mark.parametrize("text", ["hi", "Hello!", "thanks a lot", "ok thanks", "namaste"])
def test_smalltalk_gets_a_friendly_line(text: str) -> None:
    assert smalltalk_reply(text, "Acme")


@pytest.mark.parametrize(
    "text", ["hi, how do I reset my password?", "thanks but my bulb is broken", "refund please"]
)
def test_real_questions_are_not_smalltalk(text: str) -> None:
    assert smalltalk_reply(text, "Acme") is None


def test_validate_accepts_a_cited_passing_source() -> None:
    hits = [hit("Shipping takes 3 to 5 days."), hit("Returns within 30 days.", 0.2)]
    answer = validate("Shipping takes 3 to 5 days [1].", hits, 0.5)
    assert (
        answer.grounded
        and answer.text == "Shipping takes 3 to 5 days."
        and answer.cited == [hits[0]]
    )


def test_validate_refuses_no_answer_low_relevance_and_bad_citations() -> None:
    hits = [hit("Shipping takes 3 to 5 days.", 0.3)]
    assert not validate("NO_ANSWER", hits, 0.5).grounded
    assert not validate(
        "Shipping takes 3 to 5 days [1].", hits, 0.5
    ).grounded  # cites a weak passage
    assert not validate("We ship by drone [7].", [hit("Shipping takes 3 days.")], 0.5).grounded


def test_validate_grounds_an_uncited_answer_by_overlap_only() -> None:
    hits = [hit("Standard shipping takes 3 to 5 business days.")]
    assert validate("Standard shipping takes 3 to 5 business days.", hits, 0.5).grounded
    assert not validate("Our premium plan includes a free pony.", hits, 0.5).grounded


def test_extractive_returns_the_faq_answer_or_best_sentences() -> None:
    faq = hit("Q: How long is shipping?\nA: Three to five days.")
    assert extractive("how long is shipping", [faq], 0.5).text == "Three to five days."
    prose = hit(
        "Our office is in Pune. Shipping takes three days. Returns are free. We love lamps. Call us anytime."
    )
    assert (
        "Shipping takes three days." in extractive("how long does shipping take", [prose], 0.5).text
    )
    assert not extractive("anything", [hit("x", 0.1)], 0.5).grounded


async def test_hash_embedder_is_deterministic_and_lexical() -> None:
    e = HashEmbedder()
    a, b, c = await e.embed(["reset my password", "password reset", "shipping times"])
    assert a == (await e.embed(["reset my password"]))[0]
    sim = sum(x * y for x, y in zip(a, b, strict=True))
    unrelated = sum(x * y for x, y in zip(a, c, strict=True))
    assert sim > 0.5 > unrelated


def test_entities_tell_apart_questions_that_embed_alike() -> None:
    from supportdesk.ai.text import entities

    assert entities("What does plan B cost?") == {"b"}
    assert entities("What does plan A cost?") != entities("What does plan B cost?")
    assert entities("Where is order 4512?") == {"4512"}
    assert entities("Do you offer GarminX WearX?") == {"garminx", "wearx"}
    assert entities("How long does shipping take?") == entities("how long is shipping")  # no names
    assert entities("Hi, I need help. Thanks") == frozenset()
