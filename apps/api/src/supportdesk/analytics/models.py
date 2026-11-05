"""Daily rollups: dashboards read these instead of scanning tickets and messages."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from supportdesk.core.db import Base, OrgScoped


class StatsDaily(OrgScoped, Base):
    __tablename__ = "stats_daily"
    __table_args__ = (UniqueConstraint("org_id", "day", name="uq_stats_daily"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    escalated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reopened: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Seconds; percentiles over tickets whose first response or resolution fell on the day.
    frt_median_s: Mapped[int | None] = mapped_column(Integer)
    frt_p90_s: Mapped[int | None] = mapped_column(Integer)
    resolution_median_s: Mapped[int | None] = mapped_column(Integer)
    resolution_p90_s: Mapped[int | None] = mapped_column(Integer)
    csat_sum: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    csat_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_customer: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_agent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_ai: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    saved_cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=0)
    # {"by_channel": {...}, "by_category": {...}, "escalation_reasons": {...},
    #  "sentiment": {...}, "sla_breached": n}
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
