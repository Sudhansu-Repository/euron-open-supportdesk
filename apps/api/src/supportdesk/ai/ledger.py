"""Model prices and the ledger of every call (or call avoided by a cache)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.ai.models import LlmCall, ModelPrice

MTOK = Decimal(1_000_000)

# Defaults (USD per million input / output tokens) as published by the providers; edit
# them in Settings > AI to match your contract. Local models cost nothing.
DEFAULT_PRICES: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    ("openai", "gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    ("anthropic", "claude-haiku-4-5"): (Decimal("1.00"), Decimal("5.00")),
}
FREE_PROVIDERS = {"extractive", "ollama", "rules", "local", "hash"}


async def price_of(
    session: AsyncSession, org_id: uuid.UUID, provider: str, model: str
) -> tuple[Decimal, Decimal]:
    row = await session.scalar(
        select(ModelPrice).where(
            ModelPrice.org_id == org_id, ModelPrice.provider == provider, ModelPrice.model == model
        )
    )
    if row is not None:
        return row.input_per_mtok, row.output_per_mtok
    if provider in FREE_PROVIDERS:
        return Decimal(0), Decimal(0)
    return DEFAULT_PRICES.get((provider, model), (Decimal(0), Decimal(0)))


def cost(prices: tuple[Decimal, Decimal], input_tokens: int, output_tokens: int) -> Decimal:
    pin, pout = prices
    return ((pin * input_tokens + pout * output_tokens) / MTOK).quantize(Decimal("0.000001"))


@dataclass
class LedgerEntry:
    """One model call (or call avoided by a cache) before it is written."""

    purpose: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    cache: str | None = None
    saved_tokens: int = 0
    saved_cost_usd: Decimal = Decimal(0)
    latency_ms: int = 0
    status: str = "ok"
    error: str | None = None


def record_entry(
    session: AsyncSession, org_id: uuid.UUID, ticket_id: uuid.UUID | None, entry: LedgerEntry
) -> LlmCall:
    return record(
        session,
        org_id,
        ticket_id=ticket_id,
        purpose=entry.purpose,
        provider=entry.provider,
        model=entry.model,
        input_tokens=entry.input_tokens,
        output_tokens=entry.output_tokens,
        cost_usd=entry.cost_usd,
        cache=entry.cache,
        saved_tokens=entry.saved_tokens,
        saved_cost_usd=entry.saved_cost_usd,
        latency_ms=entry.latency_ms,
        status=entry.status,
        error=entry.error,
    )


def record(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    purpose: str,
    provider: str,
    model: str,
    ticket_id: uuid.UUID | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: Decimal = Decimal(0),
    cache: str | None = None,
    saved_tokens: int = 0,
    saved_cost_usd: Decimal = Decimal(0),
    latency_ms: int = 0,
    status: str = "ok",
    error: str | None = None,
) -> LlmCall:
    call = LlmCall(
        org_id=org_id,
        ticket_id=ticket_id,
        purpose=purpose,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        cache=cache,
        saved_tokens=saved_tokens,
        saved_cost_usd=saved_cost_usd,
        latency_ms=latency_ms,
        status=status,
        error=error[:1000] if error else None,
    )
    session.add(call)
    return call
