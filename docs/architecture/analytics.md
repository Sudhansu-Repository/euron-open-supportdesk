# Analytics

What the Analytics pages show, how each number is defined, and where it comes from.
Code: `apps/api/src/supportdesk/analytics/service.py`. Endpoints (any agent):
`GET /api/v1/analytics/overview?days=`, `/team`, `/costs`; CSV export (admin):
`/export.csv`.

## Definitions

| Metric | Definition |
| --- | --- |
| Volume | Conversations created in the period, also broken down by channel, category and sentiment (at creation) |
| First response time (FRT) | `first_response_at - created_at`: from the customer's first message to the first reply anyone sent, the AI or a person. Median and p90 over conversations whose first response fell in the period |
| Human first response time | `human_replied_at - escalated_at`: from the handoff to the first reply by a person. Median over escalated conversations whose first human reply fell in the period. This is what SLAs measure |
| Resolution time | `resolved_at - created_at`. Median and p90 over conversations resolved in the period |
| AI resolution rate | Conversations resolved with no human reply (`ai_resolved`) divided by all conversations resolved in the period |
| Deflection rate | AI resolutions divided by all conversations created in the period: the share of demand the team never had to touch |
| Escalation rate | Conversations escalated in the period divided by conversations created in the period |
| Escalation reasons | Count of each reason code on conversations escalated in the period ([ai-agent.md](ai-agent.md#the-policy-gate-and-reason-codes)) |
| CSAT | Mean of the 1 to 5 ratings on conversations resolved in the period |
| Reopened | `reopened` events in the period |
| Messages | Sent replies by customers, agents and the AI |
| Tokens and cost | Sum over `llm_calls` in the period: every model call, including failed ones, drafts, triage, summaries and the playground |
| Cache hits and savings | Ledger rows answered by a cache, and the cost those answers originally took |
| Cost per AI resolution | Total model cost in the period divided by AI resolutions in the period. Failed and escalated attempts are included on purpose: they are part of what an AI resolution really costs |
| SaaS comparison | Intercom Fin's published price of **$0.99 per resolution** times the number of AI resolutions, shown next to the actual cost |

### When a conversation counts as resolved by AI

`ai_resolved` is set when a conversation is resolved while the AI owns it and no person
has replied:

- the customer marks an AI answer helpful (widget or portal); or
- **auto-resolve**: the AI answered, the conversation is `pending` (waiting on the
  customer), and the customer stays silent for **24 hours**. `tickets.auto_resolve` runs
  every 5 minutes and resolves up to 200 such conversations per run.

Any agent reply, approval, assignment or escalation moves the conversation to people, and
a customer reply reopens it and clears `ai_resolved`. Silence is a proxy for "the answer
worked", the same convention per-resolution SaaS pricing uses; a customer who comes back
later reopens the conversation and it no longer counts.

## Rollups and live percentiles

Dashboards read `stats_daily`, not raw tables. One row per organisation and UTC day holds
the counts, the day's FRT and resolution medians and p90s, CSAT sum and count, message
counts, tokens, cost, cache hits, savings and the breakdowns (JSONB).

| Source | When it is computed |
| --- | --- |
| `stats_daily` from the last rolled-up day to today | `analytics.rollup` every 5 minutes (advisory lock, one replica), as an idempotent upsert |
| `stats_daily` for today | Again on every overview request, so today's numbers are always current |
| Older days | Written by the rollup while they were "today" or "yesterday" (and by `make demo` for its 31 days of history); after an outage the next rollup catches up on the missed days (up to 31 days back) |
| Percentiles over the range (FRT, human FRT, resolution) | **Live**, from the indexed ticket timestamps, because medians of daily medians are not the median of the range |

Totals and rates over a range are sums of the daily rows, so a 30-day overview reads 30
rows plus one percentile query. The team view (open load, resolved, replies and CSAT per
agent) is computed live.

`test_overview_matches_a_hand_computed_fixture` inserts four resolved conversations with
known timings, ratings, channels and reasons, and checks volume, AI resolution rate,
CSAT, escalation reasons, channel breakdown and percentiles against hand-computed values.

## Costs view

`GET /api/v1/analytics/costs` groups the ledger by purpose, provider and model: calls,
input and output tokens, cost, cache hits, savings, blocked calls, errors and median
latency, plus today's and this month's budget usage (used, reserved, blocked).

## CSV export

`/export.csv` writes one line per day from `stats_daily` with the counts, medians, CSAT
sum and count, messages, tokens, cost, cache hits and savings.
