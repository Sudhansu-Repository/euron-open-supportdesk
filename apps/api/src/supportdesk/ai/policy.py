"""The escalation engine: whether the AI may answer, and what happens to its answer.

Pure functions over plain values, so every rule is unit tested and none of them asks the
model. Two checkpoints:

* :func:`gate` before retrieval: reasons to hand over at once (the customer asked for a
  person, AI is off, too many AI turns, the last answers did not help) and reasons the AI
  may only *prepare* an answer for a person (sensitive intent, VIP, frustration, a
  category it may not resolve);
* :func:`finalize` after generation: a grounded answer is sent, held for approval or kept
  as a draft; anything not grounded becomes an honest handoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from supportdesk.ai.triage import Triage
from supportdesk.org.schemas import Policy

Action = Literal["send", "approval", "draft", "escalate"]

# Reason codes, stored on the conversation and shown to agents and in analytics.
CUSTOMER_REQUESTED = "customer_requested"
SENSITIVE = "sensitive_intent"
NEGATIVE = "negative_sentiment"
VIP = "vip_customer"
CATEGORY = "category_not_allowed"
NO_ANSWER = "no_grounded_answer"
UNHELPFUL = "answer_unhelpful"
TURNS = "max_ai_turns"
AI_OFF = "ai_off"
AI_UNAVAILABLE = "ai_unavailable"
BUDGET = "budget_exhausted"
# The answer itself raised a sensitive topic the customer did not (see engine.py).
SENSITIVE_ANSWER = "sensitive_answer"

REASON_LABELS = {
    CUSTOMER_REQUESTED: "Customer asked for a person",
    SENSITIVE: "Sensitive request",
    NEGATIVE: "Customer is frustrated",
    VIP: "VIP customer",
    CATEGORY: "Category needs a person",
    NO_ANSWER: "Not covered by the knowledge base",
    UNHELPFUL: "AI answer did not help",
    TURNS: "Long AI conversation",
    AI_OFF: "AI is off",
    AI_UNAVAILABLE: "AI provider unavailable",
    BUDGET: "AI budget spent",
    SENSITIVE_ANSWER: "Answer needs a person to check",
}


@dataclass(frozen=True)
class Context:
    policy: Policy
    triage: Triage
    vip: bool = False
    inbox_ai_enabled: bool = True
    ai_turns: int = 0
    unhelpful: int = 0
    budget_exhausted: bool = False
    on_exhausted: Literal["extractive", "human"] = "extractive"


@dataclass(frozen=True)
class Gate:
    # proceed: retrieve and answer. prepare: answer as a draft or for approval, for a person.
    # handover: no AI answer at all.
    route: Literal["proceed", "prepare", "handover"]
    reasons: tuple[str, ...] = ()
    # When the model budget is spent but extractive answers are allowed.
    extractive_only: bool = False
    # For "prepare": hold for approval (approval mode, sensitive) instead of a draft.
    hold_for_approval: bool = False


def gate(ctx: Context) -> Gate:
    p, t = ctx.policy, ctx.triage
    if p.mode == "off" or not ctx.inbox_ai_enabled:
        return Gate("handover", (AI_OFF,))
    if t.wants_human:
        return Gate("handover", (CUSTOMER_REQUESTED,))
    if p.max_unhelpful and ctx.unhelpful >= p.max_unhelpful:
        return Gate("handover", (UNHELPFUL,))
    if ctx.ai_turns >= p.max_ai_turns:
        return Gate("handover", (TURNS,))
    extractive_only = False
    if ctx.budget_exhausted:
        if ctx.on_exhausted == "human":
            return Gate("handover", (BUDGET,))
        extractive_only = True

    reasons: list[str] = []
    sensitive = [s for s in t.sensitive if s in p.sensitive_intents or s == "custom"]
    if sensitive:
        reasons.append(SENSITIVE)
    if p.escalate_vip and ctx.vip:
        reasons.append(VIP)
    if p.escalate_negative_sentiment and t.sentiment == "negative":
        reasons.append(NEGATIVE)
    if t.category not in p.auto_categories:
        reasons.append(CATEGORY)

    if p.mode == "draft":
        return Gate("prepare", tuple(reasons), extractive_only)
    if reasons:
        # Only a sensitive intent in approval mode may wait for approval; every other
        # reason (and sensitive in auto mode) goes to a person with a draft.
        hold = p.mode == "approval" and reasons == [SENSITIVE]
        return Gate("prepare", tuple(reasons), extractive_only, hold_for_approval=hold)
    return Gate("proceed", (), extractive_only)


@dataclass(frozen=True)
class Outcome:
    action: Action
    reasons: tuple[str, ...]


def finalize(g: Gate, grounded: bool) -> Outcome:
    """What to do with a generated answer. Ungrounded answers are never shown to the
    customer; a draft is still useful to the agent only if it is grounded."""
    if g.route == "handover":
        return Outcome("escalate", g.reasons)
    if not grounded:
        return Outcome("escalate", (*g.reasons, NO_ANSWER))
    if g.route == "prepare":
        if g.hold_for_approval:
            return Outcome("approval", g.reasons)
        return Outcome("draft", g.reasons)
    return Outcome("send", ())
