"""The AI engine: from a customer question to a decided outcome.

Used by the ``ai.reply`` job (``pipeline.py``) and by the knowledge playground, so what an
admin tests is exactly what customers get. The engine makes model calls and collects
ledger entries, but writes nothing to the conversation; its caller does that in one
fenced transaction.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any

import orjson

from supportdesk.ai import budget, cache, ledger, policy
from supportdesk.ai.answer import Answer, extractive, validate
from supportdesk.ai.ledger import LedgerEntry
from supportdesk.ai.prompts import (
    SUMMARY_SYSTEM,
    answer_messages,
    transcript,
    triage_messages,
)
from supportdesk.ai.providers.base import ChatMessage, ProviderError, estimate_tokens
from supportdesk.ai.redact import redact
from supportdesk.ai.registry import AiRuntime
from supportdesk.ai.text import content_words, truncate_tokens
from supportdesk.ai.triage import Triage, merge, rule_triage
from supportdesk.core.container import Container
from supportdesk.knowledge import retrieval
from supportdesk.org.service import SettingsBundle

SMALLTALK = {
    "hi",
    "hello",
    "hey",
    "hiya",
    "yo",
    "morning",
    "afternoon",
    "evening",
    "good",
    "thanks",
    "thank",
    "thx",
    "ty",
    "cheers",
    "ok",
    "okay",
    "cool",
    "great",
    "bye",
    "goodbye",
    "namaste",
    "hola",
    "bonjour",
    "awesome",
    "perfect",
    "nice",
    "appreciate",
}
FILLER = {"you", "a", "lot", "so", "much", "there", "very", "all", "again", "guys", "team"}
GRATITUDE = {"thanks", "thank", "thx", "ty", "cheers", "appreciate", "great", "awesome", "perfect"}
SENSITIVE_ANSWER = policy.SENSITIVE_ANSWER


@dataclass
class Result:
    action: policy.Action
    reasons: tuple[str, ...]
    triage: Triage
    answer: Answer | None
    retrieval: retrieval.Retrieval | None = None
    question_vector: list[float] | None = None
    cache_hit: cache.CachedAnswer | None = None
    smalltalk: str | None = None
    ledger: list[LedgerEntry] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    provider_error: str | None = None
    # The answer call failed in a way worth retrying (timeout, 429, 5xx).
    retryable: bool = False

    @property
    def tokens(self) -> int:
        return sum(e.input_tokens + e.output_tokens for e in self.ledger)

    @property
    def cost(self) -> Decimal:
        return sum((e.cost_usd for e in self.ledger), Decimal(0))

    def meta(self) -> dict[str, Any]:
        """What the agent's AI panel shows about this decision."""
        return {
            "action": self.action,
            "reasons": list(self.reasons),
            "method": self.answer.method if self.answer else None,
            "grounded": bool(self.answer and self.answer.grounded),
            "triage": {
                "intent": self.triage.intent,
                "category": self.triage.category,
                "sentiment": self.triage.sentiment,
                "priority": self.triage.priority,
                "sensitive": list(self.triage.sensitive),
                "source": self.triage.source,
            },
            "best_relevance": round(self.retrieval.best, 3) if self.retrieval else None,
            "cache": self.cache_hit.kind if self.cache_hit else None,
            "tokens": self.tokens,
            "cost_usd": str(self.cost),
            "timings_ms": {k: round(v, 1) for k, v in self.timings.items()},
            "provider_error": self.provider_error,
        }


@dataclass(frozen=True)
class Turn:
    """What the engine needs to know about the conversation so far."""

    question: str
    history: list[tuple[str, str]]  # (customer|ai|agent, text), oldest first, redacted
    ai_turns: int = 0
    unhelpful: int = 0
    vip: bool = False
    inbox_ai_enabled: bool = True
    first_question: bool = True
    ticket_id: uuid.UUID | None = None


def smalltalk_reply(text: str, company: str) -> str | None:
    """Greetings and thanks get a friendly line, never an escalation or a knowledge gap."""
    ws = [w for w in content_words(text) if w]
    raw = set(text.lower().replace("!", " ").replace(".", " ").split())
    if not raw or len(text) > 60 or not raw <= (SMALLTALK | FILLER):
        return None
    if ws and not set(ws) <= SMALLTALK | FILLER:
        return None
    if raw & GRATITUDE:
        return "You're welcome! Is there anything else I can help you with?"
    return f"Hi! I'm the {company} support assistant. What can I help you with today?"


class Engine:
    def __init__(self, container: Container, bundle: SettingsBundle, runtime: AiRuntime) -> None:
        self.container = container
        self.bundle = bundle
        self.runtime = runtime
        self.org_id = bundle.org.id

    async def call(
        self,
        result: Result,
        purpose: str,
        messages: list[ChatMessage],
        *,
        model: str,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str | None:
        """One model call under the budget. None when the budget refuses it."""
        chat = self.runtime.chat
        assert chat is not None
        estimate_in = sum(estimate_tokens(m.content) for m in messages) + 8 * len(messages)
        async with self.container.db.sessionmaker() as session:
            prices = await ledger.price_of(session, self.org_id, chat.provider, model)
            worst = ledger.cost(prices, estimate_in, max_tokens)
            reservation = await budget.reserve(
                session, self.org_id, self.bundle.budgets, estimate_in + max_tokens, worst
            )
        if reservation is None:
            result.ledger.append(
                LedgerEntry(purpose, chat.provider, model, status="budget_blocked")
            )
            return None
        started = time.perf_counter()
        used_tokens, used_cost = 0, Decimal(0)
        try:
            completion = await chat.complete(
                messages,
                model=model,
                max_tokens=max_tokens,
                temperature=self.runtime.config.temperature,
                json_mode=json_mode,
            )
            input_tokens = completion.input_tokens or estimate_in
            output_tokens = completion.output_tokens or estimate_tokens(completion.text)
            used_tokens = input_tokens + output_tokens
            used_cost = ledger.cost(prices, input_tokens, output_tokens)
            result.ledger.append(
                LedgerEntry(
                    purpose,
                    chat.provider,
                    completion.model or model,
                    input_tokens,
                    output_tokens,
                    used_cost,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            return completion.text
        except ProviderError as exc:
            result.ledger.append(
                LedgerEntry(
                    purpose,
                    chat.provider,
                    model,
                    status="error",
                    error=str(exc),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            raise
        finally:
            async with self.container.db.sessionmaker() as session:
                await budget.settle(session, reservation, used_tokens, used_cost)

    async def triage(self, result: Result, text: str) -> Triage:
        rules = rule_triage(
            text, self.bundle.categories, self.bundle.policy.custom_sensitive_keywords
        )
        cfg = self.runtime.config
        if self.runtime.chat is None or not cfg.llm_triage:
            return rules
        started = time.perf_counter()
        try:
            raw = await self.call(
                result,
                "triage",
                triage_messages(
                    truncate_tokens(text, 1000),
                    self.bundle.categories,
                    self.bundle.policy.sensitive_intents,
                ),
                model=cfg.model_for("triage"),
                max_tokens=120,
                json_mode=True,
            )
        except ProviderError:
            return rules  # triage is best effort: the rules already decided what matters
        finally:
            result.timings["triage"] = (time.perf_counter() - started) * 1000
        if not raw:
            return rules
        try:
            data = orjson.loads(raw[raw.find("{") : raw.rfind("}") + 1] or "{}")
        except orjson.JSONDecodeError:
            return rules
        if not isinstance(data, dict):
            return rules
        return merge(
            rules,
            data,
            self.bundle.categories,
            self.bundle.policy.sensitive_intents,
            self.bundle.policy.auto_categories,
        )

    async def budget_spent(self) -> bool:
        if self.runtime.chat is None:
            return False
        async with self.container.db.sessionmaker() as session:
            return await budget.exhausted(session, self.org_id, self.bundle.budgets)

    async def run(self, turn: Turn) -> Result:
        """Decide and, where allowed, answer. Never raises for a provider failure: the
        result says ``ai_unavailable`` (and whether a retry may help) instead."""
        question, _ = redact(turn.question)
        history = [(role, redact(text)[0]) for role, text in turn.history]
        company = self.bundle.brand.company_name
        empty = Triage(category=self.bundle.categories[0] if self.bundle.categories else "general")
        # Greetings get a friendly line only where the AI may speak at all: off and draft
        # modes, and an inbox with AI switched off, go through the gate like any message.
        may_speak = turn.inbox_ai_enabled and self.bundle.policy.mode not in ("off", "draft")
        small = smalltalk_reply(question, company) if may_speak else None
        if small is not None:
            return Result(
                "send", (), empty, Answer(small, True, method="smalltalk"), smalltalk=small
            )

        result = Result("escalate", (), empty, None)
        result.triage = await self.triage(result, question)
        ctx = policy.Context(
            policy=self.bundle.policy,
            triage=result.triage,
            vip=turn.vip,
            inbox_ai_enabled=turn.inbox_ai_enabled,
            ai_turns=turn.ai_turns,
            unhelpful=turn.unhelpful,
            budget_exhausted=await self.budget_spent(),
            on_exhausted=self.bundle.budgets.on_exhausted,
        )
        gate = policy.gate(ctx)
        if gate.route == "handover":
            result.action, result.reasons = "escalate", gate.reasons
            return result

        saver = self.bundle.token_saver
        kb_version = self.bundle.org.kb_version
        use_cache = turn.first_question and gate.route == "proceed"
        if use_cache and saver.exact_cache:
            async with self.container.db.sessionmaker() as session:
                hit = await cache.lookup_exact(
                    session,
                    self.container.kv,
                    self.org_id,
                    kb_version,
                    question,
                    saver.cache_ttl_hours * 3600,
                )
            if hit is not None:
                return self._from_cache(result, hit)

        started = time.perf_counter()
        embedder = self.runtime.embedder
        try:
            vectors = await embedder.embed([question], kind="query")
            result.question_vector = vectors[0] if vectors else None
        except ProviderError as exc:
            # Full-text search still works without the vector; note it for the panel.
            result.provider_error = f"embedding: {exc}"
        result.timings["embed"] = (time.perf_counter() - started) * 1000

        if use_cache and saver.semantic_cache and result.question_vector is not None:
            async with self.container.db.sessionmaker() as session:
                hit = await cache.lookup_semantic(
                    session,
                    self.org_id,
                    kb_version,
                    result.question_vector,
                    saver.semantic_threshold,
                    saver.cache_ttl_hours * 3600,
                    question,
                )
            if hit is not None:
                return self._from_cache(result, hit)

        async with self.container.db.sessionmaker() as session:
            found = await retrieval.search(
                session,
                self.org_id,
                question,
                result.question_vector,
                embedder.name,
                top_k=self.runtime.config.top_k,
            )
        result.retrieval = found
        result.timings["retrieve"] = found.ms
        threshold = self.bundle.policy.min_relevance
        passing = found.passing(threshold)

        if not passing:
            answer = Answer("", grounded=False)
        elif self.runtime.chat is None or gate.extractive_only:
            answer = extractive(question, found.hits, threshold)
        else:
            context = retrieval.within_budget(passing, self.runtime.config.context_tokens)
            keep = history[-saver.history_turns :]
            earlier = None
            if len(history) > len(keep):
                earlier = truncate_tokens(
                    " ".join(t for r, t in history[: -len(keep)] if r == "customer"), 120
                )
            started = time.perf_counter()
            try:
                raw = await self.call(
                    result,
                    "answer",
                    answer_messages(
                        company, context, keep, question, result.triage.language, earlier
                    ),
                    model=self.runtime.config.model_for("answer"),
                    max_tokens=self.runtime.config.max_answer_tokens,
                )
            except ProviderError as exc:
                result.provider_error = str(exc)
                result.retryable = exc.retryable
                result.action, result.reasons = "escalate", (*gate.reasons, policy.AI_UNAVAILABLE)
                return result
            finally:
                result.timings["generate"] = (time.perf_counter() - started) * 1000
            if raw is None:
                # The budget refused the call: fall back as the organisation chose.
                if self.bundle.budgets.on_exhausted == "human":
                    result.action, result.reasons = "escalate", (*gate.reasons, policy.BUDGET)
                    return result
                answer = extractive(question, found.hits, threshold)
                gate = replace(gate, extractive_only=True)
            else:
                answer = validate(raw, context, threshold)
        result.answer = answer

        if answer.grounded:
            outbound = rule_triage(
                answer.text, self.bundle.categories, self.bundle.policy.custom_sensitive_keywords
            )
            leaked = [s for s in outbound.sensitive if s not in result.triage.sensitive]
            if leaked and gate.route == "proceed":
                # The answer itself talks about refunds, cancellations or account changes the
                # customer did not ask about: a poisoned source, or a model that strayed.
                gate = policy.Gate(
                    "prepare",
                    (SENSITIVE_ANSWER,),
                    gate.extractive_only,
                    hold_for_approval=self.bundle.policy.mode == "approval",
                )
        outcome = policy.finalize(gate, answer.grounded)
        result.action, result.reasons = outcome.action, outcome.reasons
        return result

    def _from_cache(self, result: Result, hit: cache.CachedAnswer) -> Result:
        provider = self.runtime.chat.provider if self.runtime.chat else "extractive"
        result.cache_hit = hit
        result.answer = Answer(hit.answer, True, method="cache")
        result.action, result.reasons = "send", ()
        result.ledger.append(
            LedgerEntry(
                "answer",
                provider,
                self.runtime.config.model_for("answer"),
                cache=hit.kind,
                saved_tokens=hit.tokens,
                saved_cost_usd=hit.cost_usd,
            )
        )
        return result

    async def summarize(
        self, result: Result | None, history: list[tuple[str, str]], reasons: list[str]
    ) -> str:
        """The handoff note. A model summary when one is configured and affordable;
        otherwise a deterministic one built from the customer's own words."""
        labels = ", ".join(policy.REASON_LABELS.get(r, r) for r in reasons) or "handed over"
        customer_lines = [t for r, t in history if r == "customer"]
        fallback = (
            f"Customer: {truncate_tokens(' / '.join(customer_lines[-3:]), 80)} "
            f"Handed over because: {labels}."
        )
        if self.runtime.chat is None or result is None or len(history) < 3:
            return fallback
        try:
            text = await self.call(
                result,
                "summary",
                [
                    ChatMessage("system", SUMMARY_SYSTEM),
                    ChatMessage("user", truncate_tokens(transcript(history), 1500)),
                ],
                model=self.runtime.config.model_for("triage"),
                max_tokens=150,
            )
        except ProviderError:
            return fallback
        return (text or "").strip() or fallback


def ledger_rows(
    org_id: uuid.UUID, ticket_id: uuid.UUID | None, entries: list[LedgerEntry]
) -> list[dict[str, Any]]:
    return [
        {
            "purpose": e.purpose,
            "provider": e.provider,
            "model": e.model,
            "ticket_id": ticket_id,
            "input_tokens": e.input_tokens,
            "output_tokens": e.output_tokens,
            "cost_usd": e.cost_usd,
            "cache": e.cache,
            "saved_tokens": e.saved_tokens,
            "saved_cost_usd": e.saved_cost_usd,
            "latency_ms": e.latency_ms,
            "status": e.status,
            "error": e.error,
        }
        for e in entries
    ]
