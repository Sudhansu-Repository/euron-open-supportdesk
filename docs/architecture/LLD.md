# Low-level design

How the code is organised and how the moving parts behave. Read [HLD.md](HLD.md) first.

## Domain packages

`apps/api/src/supportdesk/` is packaged by domain. A domain owns its `router.py` (HTTP
only), `schemas.py` (the public contract), `service.py` (rules and queries) and
`models.py`. Dependencies point inward; a domain calls another domain's service.

| Package | Owns |
| --- | --- |
| `core` | Settings and boot guards (`config.py`), engine and session (`db.py`), the error envelope (`errors.py`), ASGI middleware (`middleware.py`), the jobs outbox (`jobs.py`), periodic tasks (`tasks.py`), live events (`events.py`, `hub.py`), the KV store (`kv.py`), sealing (`sealing.py`), storage, mail, URL safety (`net.py`), tokens and hashing (`security.py`) |
| `auth` | Sign-up, sign-in with lockout, sessions and revocation, invitations, password change, role and API-key dependencies |
| `org` | Organisations, settings documents (brand, AI, policy, budgets, Token Saver, categories), teams, model prices, the AI connection test |
| `users` | Agents: roles, availability, capacity, invitations |
| `customers` | Customers, merge, portal sign-in tokens |
| `tickets` | Conversations (one conversation is one ticket), messages, notes, events, SLA, routing, macros, approvals, the inbox read side (`queries.py`), periodic upkeep (`tasks.py`) |
| `channels` | Inboxes, the website widget, email in and out, the customer portal |
| `realtime` | The three WebSocket endpoints |
| `knowledge` | Sources, parsing, chunking, the ingest job, articles, hybrid retrieval, the public help center |
| `ai` | Providers, the engine, the `ai.reply` pipeline, triage, policy, answers and grounding, redaction, caches, budgets, the ledger, drafts and the playground |
| `gaps` | Knowledge gaps: recording, clustering, article drafts |
| `analytics` | Daily rollups, the overview, team and cost views, CSV export |
| `integrations` | API keys and webhooks |
| `audit` | The append-only audit log |
| `demo` | The Lumen demo seed |
| `system` | Health, readiness, metrics, deployment info |

Services query the database through SQLAlchemy with the organisation filter in every
statement; tenant-owned tables carry `org_id` through the `OrgScoped` mixin, and lookups by
primary key check `row.org_id` against the caller's scope before returning anything.

## The answer pipeline, step by step

`ai/pipeline.py` (the `ai.reply` job) and `ai/engine.py` (the decision). The playground
(`POST /api/v1/knowledge/test`) runs the same engine with no conversation and the caches
bypassed.

1. **Load** (short session): the customer message, its ticket (skip unless
   `handled_by = 'ai'`), whether an AI or system message already answers it (skip), the
   customer, the inbox, the history (sent replies only), the number of AI turns, unhelpful
   marks, VIP flag, and whether this is the first question (no AI or agent message yet).
2. **Redact** the question and the history (cards with a valid Luhn checksum, API keys,
   AWS keys, GitHub and Slack tokens, JWTs, `password: ...` style secrets).
3. **Small talk**: a greeting or thanks of at most 60 characters gets a fixed friendly
   line, never a knowledge gap.
4. **Triage**: deterministic rules always; the triage model too when one is configured
   and `llm_triage` is on. The merge can only add caution.
5. **Gate** (`policy.gate`): hand over at once, or let the AI *prepare* an answer for a
   person, or *proceed*.
6. **Exact cache**, then **semantic cache**, only when the gate says *proceed* and this is
   the first question.
7. **Embed** the question (an embedding failure falls back to full-text search only).
8. **Retrieve**: hybrid search, top `top_k` hits, each with a relevance score.
9. **Answer**: no passage at or above `min_relevance` means no answer. With no model (the
   extractive provider, or a spent budget with the extractive fallback) the best passage
   is quoted. Otherwise the passages that fit `context_tokens` go to the answer model,
   with the last `history_turns` turns and a one-line summary of older customer turns.
10. **Ground** (`answer.validate`): a cited passage at or above the threshold, or an
    uncited answer whose content words mostly appear in one passing passage.
11. **Outbound screen**: the rules run on the answer text; a sensitive intent the customer
    did not raise turns *proceed* into *prepare* with `sensitive_answer`.
12. **Finalize** (`policy.finalize`): `send`, `approval`, `draft` or `escalate`.
13. **Write** in one fenced transaction (below), then publish events.

Provider failures never raise out of the engine: the result carries `ai_unavailable` and
whether a retry may help. The pipeline raises `RetryLaterError` while attempts remain
(the ledger rows of the failed attempt are written first), and hands over on the last one.

### What each outcome writes

| Action | Messages | Ticket |
| --- | --- | --- |
| `send` | AI reply (`kind=reply`, `status=sent`, citations, `ai_meta`) | `status = pending`, `ai_answered_at`, `first_response_at`; cache entry for a first-question model answer; `mail.reply` job when the customer has an email address (always on email tickets) |
| `approval` | AI reply with `status=pending`, plus a system handoff ("A teammate is checking this") | `pending_approval = true`, escalated with the reasons |
| `draft` | AI draft (`kind=draft`, `status=draft`) visible to agents only, plus a system handoff | escalated with the reasons |
| `escalate` | System handoff only; an `ai.decision` event records the decision | escalated; a knowledge gap question when the reason includes `no_grounded_answer` and not `sensitive_intent` |

Escalation (`tickets.service.escalate`) sets `handled_by = human`, records the reasons and
the summary, starts the SLA clock, and routes to an agent.

## The job model

`core/jobs.py` is a transactional outbox with leases.

| Mechanism | Detail |
| --- | --- |
| Enqueue | `INSERT INTO jobs` in the caller's transaction, then `pg_notify('supportdesk_jobs', kind)`. Visible, and waking workers, only on commit. An optional `dedupe_key` (unique partial index) makes the enqueue idempotent: `ai:<message id>`, `mail:<message id>` |
| Wake-up | Each worker holds one `LISTEN supportdesk_jobs` connection; a missed notification is covered by `WORKER_POLL_INTERVAL_S` (default 5 s). After a successful claim the worker claims again at once |
| Claim | `UPDATE jobs SET status='running', attempts=attempts+1, lease_until=now()+lease, worker=... WHERE id IN (SELECT ... WHERE (status='queued' AND run_after<=now()) OR (status='running' AND lease_until<now()) ORDER BY run_after LIMIT n FOR UPDATE SKIP LOCKED) RETURNING *` |
| Lease | `JOB_LEASE_S` (default 120 s); a heartbeat extends it every third of the lease while the handler runs, only if the row is still `running` with the same attempt number |
| Fencing | Handlers write results through `JobContext.fenced()`, which locks the job row and checks `status='running'` and `attempts` equal to its own attempt before yielding the session; the commit also marks the job `done`. A worker that lost its lease gets `LostLeaseError` and writes nothing |
| Retry | Any exception (or `RetryLaterError`, which skips the stack trace) reschedules with backoff 2, 10, 60, 300, 1800 s (the last repeats) until `max_attempts` |
| Dead | After the last attempt the row is `dead` with `last_error`; the job type's `on_dead` handler runs once (`ai.reply` hands over with `ai_unavailable`) |
| Retention | `jobs.prune` deletes `done` jobs older than 2 days; dead jobs stay for inspection |

| Kind | Handler | Max attempts | Idempotency |
| --- | --- | --- | --- |
| `ai.reply` | `ai/pipeline.py` | 3 | Skips when an AI or system message already replies to the message; unique AI reply index; fenced write |
| `kb.ingest` | `knowledge/service.py` | 3 | Deletes and re-inserts all chunks of the source in the fenced transaction |
| `kb.article` | `knowledge/service.py` | 5 | Same, per article |
| `mail.reply` | `channels/email.py` | 5 | Skips a message already marked `delivery.email = sent`; the `Message-ID` is fixed before sending |
| `webhooks.deliver` | `integrations/service.py` | 8 (ping: 1) | Skips a delivered row; receivers dedupe on `X-SupportDesk-Delivery` |

An external side effect made before the fenced commit (an email, a webhook) may repeat
once after a crash; that is at least once delivery, with the ids above for deduplication.

## Live events and the WebSocket protocol

Events are invalidations, never data: a client that hears one refetches over REST. A lost
event delays an update; it never loses a message. Services call `events.emit()` while they
work; `events.commit()` publishes after the transaction commits, so a rolled-back change
is never announced. Duplicates within one commit are collapsed.

Transport (`core/hub.py`): Redis pub/sub on `sd:ev:<topic>` with one pattern subscription
per process when `REDIS_URL` is set; otherwise Postgres `NOTIFY supportdesk_events`. Each
process fans out to local queues of 256 events; a stalled client drops its oldest event.

| Endpoint | Auth | Topic | Server sends | Client may send |
| --- | --- | --- | --- | --- |
| `/ws/agent` | Session cookie `sd_session` (or `?token=`), not revoked, matching `session_version`, user enabled; `Origin` must be in `CORS_ORIGINS` (or absent) | `org:<org id>` | `ready`, `ping` (every 25 s idle), `message.created {ticket_id}`, `ticket.updated {ticket_id}`, `typing {who: customer, ticket_id}` | `typing {ticket_id}` (relayed to the customer, not stored) |
| `/ws/widget/{ticket_id}` | Visitor token in `?token=` (audience `supportdesk-widget`); the inbox's allowed origins (or the app origin); the ticket must belong to the visitor | `ticket:<ticket id>` | `ready`, `ping`, `message.created {message_id}` (customer-visible replies only), `ticket.updated {status}`, `typing {who: agent, name}` | `typing` |
| `/ws/portal/{ticket_id}` | Portal token in `?token=` (audience `supportdesk-portal`); the ticket must belong to the customer | `ticket:<ticket id>` | as the widget | nothing |

Close codes: 4401 unauthenticated, 4404 not your conversation. Frames over 2000 bytes from
clients are ignored. Internal notes and drafts are never announced on a ticket topic.

## Auth model

| Caller | Credential | Checks |
| --- | --- | --- |
| Agent (browser) | HttpOnly `sd_session` cookie (`SameSite=Lax`, `Secure` with `COOKIE_SECURE`), a JWT (HS256, audience `supportdesk-dashboard`, `SESSION_TTL_HOURS`, `jti`) | Signature, expiry, not in `revoked_sessions`, user enabled, `session_version` matches. Mutations with the cookie must carry `X-SupportDesk-CSRF: 1` |
| Agent (API client) | The same token as `Authorization: Bearer` | As above, no CSRF header needed |
| Integration | `Authorization: Bearer sdk_<12 hex prefix>_<secret>` | Prefix lookup, peppered HMAC of the secret compared in constant time, not revoked. Scope `read` or `write`; `ApiWrite` endpoints refuse read keys with `insufficient_scope` |
| Widget visitor | Visitor token (audience `supportdesk-widget`, 30 days, claims org, inbox, customer) from `POST /api/v1/widget/{key}/session` | Inbox active and in the same org, `Origin` allowed, customer exists |
| Portal customer | Portal token (audience `supportdesk-portal`, 7 days) from redeeming a single-use 15 minute magic link | Org matches the slug in the path |
| Mail provider | Inbound token in the URL path | Peppered hash lookup, constant time compare, inbox active and of channel `email` |

Roles rank `agent < admin < owner`. Agents work the inbox; admins change settings,
inboxes, knowledge sources and articles, macros, SLA policies, API keys and webhooks;
the last owner cannot be demoted. API key actors have role `api`. Signing out records the
token's `jti`; a password change bumps `session_version`, ending every other session.

Lockout: 5 failures per (email, client address) lock that pair for 15 minutes; 50
failures per account within the window lock the account. Unknown emails cost the same
Argon2 verification as known ones.

## Error envelope

Every error, from a typed `AppError`, validation, an integrity race, a too-large body or
an unhandled exception, has the same shape:

```json
{"error": {"code": "origin_not_allowed", "type": "permission_error",
           "message": "This website is not allowed to use this chat widget. Add it under Settings > Inboxes",
           "details": {}}}
```

| Status | Class | Typical codes |
| --- | --- | --- |
| 400 | `AppError` | `invalid_status`, `unsupported_file`, `invalid_url`, `private_url`, `weak_password` |
| 401 | `AuthenticationError` | `not_signed_in`, `session_expired`, `invalid_credentials`, `account_locked`, `invalid_api_key`, `visitor_expired`, `portal_expired`, `identity_invalid`, `identity_required`, `invalid_inbound_token` |
| 403 | `PermissionDeniedError` | `csrf_required`, `insufficient_role`, `insufficient_scope`, `origin_not_allowed` |
| 404 | `NotFoundError` | `ticket_not_found`, `widget_not_found`, `org_not_found` |
| 409 | `ConflictError` | `email_taken`, `conflict` (a unique constraint race) |
| 410 | `GoneError` | `invitation_gone`, `content_expired` |
| 413 | middleware | `payload_too_large` |
| 422 | validation | `validation_error` (with `details.errors`), `invalid_json` |
| 429 | `RateLimitedError` | `rate_limited`, with `Retry-After` |
| 500 | unhandled | `internal_error` (logged with the request id, no stack trace in the body) |

## Middleware order

Outermost first: `RequestContextMiddleware` (request id, security headers, one log line),
`BodySizeLimitMiddleware` (413 before any route reads the body; invalid JSON text is a
422), CORS, gzip (bodies over 2 KB). All are pure ASGI.
