# ADR-0001: No LangChain

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

The brief suggested LangChain for the AI layer. The product's value is in decisions that
must be visible and testable: when to retrieve, which passages count, whether an answer
is grounded, whether it may be sent, what it cost. The whole pipeline (triage, gate,
caches, retrieval, generation, grounding, screening, decision) is a few hundred lines.

## Decision

The AI layer is plain Python in `apps/api/src/supportdesk/ai/`: two Protocols
(`ChatModel`, `Embedder`), one file per provider, and an engine whose steps are ordinary
functions. Prompts are string templates in `ai/prompts.py`. Retrieval is SQL.

## Consequences

**Good**
- Every policy decision is a pure function with unit tests (`tests/unit/ai/`).
- The ledger and the budget wrap every call in one place (`Engine.call`).
- A small dependency tree; no framework upgrades breaking the pipeline.

**Bad / caveats**
- No ready-made loaders, agents or tool calling; each new capability is written here.
- Contributors familiar with LangChain find a different structure.

## Alternatives considered

- **LangChain or LlamaIndex**: fast to prototype, but the chains hide the exact decision
  points this product is built on, and they pull a large, fast-moving dependency tree.
- **A thin wrapper around one SDK**: ties the product to one provider; the Protocols keep
  four providers interchangeable.
