# Data model

PostgreSQL 16 with the `vector` extension (pgvector). One Alembic revision creates the
schema: `apps/api/src/supportdesk/migrations/versions/cd27cbfa6596_initial_schema.py`.
`test_the_migrations_match_the_models` proves the migration and the SQLAlchemy models
agree; `test_the_migrations_downgrade_and_upgrade_again` proves the downgrade.

Every tenant-owned table has `org_id uuid NOT NULL REFERENCES orgs ON DELETE CASCADE` with
an index (the `OrgScoped` mixin). Timestamps are `timestamptz`. Ids are UUIDv4 except the
append-heavy tables (`llm_calls`, `ticket_events`, `audit_log`, `budget_usage`,
`stats_daily`), which use `bigint` identities.

## Organisations, people and access

| Table | Key columns | Constraints and indexes |
| --- | --- | --- |
| `orgs` | `name`, `slug` (help center address `/help/<slug>`), `ticket_seq` (per-org ticket numbers), `kb_version` (bumped on every knowledge change) | unique `slug` |
| `org_settings` | PK `org_id`; JSONB documents `brand`, `ai`, `policy`, `budgets`, `token_saver`, `categories`; `ai_api_key_sealed` (bytea) | One row per org. Documents are validated by the Pydantic models in `org/schemas.py` on every read and write, so older documents gain new fields with defaults |
| `users` | `email`, `name`, `password_hash` (Argon2id), `role` (agent, admin, owner), `disabled`, `availability` (online, away, offline), `capacity` (default 10), `session_version` | unique index on `lower(email)` across the install: one account per address, so sign-in needs no organisation picker |
| `invitations` | `email`, `role`, `token_hash` (peppered HMAC), `expires_at` (7 days), `accepted_at`, `invited_by` | unique `token_hash` |
| `teams` | `name`, `last_assigned_user_id` (round-robin cursor) | unique `(org_id, name)` |
| `team_members` | PK `(team_id, user_id)` | index on `user_id` |
| `revoked_sessions` | PK `jti`, `expires_at` | index on `expires_at`; rows past expiry are pruned on later sign-outs |
| `login_failures` | PK `key` (HMAC of email and address, or email), `failures`, `window_started_at`, `locked_until` | Counted with one `INSERT ... ON CONFLICT DO UPDATE` |
| `api_keys` | `name`, `prefix` (12 hex), `secret_hash`, `scope` (read, write), `last_used_at`, `revoked_at` | unique `prefix` |

## Customers and channels

| Table | Key columns | Constraints and indexes |
| --- | --- | --- |
| `customers` | `email`, `name`, `external_id` (the company's own id), `vip`, `attributes` (JSONB), `last_seen_at`, `merged_into_id` | Partial unique `(org_id, lower(email)) WHERE email IS NOT NULL AND merged_into_id IS NULL`, and partial unique `(org_id, external_id) WHERE external_id IS NOT NULL AND merged_into_id IS NULL`. Anonymous widget visitors have no email; merged customers keep their row (pointing at the survivor) without blocking the address |
| `portal_tokens` | `customer_id`, `token_hash`, `expires_at` (15 min), `used_at` | unique `token_hash`; redeemed with one conditional `UPDATE ... RETURNING`, so a link works once |
| `inboxes` | `name`, `channel` (widget, email, portal, api), `public_key` (widget), `allowed_origins`, `appearance` (JSONB), `identity_secret_sealed`, `identity_required`, `email_address`, `inbound_secret_hash`, `team_id`, `ai_enabled`, `active` | unique `public_key`, unique `inbound_secret_hash`. Every new org gets four inboxes; the API inbox has `ai_enabled = false` |

## Conversations

| Table | Key columns | Constraints and indexes |
| --- | --- | --- |
| `tickets` | `number`, `inbox_id`, `channel`, `customer_id`, `subject`, `status` (open, pending, resolved, closed), `priority` (low, normal, high, urgent), `category`, `sentiment`, `intent`, `language`, `tags` (JSONB), `assignee_id`, `team_id`, `handled_by` (ai, human), `ai_resolved`, `escalation_reasons` (JSONB), `escalated_at`, `summary`, `pending_approval`, SLA (`first_response_due_at`, `resolution_due_at`, `sla_next_due_at`, `sla_breached`), `first_response_at`, `human_replied_at`, `ai_answered_at`, `resolved_at`, `closed_at`, `reopened_count`, `last_message_at`, `last_customer_message_at`, `csat_score`, `csat_comment`, `reply_token`, `ai_cost_usd`, `ai_tokens`, `search` (generated tsvector of the subject) | unique `(org_id, number)`: numbers come from `UPDATE orgs SET ticket_seq = ticket_seq + 1 RETURNING`, so concurrent tickets never share a number (`test_concurrent_ticket_numbers_are_unique`); unique `reply_token`; `ix_tickets_inbox (org_id, status, last_message_at)` for the list; `(org_id, assignee_id, status)`; `(customer_id, created_at)`; `(org_id, status, sla_next_due_at)` for the SLA view and scan; GIN on `tags` and `search` |
| `messages` | `ticket_id`, `author_type` (customer, agent, ai, system), `author_id`, `kind` (reply, note, draft), `status` (sent, draft, pending, discarded, rejected), `body`, `citations` (JSONB), `reply_to_id` (for an AI turn, the customer message it answers), `feedback` (helpful, unhelpful), `email_message_id`, `delivery` (JSONB), `ai_meta` (JSONB: the decision panel), `sent_at`, `search` (generated tsvector) | **Partial unique `uq_messages_ai_reply (reply_to_id) WHERE author_type = 'ai' AND reply_to_id IS NOT NULL`**: one AI turn per customer message whatever the number of job attempts. `(ticket_id, created_at)`; `(org_id, email_message_id)` for threading and duplicate detection; partial `(org_id, status) WHERE status = 'pending'` for the approvals queue; GIN on `search` |
| `attachments` | `ticket_id`, `message_id`, `filename`, `content_type`, `size`, `sha256`, `storage_key` | Bytes in object storage; the row keeps only the key |
| `ticket_events` | `ticket_id`, `type` (created, status, assigned, priority, category, escalated, taken_over, ai.answered, ai.decision, approved, rejected, note, rated, reopened, sla_breached), `actor_type`, `actor_id`, `data` (JSONB) | index on `ticket_id`. The conversation's history |
| `macros` | `title`, `body`, `actions` (JSONB), `uses` | unique `(org_id, title)` |
| `sla_policies` | `priority`, `first_response_minutes`, `resolution_minutes`, `enabled` | unique `(org_id, priority)`. Defaults: urgent 30 min / 4 h, high 2 h / 24 h, normal 8 h / 3 days, low 24 h / 7 days |

## Knowledge

| Table | Key columns | Constraints and indexes |
| --- | --- | --- |
| `kb_sources` | `kind` (file, url, sitemap), `title`, `url`, `filename`, `content_type`, `storage_key`, `sha256`, `size`, `status` (queued, processing, ready, failed), `error`, `pages`, `chunk_count`, `version`, `last_indexed_at` | |
| `kb_articles` | `title`, `slug`, `body` (Markdown), `category`, `status` (draft, published), `published_at`, `views`, `helpful_yes`, `helpful_no`, `search` (generated, title weight A, body weight B) | unique `(org_id, slug)`; GIN on `search` |
| `kb_chunks` | `source_id` or `article_id` (cascade), `version`, `ordinal`, `title`, `heading`, `url` (deep link), `text`, `tokens`, `embedding vector` (unsized), `dims`, `embed_model`, `search` (generated, title and heading weight A, text weight B) | `(source_id, version)`, `article_id`, GIN on `search`, **HNSW per dimension** (below) |

### Vector indexes

Embedding columns are unsized `vector`, so an organisation can change embedder without a
migration. pgvector cannot build one HNSW index over vectors of mixed sizes, so the
migration creates one **partial expression index per supported size**:

```sql
CREATE INDEX ix_kb_chunks_hnsw_384 ON kb_chunks USING hnsw
  ((embedding::vector(384)) vector_cosine_ops) WHERE dims = 384;
```

for 384, 768, 1024 and 1536 dimensions, on `kb_chunks` and on `answer_cache`. Queries cast
the same way and filter `dims = N` (and `embed_model = <current embedder>` for chunks),
so the planner uses the index and vectors from a previous embedder are never compared with
new ones. Other sizes fall back to full-text search only. See
[ADR-0004](adr/0004-pgvector-in-the-same-postgres.md).

## AI, cost and caches

| Table | Key columns | Constraints and indexes |
| --- | --- | --- |
| `llm_calls` | `ticket_id`, `purpose` (triage, answer, draft, summary, article), `provider`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `cache` (exact, semantic), `saved_tokens`, `saved_cost_usd`, `latency_ms`, `status` (ok, error, budget_blocked), `error` | `(org_id, created_at)`, `ticket_id`. One row per model call or per call a cache avoided |
| `model_prices` | `provider`, `model`, `input_per_mtok`, `output_per_mtok` (USD) | unique `(org_id, provider, model)`. Defaults in code for `gpt-4o-mini` and `claude-haiku-4-5`; local providers cost 0 |
| `budget_usage` | `period` (`d:2026-10-30` or `m:2026-10`), `tokens`, `cost_usd`, `reserved_tokens`, `reserved_cost_usd`, `blocked` | unique `(org_id, period)`; reserved with a conditional `UPDATE` ([ai-agent.md](ai-agent.md#hard-budgets)) |
| `answer_cache` | `kb_version`, `question_hash`, `question`, `embedding`, `dims`, `answer`, `citations`, `category`, `tokens`, `cost_usd`, `hits`, `disabled`, `last_hit_at` | unique `(org_id, kb_version, question_hash)`; HNSW per dimension |
| `knowledge_gaps` | `title`, `status` (open, drafted, resolved, dismissed), `question_count`, `last_seen_at`, `centroid`, `dims`, `article_id` | `(org_id, status, question_count)` |
| `gap_questions` | `gap_id`, `ticket_id`, `message_id`, `question`, `reason` (no_answer, unhelpful), `embedding`, `dims` | unique `message_id` (recording is idempotent per customer message); `(org_id, gap_id)` for the unclustered scan |

## Integrations, jobs, analytics, audit

| Table | Key columns | Constraints and indexes |
| --- | --- | --- |
| `webhooks` | `url`, `events` (JSONB), `secret_sealed`, `active`, `consecutive_failures`, `disabled_reason`, `last_success_at` | |
| `webhook_deliveries` | `webhook_id`, `event`, `payload`, `status` (pending, delivered, failed, dead), `attempts`, `response_status`, `response_ms`, `error`, `delivered_at`, `size` | `(webhook_id, created_at)` |
| `jobs` | `org_id` (nullable), `kind`, `payload`, `dedupe_key`, `status` (queued, running, done, dead), `attempts`, `max_attempts`, `run_after`, `lease_until`, `worker`, `last_error`, `finished_at` | `ix_jobs_claim (status, run_after)`; partial unique `dedupe_key WHERE dedupe_key IS NOT NULL`; `org_id` |
| `stats_daily` | `day`, `created`, `resolved`, `ai_resolved`, `escalated`, `reopened`, FRT and resolution median and p90 (seconds), `csat_sum`, `csat_count`, messages by author, `tokens`, `cost_usd`, `cache_hits`, `saved_cost_usd`, `breakdown` (JSONB: by channel, category, sentiment, escalation reason), `computed_at` | unique `(org_id, day)`, upserted by the rollup |
| `audit_log` | `at`, `actor_id`, `actor_email`, `action`, `target_type`, `target_id`, `details`, `ip` | index on `at`. **Append-only**: a `BEFORE UPDATE OR DELETE` trigger raises `audit_log is append-only` unless the transaction sets `supportdesk.allow_audit_delete = on` (reserved for removing a whole organisation; no endpoint does that in 0.1.0) |

## Retention

| Data | Kept |
| --- | --- |
| `jobs` with status `done` | 2 days (`jobs.prune`, hourly) |
| `jobs` with status `dead` | Until an operator deletes them (they carry `last_error` for inspection) |
| `revoked_sessions` | Until the session would have expired |
| `portal_tokens`, `invitations` | Rows stay; expired or used tokens are refused |
| `answer_cache` | Rows of a retired `kb_version`, and rows older than 365 days, are deleted by `jobs.prune`; lookups also ignore rows older than the organisation's `cache_ttl_hours` |
| Conversations, messages, ledger, audit, rollups, gaps | Indefinitely in 0.1.0 (configurable retention is on the roadmap) |
| Raw inbound mail on AWS | Under `inbound/` in the objects bucket, per the bucket's lifecycle rules |
