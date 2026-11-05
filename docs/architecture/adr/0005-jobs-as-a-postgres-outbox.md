# ADR-0005: Background jobs as a Postgres transactional outbox with NOTIFY and leases

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

A support desk must never lose a customer message's follow-up: the AI turn, the outgoing
email, the webhook. The first plan proposed Redis Streams, as an earlier Euron open-source project uses for its queue.
But a message committed to Postgres and a job published to Redis are two writes: if the
process dies between them, or Redis is down, the message exists without its AI turn. Redis
is also optional in this product.

## Decision

Jobs are rows in the `jobs` table, inserted in the **same transaction** as the change
that needs them (the customer message and its `ai.reply` job commit together), with an
optional unique `dedupe_key`. `pg_notify` on commit wakes idle workers within
milliseconds; a poll interval covers a missed notification. Workers claim with
`FOR UPDATE SKIP LOCKED` and a lease that a heartbeat extends; an expired lease makes the
job claimable again. Each claim increments `attempts`, and results are written through a
fenced session that checks the attempt is still the worker's own. Failures retry with
backoff; the last failure marks the job dead and calls its `on_dead` handler (the AI turn
hands the conversation to a person).

## Consequences

**Good**
- An accepted message can never lose its AI turn (`test_message_is_stored_before_the_ai_runs`,
  `test_a_crashed_workers_job_is_reclaimed_and_answered_once`).
- Works with or without Redis; one less thing to persist and back up.
- The queue is inspectable with SQL.

**Bad / caveats**
- Polling and claim queries load Postgres; fine for support volumes, not for millions of
  jobs per minute.
- One `LISTEN` connection per worker.

## Alternatives considered

- **Redis Streams with consumer groups**: fast and proven, but not atomic with the
  Postgres write, and it would make Redis mandatory and durable.
- **SQS**: the same dual-write gap, plus the emulator in the local hot path.
- **Celery or RQ**: a broker plus a framework, and still not transactional with the
  business write.
