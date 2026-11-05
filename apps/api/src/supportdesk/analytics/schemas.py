"""Analytics responses (typed, so the web client's types are generated)."""

from __future__ import annotations

from pydantic import Field

from supportdesk.core.schemas import ApiModel


class Totals(ApiModel):
    created: int
    resolved: int
    ai_resolved: int
    escalated: int
    reopened: int
    csat_sum: int
    csat_count: int
    messages_customer: int
    messages_agent: int
    messages_ai: int
    tokens: int
    cache_hits: int
    cost_usd: str
    saved_cost_usd: str


class DayPoint(ApiModel):
    day: str
    created: int
    resolved: int
    ai_resolved: int
    escalated: int
    cost_usd: str


class Overview(ApiModel):
    days: int
    totals: Totals
    ai_resolution_rate: float | None = Field(description="AI resolutions over all resolutions")
    escalation_rate: float | None
    deflection_rate: float | None = Field(description="AI resolutions over all conversations")
    csat_avg: float | None
    frt_median_s: int | None
    frt_p90_s: int | None
    resolution_median_s: int | None
    resolution_p90_s: int | None
    human_frt_median_s: int | None = Field(description="From handover to the first human reply")
    cost_per_ai_resolution_usd: str | None
    saas_price_per_resolution_usd: str
    saas_equivalent_usd: str
    series: list[DayPoint]
    breakdown: dict[str, dict[str, int]] = Field(
        description="by_channel, by_category, sentiment and escalation_reasons counts"
    )


class CostRow(ApiModel):
    purpose: str
    provider: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: str
    cache_hits: int
    saved_cost_usd: str
    blocked: int
    errors: int
    p50_ms: int | None


class Usage(ApiModel):
    tokens: int
    cost_usd: str
    reserved_tokens: int
    blocked: int


class Costs(ApiModel):
    rows: list[CostRow]
    usage: dict[str, Usage] = Field(description="today and month")


class TeamMember(ApiModel):
    id: str
    name: str
    availability: str
    capacity: int
    open: int
    resolved: int
    replies: int
    csat: float | None
