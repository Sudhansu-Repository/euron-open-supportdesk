# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-30

First public release: a self-hosted support desk with a shared inbox, website chat,
email, a customer portal and help center, and an AI agent that answers only from the
organisation's knowledge, within its policy, with a visible cost.

### Added

- Organisations with owners, admins and agents; teams; invitations by email; agent
  availability and capacity; sessions with server-side revocation, a CSRF header, lockout
  per account and address, and password change that ends other sessions.
- Conversations (one conversation is one ticket) across the widget, email, portal and API
  inboxes: statuses, priority, category, tags, assignee and team, internal notes, canned
  replies with placeholders, bulk actions, saved views, full-text search, attachments,
  CSAT, customer merge, keyset pagination, and live updates over WebSockets.
- SLA policies per priority with due times, at-risk and breached flags and a worker scan;
  routing to the least loaded online agent of the team with spare capacity, round robin on
  ties.
- A website widget (one script tag, an iframe on the app's origin) with per-inbox
  appearance, allowed origins enforced by `frame-ancestors` and on every API call, HMAC
  identity verification for API clients, "talk to a person", feedback, ratings and email
  capture.
- An email channel: raw RFC 822 and SES receipt notifications in, threading by reply
  address and `In-Reply-To`/`References`, auto-reply and loop protection, attachments;
  replies out by SMTP or SES with threading headers. Widget and portal replies are also
  emailed when the customer left an address.
- A customer portal with magic link sign-in, and a public help center with search.
- A knowledge base: PDF, DOCX, Markdown, text, HTML and FAQ CSV uploads, single URLs and
  sitemaps (SSRF guarded, robots.txt respected), articles written in the app; bounded
  parsing, chunking with headings and overlap, local embeddings (fastembed bge-small),
  atomic re-indexing, and hybrid retrieval (pgvector HNSW plus Postgres full text, fused
  by reciprocal rank).
- An AI agent with four providers (extractive with no model, Ollama, any OpenAI-compatible
  endpoint, Anthropic) and three embedders (local, Ollama, OpenAI-compatible); provider
  keys sealed with KMS or a local key; a connection test.
- Triage by rules, optionally merged with a model that can only add caution; a policy gate
  outside the model (off, draft, approval, auto) with reason codes; grounding that
  requires a citation above a relevance threshold (with an overlap fallback); outbound
  screening of answers for sensitive topics; redaction of card numbers and secrets before
  any model call; handoff summaries; approval queue; AI drafts for agents.
- Token Saver: exact and semantic answer caches keyed by the knowledge version, short
  context, history folding, model routing, and hard daily and monthly token and cost
  budgets reserved atomically before every call, with an extractive or human fallback.
- A ledger of every model call with tokens, cost, cache savings and latency; editable model
  prices; cost per conversation and per AI resolution.
- Knowledge gaps: unanswered and unhelpful questions clustered by embedding, article drafts
  from the agents' replies, and publish to close the gap.
- Analytics from daily rollups: volume by channel, first response and resolution times
  (median and p90, live percentiles), AI resolution rate with 24 hour auto-resolve,
  escalation rate and reasons, CSAT, team workload, costs against the $0.99 per resolution
  SaaS reference; CSV export.
- A REST API with read and write API keys, and signed webhooks with retries, a delivery
  log, automatic disabling and an SSRF guard.
- Background jobs as a Postgres transactional outbox with `NOTIFY`, `SKIP LOCKED` leases,
  fencing, retries with backoff and dead-job handlers; periodic tasks under advisory
  locks; live events over Redis pub/sub or Postgres `LISTEN/NOTIFY`.
- An append-only audit log enforced by a database trigger; production boot guards;
  security headers; body size limits before routes; rate limits.
- Docker Compose with Floci provisioned by Terraform, an optional Ollama profile, a mock AI,
  a demo customer site and Mailpit; `make demo` seeds the Lumen demo company; `make backup`
  and `make restore`; Prometheus metrics, structured logs, health and readiness probes.
- Terraform for AWS (network, RDS PostgreSQL, ElastiCache, S3, KMS, Secrets Manager, ECR,
  ECS Fargate behind an ALB, SES with optional inbound, CloudWatch) with `local-floci`,
  `aws-dev` and `aws-prod` environments and a migrate-first deploy script.
- Unit, integration (real API and worker against Postgres and Redis), backend matrix,
  end-to-end and browser QA suites; architecture docs, guides and ADRs.

### Known limitations

- The bundled widget loader does not pass verified identity yet.
- SNS subscription confirmation for SES inbound mail is not handled yet.

[Unreleased]: https://github.com/euron-sde-team/euron-open-supportdesk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/euron-sde-team/euron-open-supportdesk/releases/tag/v0.1.0
