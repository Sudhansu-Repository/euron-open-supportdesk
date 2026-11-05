# ADR-0008: Whether an AI answer is sent is decided by code, never by the model

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

Support conversations include refunds, cancellations, account changes and legal
questions. A model can be talked into anything by a customer message or a poisoned
document; asking it "should this be escalated?" makes the safety decision injectable.

## Decision

`ai/policy.py` holds the decision as pure functions over plain values: a gate before
retrieval (hand over, prepare for a person, or proceed) and a finalize step after
generation (send, approval, draft or escalate). Inputs are deterministic: rule-based
triage (merged with model triage only in the cautious direction), retrieval scores,
whether the answer cites a passage above the threshold, the organisation's policy, VIP
flags, budgets. The answer text itself is screened by the same rules before it can be
sent. The model has no tools.

## Consequences

**Good**
- Prompt injection cannot approve a refund
  (`test_a_customer_cannot_talk_the_ai_out_of_flagging_a_refund`,
  `test_instructions_in_a_document_cannot_get_a_refund_promise_sent`).
- Every rule is unit tested and every decision is stored with reason codes.

**Bad / caveats**
- Rules miss phrasings the model would catch; the merge lets the model add caution, never
  remove it, so misses err towards handing over.
- Rule lists are English-centric in 0.1.0; organisations add custom keywords.

## Alternatives considered

- **Letting the model classify and decide** (common in AI agents): simpler, but the
  decision becomes as attackable as the prompt.
- **A second "guard" model**: another injectable model and another cost per message.
