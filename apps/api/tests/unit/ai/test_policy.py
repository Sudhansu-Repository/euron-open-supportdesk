"""The escalation engine: every rule, decided without the model."""

from __future__ import annotations

import pytest

from supportdesk.ai import policy
from supportdesk.ai.triage import Triage
from supportdesk.org.schemas import Policy

CLEAN = Triage(category="technical")


def ctx(triage: Triage = CLEAN, **kw: object) -> policy.Context:
    return policy.Context(policy=kw.pop("policy", Policy()), triage=triage, **kw)  # type: ignore[arg-type]


def test_a_clean_question_proceeds_and_a_grounded_answer_is_sent() -> None:
    gate = policy.gate(ctx())
    assert gate.route == "proceed" and gate.reasons == ()
    assert policy.finalize(gate, grounded=True) == policy.Outcome("send", ())


def test_an_ungrounded_answer_always_escalates() -> None:
    assert policy.finalize(policy.gate(ctx()), grounded=False) == policy.Outcome(
        "escalate", (policy.NO_ANSWER,)
    )


@pytest.mark.parametrize(
    ("context", "reason"),
    [
        (ctx(policy=Policy(mode="off")), policy.AI_OFF),
        (ctx(inbox_ai_enabled=False), policy.AI_OFF),
        (ctx(Triage(category="technical", wants_human=True)), policy.CUSTOMER_REQUESTED),
        (ctx(unhelpful=1), policy.UNHELPFUL),
        (ctx(ai_turns=6), policy.TURNS),
        (ctx(budget_exhausted=True, on_exhausted="human"), policy.BUDGET),
    ],
)
def test_handover_rules(context: policy.Context, reason: str) -> None:
    gate = policy.gate(context)
    assert gate.route == "handover" and gate.reasons == (reason,)
    assert policy.finalize(gate, grounded=True).action == "escalate"


def test_sensitive_intent_waits_for_approval_in_approval_mode() -> None:
    gate = policy.gate(ctx(Triage(category="billing", sensitive=("refund",))))
    assert gate.route == "prepare" and gate.hold_for_approval
    assert policy.finalize(gate, True) == policy.Outcome("approval", (policy.SENSITIVE,))


def test_sensitive_intent_is_drafted_for_a_person_in_auto_mode() -> None:
    gate = policy.gate(
        ctx(Triage(category="billing", sensitive=("refund",)), policy=Policy(mode="auto"))
    )
    assert policy.finalize(gate, True).action == "draft"


@pytest.mark.parametrize(
    ("context", "reason"),
    [
        (ctx(vip=True), policy.VIP),
        (ctx(Triage(category="technical", sentiment="negative")), policy.NEGATIVE),
        (ctx(Triage(category="legal-stuff")), policy.CATEGORY),
    ],
)
def test_prepare_rules_draft_for_a_person(context: policy.Context, reason: str) -> None:
    gate = policy.gate(context)
    assert gate.route == "prepare" and reason in gate.reasons and not gate.hold_for_approval
    assert policy.finalize(gate, True).action == "draft"


def test_rules_can_be_switched_off() -> None:
    relaxed = Policy(escalate_vip=False, escalate_negative_sentiment=False)
    assert (
        policy.gate(
            ctx(Triage(category="technical", sentiment="negative"), vip=True, policy=relaxed)
        ).route
        == "proceed"
    )


def test_draft_mode_prepares_everything() -> None:
    gate = policy.gate(ctx(policy=Policy(mode="draft")))
    assert gate.route == "prepare" and policy.finalize(gate, True).action == "draft"


def test_exhausted_budget_with_extractive_fallback_still_answers() -> None:
    gate = policy.gate(ctx(budget_exhausted=True, on_exhausted="extractive"))
    assert gate.route == "proceed" and gate.extractive_only


def test_unknown_custom_keyword_counts_as_sensitive() -> None:
    gate = policy.gate(ctx(Triage(category="technical", sensitive=("custom",))))
    assert policy.SENSITIVE in gate.reasons


def test_every_reason_has_a_label() -> None:
    reasons = [
        v
        for k, v in vars(policy).items()
        if k.isupper() and isinstance(v, str) and k not in ("SENSITIVE",)
    ]
    assert all(r in policy.REASON_LABELS for r in [*reasons, policy.SENSITIVE])
