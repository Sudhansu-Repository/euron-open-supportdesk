"""AC11: analytics match hand-computed values on a fixed fixture."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.conftest import Stack


async def test_overview_matches_a_hand_computed_fixture(stack: Stack) -> None:
    org = await stack.org("Analytics")
    engine = create_async_engine(stack.settings.database_url)
    now = datetime.now(UTC).replace(microsecond=0)
    day = now - timedelta(days=2)
    async with engine.begin() as conn:
        org_id = await conn.scalar(text("SELECT id FROM orgs WHERE slug = :s"), {"s": org.slug})
        inbox = await conn.scalar(
            text("SELECT id FROM inboxes WHERE org_id = :o AND channel = 'widget'"), {"o": org_id}
        )
        customer = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO customers (id, org_id, name, vip, attributes, created_at, updated_at) "
                "VALUES (:id, :o, 'Fixture', false, '{}', now(), now())"
            ),
            {"id": customer, "o": org_id},
        )
        # (first response after, resolved after, ai_resolved, csat, escalation reasons, channel)
        fixture = [
            (10, 60, True, 5, [], "widget"),
            (20, 120, True, 4, [], "widget"),
            (30, 3600, False, 3, ["sensitive_intent"], "email"),
            (600, 7200, False, None, ["no_grounded_answer"], "widget"),
        ]
        for n, (frt, res, ai, csat, reasons, channel) in enumerate(fixture, start=1):
            created = day + timedelta(hours=n)
            await conn.execute(
                text(
                    "INSERT INTO tickets (id, org_id, number, inbox_id, channel, customer_id, subject, status, priority, "
                    "tags, handled_by, ai_resolved, escalation_reasons, escalated_at, pending_approval, sla_breached, "
                    "reopened_count, first_response_at, resolved_at, csat_score, reply_token, ai_cost_usd, ai_tokens, "
                    "last_message_at, created_at, updated_at) VALUES (:id, :o, :n, :inbox, :ch, :c, 'q', 'resolved', "
                    "'normal', '[]', :hb, :ai, CAST(:reasons AS jsonb), :esc, false, false, 0, :frt, :res, :csat, :tok, 0, 0, "
                    ":created, :created, :created)"
                ),
                {
                    "id": uuid.uuid4(),
                    "o": org_id,
                    "n": n,
                    "inbox": inbox,
                    "ch": channel,
                    "c": customer,
                    "hb": "ai" if ai else "human",
                    "ai": ai,
                    "reasons": str(reasons).replace("'", '"'),
                    "esc": created if reasons else None,
                    "frt": created + timedelta(seconds=frt),
                    "res": created + timedelta(seconds=res),
                    "csat": csat,
                    "tok": uuid.uuid4().hex[:24],
                    "created": created,
                },
            )
        await conn.execute(
            text(
                "INSERT INTO llm_calls (org_id, purpose, provider, model, input_tokens, output_tokens, cost_usd, "
                "saved_tokens, saved_cost_usd, latency_ms, status, created_at) VALUES "
                "(:o, 'answer', 'openai', 'gpt-4o-mini', 1000, 100, 0.0002, 0, 0, 500, 'ok', :at), "
                "(:o, 'triage', 'openai', 'gpt-4o-mini', 200, 50, 0.0001, 0, 0, 200, 'ok', :at)"
            ),
            {"o": org_id, "at": day + timedelta(hours=1)},
        )
    await engine.dispose()
    from supportdesk.analytics.service import rollup_day
    from supportdesk.core.db import Database

    db = Database(stack.settings.database_url, pool_size=1, max_overflow=0)
    async with db.sessionmaker() as session:
        await rollup_day(session, org_id, day.date())
        await rollup_day(session, org_id, (day + timedelta(hours=4)).date())
        await session.commit()
    await db.dispose()

    o = await org.ok("GET", "/api/v1/analytics/overview?days=7")
    assert (
        o["totals"]["created"] == 4
        and o["totals"]["resolved"] == 4
        and o["totals"]["ai_resolved"] == 2
    )
    assert o["ai_resolution_rate"] == 0.5
    assert o["escalation_rate"] == 0.5
    assert o["csat_avg"] == 4.0  # (5 + 4 + 3) / 3
    assert o["frt_median_s"] == 20  # percentile_disc(0.5) of 10, 20, 30, 600
    assert o["resolution_median_s"] == 120
    assert o["breakdown"]["by_channel"] == {"widget": 3, "email": 1}
    assert o["breakdown"]["escalation_reasons"] == {"sensitive_intent": 1, "no_grounded_answer": 1}
    assert Decimal(o["cost_per_ai_resolution_usd"]) == Decimal(
        "0.00015"
    )  # 0.0003 total / 2 AI resolutions
    assert Decimal(o["saas_equivalent_usd"]) == Decimal("1.98")
    costs = await org.ok("GET", "/api/v1/analytics/costs")
    assert sum(int(r["calls"]) for r in costs["rows"]) == 2
    csv = await org.client.get("/api/v1/analytics/export.csv?days=7")
    assert csv.status_code == 200 and csv.text.startswith("day,created,")
