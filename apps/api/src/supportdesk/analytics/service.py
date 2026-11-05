"""Support analytics.

Daily counters (volume, resolutions, messages, tokens, cost, breakdowns) are rolled up by
the worker into ``stats_daily`` every few minutes, today and yesterday, so dashboards read
a few rows instead of scanning conversations. Percentiles over a date range (first
response and resolution time) cannot be added up from daily medians, so they are computed
exactly over the range from the indexed ticket timestamps.

Definitions (also in docs/architecture/analytics.md):

* first response time: from the customer's first message to the first reply anyone (the
  AI or a person) sent;
* resolution time: from creation to resolution;
* AI resolution rate: conversations resolved with no human reply, over all resolved;
* cost per AI resolution: everything spent on models in the period, divided by AI
  resolutions (so failed and escalated attempts are included, as they should be).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.analytics.models import StatsDaily
from supportdesk.core.container import Container
from supportdesk.core.tasks import periodic
from supportdesk.org.models import Org

# Intercom publishes Fin at $0.99 per resolution: the reference shown next to our cost.
SAAS_PRICE_PER_RESOLUTION = Decimal("0.99")

_DAY = text(
    """
    SELECT
      (SELECT count(*) FROM tickets WHERE org_id = :org AND created_at >= :d0 AND created_at < :d1) AS created,
      (SELECT count(*) FROM tickets WHERE org_id = :org AND resolved_at >= :d0 AND resolved_at < :d1) AS resolved,
      (SELECT count(*) FROM tickets WHERE org_id = :org AND resolved_at >= :d0 AND resolved_at < :d1 AND ai_resolved) AS ai_resolved,
      (SELECT count(*) FROM tickets WHERE org_id = :org AND escalated_at >= :d0 AND escalated_at < :d1) AS escalated,
      (SELECT count(*) FROM ticket_events WHERE org_id = :org AND type = 'reopened'
          AND created_at >= :d0 AND created_at < :d1) AS reopened,
      (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM first_response_at - created_at))
         FROM tickets WHERE org_id = :org AND first_response_at >= :d0 AND first_response_at < :d1) AS frt_median,
      (SELECT percentile_disc(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM first_response_at - created_at))
         FROM tickets WHERE org_id = :org AND first_response_at >= :d0 AND first_response_at < :d1) AS frt_p90,
      (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM resolved_at - created_at))
         FROM tickets WHERE org_id = :org AND resolved_at >= :d0 AND resolved_at < :d1) AS res_median,
      (SELECT percentile_disc(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM resolved_at - created_at))
         FROM tickets WHERE org_id = :org AND resolved_at >= :d0 AND resolved_at < :d1) AS res_p90,
      (SELECT coalesce(sum(csat_score), 0) FROM tickets WHERE org_id = :org AND resolved_at >= :d0 AND resolved_at < :d1) AS csat_sum,
      (SELECT count(csat_score) FROM tickets WHERE org_id = :org AND resolved_at >= :d0 AND resolved_at < :d1) AS csat_count
    """
)
_MESSAGES = text(
    "SELECT author_type, count(*) FROM messages WHERE org_id = :org AND kind = 'reply' AND status = 'sent' "
    "AND created_at >= :d0 AND created_at < :d1 GROUP BY author_type"
)
_LLM = text(
    "SELECT coalesce(sum(input_tokens + output_tokens), 0), coalesce(sum(cost_usd), 0), "
    "count(*) FILTER (WHERE cache IS NOT NULL), coalesce(sum(saved_cost_usd), 0) "
    "FROM llm_calls WHERE org_id = :org AND created_at >= :d0 AND created_at < :d1"
)
_GROUP = "SELECT {col}, count(*) FROM tickets WHERE org_id = :org AND created_at >= :d0 AND created_at < :d1 GROUP BY {col}"
_REASONS = text(
    "SELECT r, count(*) FROM tickets, jsonb_array_elements_text(escalation_reasons) AS r "
    "WHERE org_id = :org AND escalated_at >= :d0 AND escalated_at < :d1 GROUP BY r"
)


def _bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


async def rollup_day(session: AsyncSession, org_id: uuid.UUID, day: date) -> None:
    d0, d1 = _bounds(day)
    p = {"org": org_id, "d0": d0, "d1": d1}
    row = (await session.execute(_DAY, p)).one()
    msgs: dict[str, int] = {str(k): int(v) for k, v in (await session.execute(_MESSAGES, p)).all()}
    tokens, cost, hits, saved = (await session.execute(_LLM, p)).one()
    breakdown: dict[str, Any] = {}
    for key, col in (
        ("by_channel", "channel"),
        ("by_category", "coalesce(category, 'general')"),
        ("sentiment", "coalesce(sentiment, 'neutral')"),
    ):
        rows = await session.execute(text(_GROUP.format(col=col)), p)
        breakdown[key] = {str(k): int(v) for k, v in rows.tuples()}
    breakdown["escalation_reasons"] = {
        str(k): int(v) for k, v in (await session.execute(_REASONS, p)).tuples()
    }

    def secs(v: Any) -> int | None:
        return int(v) if v is not None else None

    values = {
        "created": row.created,
        "resolved": row.resolved,
        "ai_resolved": row.ai_resolved,
        "escalated": row.escalated,
        "reopened": row.reopened,
        "frt_median_s": secs(row.frt_median),
        "frt_p90_s": secs(row.frt_p90),
        "resolution_median_s": secs(row.res_median),
        "resolution_p90_s": secs(row.res_p90),
        "csat_sum": int(row.csat_sum),
        "csat_count": row.csat_count,
        "messages_customer": int(msgs.get("customer", 0)),
        "messages_agent": int(msgs.get("agent", 0)),
        "messages_ai": int(msgs.get("ai", 0)),
        "tokens": int(tokens),
        "cost_usd": cost,
        "cache_hits": int(hits),
        "saved_cost_usd": saved,
        "breakdown": breakdown,
        "computed_at": datetime.now(UTC),
    }
    await session.execute(
        insert(StatsDaily)
        .values(org_id=org_id, day=day, **values)
        .on_conflict_do_update(constraint="uq_stats_daily", set_=values)
    )


@periodic("analytics.rollup", every_s=300)
async def rollup_task(container: Container) -> int:
    today = datetime.now(UTC).date()
    async with container.db.sessionmaker() as session:
        org_ids = (await session.scalars(select(Org.id))).all()
        for org_id in org_ids:
            # Catch up on days missed while no worker ran (up to a month back).
            last = await session.scalar(
                select(func.max(StatsDaily.day)).where(StatsDaily.org_id == org_id)
            )
            start = (
                max(last - timedelta(days=1), today - timedelta(days=31))
                if last
                else today - timedelta(days=1)
            )
            day = start
            while day <= today:
                await rollup_day(session, org_id, day)
                day += timedelta(days=1)
            await session.commit()  # one organisation per transaction
    return 0


async def overview(session: AsyncSession, org_id: uuid.UUID, days: int) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    # Today's row is refreshed when it is more than a minute old, so a dashboard that
    # polls does not recompute it on every request.
    fresh = await session.scalar(
        select(StatsDaily.computed_at).where(StatsDaily.org_id == org_id, StatsDaily.day == today)
    )
    if fresh is None or fresh < datetime.now(UTC) - timedelta(minutes=1):
        await rollup_day(session, org_id, today)
        await session.commit()
    start = today - timedelta(days=days - 1)
    rows = list(
        (
            await session.scalars(
                select(StatsDaily)
                .where(StatsDaily.org_id == org_id, StatsDaily.day >= start)
                .order_by(StatsDaily.day)
            )
        ).all()
    )
    by_day = {r.day: r for r in rows}
    series = []
    totals: dict[str, Any] = dict.fromkeys(
        (
            "created",
            "resolved",
            "ai_resolved",
            "escalated",
            "reopened",
            "csat_sum",
            "csat_count",
            "messages_customer",
            "messages_agent",
            "messages_ai",
            "tokens",
            "cache_hits",
        ),
        0,
    )
    totals["cost_usd"] = Decimal(0)
    totals["saved_cost_usd"] = Decimal(0)
    merged: dict[str, dict[str, int]] = {}
    for i in range(days):
        day = start + timedelta(days=i)
        r = by_day.get(day)
        series.append(
            {
                "day": day.isoformat(),
                "created": r.created if r else 0,
                "resolved": r.resolved if r else 0,
                "ai_resolved": r.ai_resolved if r else 0,
                "escalated": r.escalated if r else 0,
                "cost_usd": str(r.cost_usd if r else Decimal(0)),
            }
        )
        if r is None:
            continue
        for k in totals:
            totals[k] += getattr(r, k)
        for group, counts in (r.breakdown or {}).items():
            if isinstance(counts, dict):
                target = merged.setdefault(group, {})
                for name, n in counts.items():
                    target[name] = target.get(name, 0) + int(n)
    d0 = datetime(start.year, start.month, start.day, tzinfo=UTC)
    pct = (
        await session.execute(
            text(
                """
                SELECT
                  (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM first_response_at - created_at))
                     FROM tickets WHERE org_id = :org AND first_response_at >= :d0) AS frt_median,
                  (SELECT percentile_disc(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM first_response_at - created_at))
                     FROM tickets WHERE org_id = :org AND first_response_at >= :d0) AS frt_p90,
                  (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM resolved_at - created_at))
                     FROM tickets WHERE org_id = :org AND resolved_at >= :d0) AS res_median,
                  (SELECT percentile_disc(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM resolved_at - created_at))
                     FROM tickets WHERE org_id = :org AND resolved_at >= :d0) AS res_p90,
                  (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM human_replied_at - escalated_at))
                     FROM tickets WHERE org_id = :org AND human_replied_at >= :d0 AND escalated_at IS NOT NULL) AS human_frt
                """
            ),
            {"org": org_id, "d0": d0},
        )
    ).one()
    resolved = totals["resolved"]
    ai_resolved = totals["ai_resolved"]
    cost = totals["cost_usd"]
    return {
        "days": days,
        "totals": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in totals.items()},
        "ai_resolution_rate": round(ai_resolved / resolved, 4) if resolved else None,
        "escalation_rate": round(totals["escalated"] / totals["created"], 4)
        if totals["created"]
        else None,
        # Share of all conversations the AI closed with no person: deflected from the team.
        "deflection_rate": round(ai_resolved / totals["created"], 4) if totals["created"] else None,
        "csat_avg": round(totals["csat_sum"] / totals["csat_count"], 2)
        if totals["csat_count"]
        else None,
        "frt_median_s": _int(pct.frt_median),
        "frt_p90_s": _int(pct.frt_p90),
        "resolution_median_s": _int(pct.res_median),
        "resolution_p90_s": _int(pct.res_p90),
        "human_frt_median_s": _int(pct.human_frt),
        "cost_per_ai_resolution_usd": str((cost / ai_resolved).quantize(Decimal("0.000001")))
        if ai_resolved
        else None,
        "saas_price_per_resolution_usd": str(SAAS_PRICE_PER_RESOLUTION),
        "saas_equivalent_usd": str(SAAS_PRICE_PER_RESOLUTION * ai_resolved),
        "series": series,
        "breakdown": merged,
    }


def _int(v: Any) -> int | None:
    return int(v) if v is not None else None


async def team(session: AsyncSession, org_id: uuid.UUID, days: int) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await session.execute(
        text(
            """
            SELECT u.id, u.name, u.availability, u.capacity,
              (SELECT count(*) FROM tickets t WHERE t.assignee_id = u.id AND t.status IN ('open','pending')) AS open,
              (SELECT count(*) FROM tickets t WHERE t.assignee_id = u.id AND t.resolved_at >= :since) AS resolved,
              (SELECT count(*) FROM messages m WHERE m.author_id = u.id AND m.author_type = 'agent'
                 AND m.kind = 'reply' AND m.created_at >= :since) AS replies,
              (SELECT avg(t.csat_score) FROM tickets t WHERE t.assignee_id = u.id AND t.resolved_at >= :since) AS csat
            FROM users u WHERE u.org_id = :org AND NOT u.disabled ORDER BY u.name
            """
        ),
        {"org": org_id, "since": since},
    )
    return [
        {
            **dict(r._mapping),
            "id": str(r.id),
            "csat": round(float(r.csat), 2) if r.csat is not None else None,
        }
        for r in rows
    ]


async def ledger(session: AsyncSession, org_id: uuid.UUID, days: int) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    by_purpose = await session.execute(
        text(
            "SELECT purpose, provider, model, count(*) AS calls, sum(input_tokens) AS input_tokens, "
            "sum(output_tokens) AS output_tokens, sum(cost_usd) AS cost_usd, "
            "count(*) FILTER (WHERE cache IS NOT NULL) AS cache_hits, sum(saved_cost_usd) AS saved_cost_usd, "
            "count(*) FILTER (WHERE status = 'budget_blocked') AS blocked, "
            "count(*) FILTER (WHERE status IN ('error','timeout')) AS errors, "
            "percentile_disc(0.5) WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE cache IS NULL AND status = 'ok') AS p50_ms "
            "FROM llm_calls WHERE org_id = :org AND created_at >= :since "
            "GROUP BY purpose, provider, model ORDER BY sum(cost_usd) DESC, count(*) DESC"
        ),
        {"org": org_id, "since": since},
    )
    from supportdesk.ai.budget import periods

    day, month = periods()
    usage = await session.execute(
        text(
            "SELECT period, tokens, cost_usd, reserved_tokens, blocked FROM budget_usage "
            "WHERE org_id = :org AND period IN (:d, :m)"
        ),
        {"org": org_id, "d": day, "m": month},
    )
    return {
        "rows": [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in dict(r._mapping).items()}
            for r in by_purpose
        ],
        "usage": {
            ("today" if r.period == day else "month"): {
                "tokens": int(r.tokens),
                "cost_usd": str(r.cost_usd),
                "reserved_tokens": int(r.reserved_tokens),
                "blocked": int(r.blocked),
            }
            for r in usage
        },
    }


async def export_csv(session: AsyncSession, org_id: uuid.UUID, days: int) -> str:
    start = datetime.now(UTC).date() - timedelta(days=days - 1)
    rows = (
        await session.scalars(
            select(StatsDaily)
            .where(StatsDaily.org_id == org_id, StatsDaily.day >= start)
            .order_by(StatsDaily.day)
        )
    ).all()
    cols = [
        "day",
        "created",
        "resolved",
        "ai_resolved",
        "escalated",
        "reopened",
        "frt_median_s",
        "frt_p90_s",
        "resolution_median_s",
        "csat_sum",
        "csat_count",
        "messages_customer",
        "messages_agent",
        "messages_ai",
        "tokens",
        "cost_usd",
        "cache_hits",
        "saved_cost_usd",
    ]
    lines = [",".join(cols)]
    for r in rows:
        lines.append(",".join("" if getattr(r, c) is None else str(getattr(r, c)) for c in cols))
    return "\n".join(lines) + "\n"
