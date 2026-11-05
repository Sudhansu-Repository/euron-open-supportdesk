# Operations

Running SupportDesk day to day: scaling, jobs, backups, metrics, secrets and budgets.

## Processes

| Process | Command | Scale |
| --- | --- | --- |
| API | `supportdesk serve` | N replicas behind a load balancer; stateless. Set `REDIS_URL` with more than one replica so live events, the answer cache copy and rate limits are shared |
| Worker | `supportdesk worker` | N replicas; each runs up to `WORKER_CONCURRENCY` jobs. Periodic tasks run on one replica at a time (advisory locks) |
| Web | `node server.js` (image `supportdesk-web`) | N replicas; the widget frame policy cache is per replica (60 s) |
| Migrations | `supportdesk migrate` | One-off, before new code serves |

All processes shut down gracefully on SIGTERM: the worker stops claiming, lets running
jobs finish (up to `JOB_LEASE_S`), then exits; anything unfinished is reclaimed by
another replica after its lease.

## Scaling workers

Worker throughput is roughly `replicas x WORKER_CONCURRENCY / average job time`. AI turns
dominate: with a hosted model a turn takes about the model's latency; with the extractive
provider it is retrieval only. Signs you need more workers: the `queued` count in
`GET /api/v1/system` (admin) or `supportdesk_jobs_total` growing faster than it drains,
and customers waiting for the first AI answer. Raise `WORKER_CONCURRENCY` first (I/O
bound model calls), then add replicas. Keep `(api replicas + worker replicas) x
(DB_POOL_SIZE + DB_MAX_OVERFLOW)` under the database's connection limit.

## Jobs and dead jobs

Jobs live in the `jobs` table ([LLD.md](../architecture/LLD.md#the-job-model)).

```sql
-- queue overview
SELECT status, kind, count(*) FROM jobs GROUP BY status, kind ORDER BY status, kind;

-- what is stuck or failing
SELECT id, kind, attempts, max_attempts, run_after, lease_until, worker, last_error
FROM jobs WHERE status IN ('queued', 'running') AND attempts > 1 ORDER BY run_after;

-- dead jobs with their last error
SELECT id, org_id, kind, payload, attempts, last_error, finished_at
FROM jobs WHERE status = 'dead' ORDER BY finished_at DESC LIMIT 50;
```

A job whose worker dies on its last attempt (out of memory, killed) is buried by the next
worker that sees its lease expire, and its fallback runs as if it had failed normally;
it is never reclaimed forever. Periodic tasks run beside job claiming with a time budget
(240 s), and gap clustering gives each organisation its own budget, so one tenant's slow
embedder cannot delay the others. Budget reservations left behind by a crashed call are
released by the `budget.release_stale` task.

A dead `ai.reply` has already handed its conversation to a person (`ai_unavailable`).
A dead `kb.ingest` leaves the source `failed` with the reason; re-index it from
Knowledge after fixing the cause. A dead `mail.reply` marks the message's email delivery
`failed`. A dead `webhooks.deliver` marks the delivery `dead` (visible in Settings >
Webhooks).

To retry a dead job once its cause is fixed:

```sql
UPDATE jobs SET status = 'queued', attempts = 0, run_after = now(), last_error = NULL,
       finished_at = NULL
WHERE id = '<job id>';
SELECT pg_notify('supportdesk_jobs', 'manual');
```

Handlers are idempotent, so a retried `ai.reply` for a conversation people already own
does nothing. Done jobs are deleted after 2 days; delete old dead jobs when you no longer
need them.

## Backups and restore

Local stack:

```bash
make backup                                   # backups/<timestamp>/: pg_dump (custom format) + the objects bucket
make restore BACKUP=backups/<timestamp>       # stops api, worker and web, restores, starts them
```

`pg_dump` runs in one transaction, so the dump is consistent while the app serves. Keep
`deploy/compose/.env` with the backup: `LOCAL_MASTER_KEY` is needed to open sealed provider
keys and secrets (with `KEY_MODE=kms`, the KMS key is).

AWS: RDS automated backups (3 days on aws-dev, 14 on aws-prod) and point-in-time recovery;
the objects bucket is versioned. To restore, restore the RDS instance to a new instance,
point `DATABASE_URL` (the `<prefix>/connections` secret) at it, and redeploy. Test a
restore before you need one.

## Metrics and alarms

Prometheus metrics on the API (`/metrics`) and the worker (`WORKER_METRICS_PORT`):

| Metric | What |
| --- | --- |
| `supportdesk_ai_decisions_total{action, method}` | AI turns by outcome (send, approval, draft, escalate) and answer method (model, extractive, cache, smalltalk, none) |
| `supportdesk_jobs_total{kind, result}` | Jobs by result: done, retry, dead, lost_lease |
| `supportdesk_job_seconds{kind}` | Job duration histogram |
| `supportdesk_websockets{kind}` | Open sockets: agent, widget, portal |

`GET /readyz` returns 503 when Postgres is unreachable and `degraded` (200) when Redis is.
`GET /api/v1/system` shows the job counts by status and live connections.

On AWS the `observability` module creates alarms (to the SNS topic, optionally emailed via
`alarm_email`) on load balancer 5xx and p95 latency, ECS services with no running task,
RDS CPU, storage and connections, ElastiCache memory and CPU, and two log-derived metrics:
`JobFailures` (worker jobs failing) and `AiTurnsFailed` (AI turns handed to people because
the provider failed), plus a dashboard.

Useful product-level signals: a jump in `ai_unavailable` escalations (provider trouble),
`budget_blocked` rows in Analytics > Costs (budget too tight), webhooks switched off
(Settings > Webhooks), sources `failed` (Knowledge).

## Rotating secrets

| Secret | How |
| --- | --- |
| `SESSION_SECRET` | Change and restart: every agent session, visitor token and portal token becomes invalid (agents sign in again; widget visitors start a new anonymous session) |
| `TOKEN_PEPPER` | Change and restart: every API key, inbound email token, pending invitation and portal link stops working. Issue new API keys and rotate inbound tokens afterwards |
| `LOCAL_MASTER_KEY` | Not rotatable in place in 0.1.0: sealed values (provider keys, webhook secrets, identity secrets) would no longer open. Re-enter them after a change, or use `KEY_MODE=kms`, where KMS key rotation keeps old ciphertexts readable |
| AI provider key | Settings > AI: write the new key (sealed on save) |
| Inbound email token, widget identity secret | Settings > Inboxes: rotate (shown once); update your mail provider or backend |
| Webhook secret | Delete and recreate the webhook (the secret is shown once at creation) |
| API keys | Create a new key, switch the integration, revoke the old one |

On AWS, `SESSION_SECRET` and `TOKEN_PEPPER` live in `<prefix>/app` in Secrets Manager;
update the secret and force a new deployment of the api and worker services.

## Budgets

Settings > AI > Budgets sets daily and monthly token and USD limits per organisation and
the fallback (`extractive` or `human`). Analytics > Costs shows today's and this month's
usage, reserved tokens for calls in flight, and how many calls the budget refused. A
reservation left behind by a crashed process inflates `reserved_*` until the period ends;
check for it with:

```sql
SELECT org_id, period, tokens, reserved_tokens, cost_usd, reserved_cost_usd, blocked
FROM budget_usage ORDER BY period DESC LIMIT 20;
```

and reset `reserved_tokens` and `reserved_cost_usd` to 0 for a period with no calls in
flight if needed. Prices per model are editable in Settings > AI so the costs match your
contract.

## Organisations and owners

`supportdesk create-owner --email ... --org ...` (`make admin` locally, `make aws-admin` on
AWS) creates an organisation and its owner, or resets an existing user to owner with a new
password (and ends their sessions).
