"""The token ledger, model prices, budget usage and the answer cache."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from supportdesk.core.db import Base, OrgScoped, new_id

PURPOSES = ("triage", "answer", "draft", "summary", "article", "embed")


class LlmCall(OrgScoped, Base):
    """One row per model call, or per call avoided by a cache (tokens 0, cached true)."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_calls_org_time", "org_id", "created_at"),
        Index("ix_llm_calls_ticket", "ticket_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="SET NULL")
    )
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    # exact / semantic when a cache answered; tokens are then 0 and saved_* are estimates.
    cache: Mapped[str | None] = mapped_column(String(16))
    saved_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    saved_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ok, error, timeout, budget_blocked
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ModelPrice(OrgScoped, Base):
    """USD per million tokens. Local models (extractive, Ollama) cost 0 unless set."""

    __tablename__ = "model_prices"
    __table_args__ = (UniqueConstraint("org_id", "provider", "model", name="uq_prices_model"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_per_mtok: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    output_per_mtok: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)


class BudgetUsage(OrgScoped, Base):
    """Tokens and cost used (and reserved by calls in flight) per period.

    ``period`` is ``d:2026-10-30`` or ``m:2026-10``. A call reserves its worst case with
    one conditional UPDATE that succeeds only if the limit still holds, then settles to
    the real usage, so concurrent calls can never overspend a hard budget.
    """

    __tablename__ = "budget_usage"
    __table_args__ = (UniqueConstraint("org_id", "period", name="uq_budget_period"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=0)
    reserved_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reserved_cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=0)
    blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # When the latest reservation was made; the reaper releases reservations left by a
    # call whose worker died before settling (see ai.budget.release_stale).
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnswerCache(OrgScoped, Base):
    """Answers the AI sent, reusable for the same question (exact) or a near one
    (semantic) while the knowledge version is unchanged."""

    __tablename__ = "answer_cache"
    __table_args__ = (
        UniqueConstraint("org_id", "kb_version", "question_hash", name="uq_answer_cache_q"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    kb_version: Mapped[int] = mapped_column(Integer, nullable=False)
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(), nullable=True)
    dims: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    category: Mapped[str | None] = mapped_column(String(64))
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # A customer said this answer did not help: never reuse it.
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
