# Configuration

Two layers:

- **Deployment settings** come from the environment, are read once at boot by
  `Settings` in `apps/api/src/supportdesk/core/config.py` (the API, the worker and the CLI
  all use it), and are checked by `guard()` when `ENVIRONMENT=production`. Names are case
  insensitive.
- **Organisation settings** (AI provider, models, policy, budgets, Token Saver,
  categories, brand) live in the database and are edited in Settings by admins. They take
  effect on the next message; nothing restarts.

Locally, `deploy/compose/compose.yaml` sets the deployment settings and `make env` writes
the secrets to `deploy/compose/.env`. On AWS the Terraform `service` module sets them
(secrets from Secrets Manager); extra non-secret values go in `api_extra_environment`.

## Environment variables (API and worker)

### Runtime

| Variable | Default | Meaning |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development`, `test` or `production`. Production runs the boot guards |
| `LOG_LEVEL` | `INFO` | Log level of the JSON logs |
| `SUPPORTDESK_CLOUD` | `local` | `local`, `floci` or `aws`. With `aws`, `AWS_ENDPOINT_URL` must be unset in production |
| `OTEL_ENABLED` | `false` | Turn on OpenTelemetry tracing hooks |

### Database and cache

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://supportdesk:supportdesk@localhost:4842/supportdesk` | Postgres 16 with the `vector` extension available |
| `DB_POOL_SIZE` | `10` | SQLAlchemy pool size per process |
| `DB_MAX_OVERFLOW` | `20` | Extra connections above the pool |
| `REDIS_URL` | empty | Redis for cross-replica live events, the exact answer cache copy and rate limits. Empty: process memory and Postgres `LISTEN/NOTIFY` (exact for one replica). Jobs never depend on it |
| `MEMORY_CACHE_MAX_BYTES` | `64000000` | Byte budget of the in-process cache when `REDIS_URL` is empty (minimum 1,000,000) |

### Sessions, tokens and URLs

| Variable | Default | Meaning |
| --- | --- | --- |
| `SESSION_SECRET` | dev placeholder | Signs agent sessions, visitor tokens and portal tokens. Production: random, at least 32 characters |
| `TOKEN_PEPPER` | dev placeholder | Peppers the hashes of API keys, invitation, portal and inbound tokens, and lockout keys. Production: random, at least 32 characters, different from `SESSION_SECRET` |
| `SESSION_TTL_HOURS` | `12` | Agent session lifetime |
| `COOKIE_SECURE` | `false` | `Secure` flag on the session cookie. Must be true in production |
| `CORS_ORIGINS` | `http://localhost:4810` | Comma-separated origins of the agent app (also the allowed `Origin` of `/ws/agent`). `*` is refused in production. Widget origins are per inbox, not here |
| `PUBLIC_URL` | `http://localhost:4810` | Where agents and customers open the app: links in emails, article URLs in citations, the widget frame origin. Must be `https://` in production |
| `PUBLIC_API_URL` | `http://localhost:4830` | Where browsers on customer websites reach the API. Must be `https://` in production |
| `SIGNUP_ENABLED` | `true` | Anyone may create an organisation from the sign-up page. Turn off on a private install once your organisation exists; invitations still work |

### Secrets sealing

| Variable | Default | Meaning |
| --- | --- | --- |
| `KEY_MODE` | `local` | `local` (AES-256-GCM with `LOCAL_MASTER_KEY`) or `kms` (AWS KMS) for AI provider keys, webhook secrets and widget identity secrets |
| `LOCAL_MASTER_KEY` | dev placeholder | The local sealing key. Production with `KEY_MODE=local`: random, at least 32 characters. Changing it makes existing sealed values unreadable |
| `KMS_KEY_ID` | `alias/supportdesk-local` | KMS key id or alias with `KEY_MODE=kms` |

### AWS and storage

| Variable | Default | Meaning |
| --- | --- | --- |
| `AWS_REGION` | `us-east-1` | Region for S3, KMS and SES |
| `AWS_ENDPOINT_URL` | unset | An emulator endpoint (Floci locally). Unset on AWS |
| `S3_FORCE_PATH_STYLE` | `false` | Path-style S3 addressing (emulators) |
| `STORAGE` | `local` | `local` (disk) or `s3` for knowledge uploads, attachments and exports. Rows keep only the key |
| `OBJECTS_BUCKET` | `supportdesk-local-objects` | The S3 bucket with `STORAGE=s3` |
| `LOCAL_STORAGE_DIR` | `./.data/objects` | The directory with `STORAGE=local` |

Standard AWS SDK variables (`AWS_ACCESS_KEY_ID`, `AWS_PROFILE` and so on) are read by
boto3; on ECS the task role is used.

### Mail

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAIL_BACKEND` | `log` | `log` (kept in memory, never sent; development and tests), `smtp` or `ses`. `log` is refused in production |
| `MAIL_FROM_NAME` | `Support` | Default sender name (ticket replies use `<Company> Support`) |
| `MAIL_FROM_ADDRESS` | `support@supportdesk.local` | The sender address. Mail from this address is ignored when it comes back in |
| `MAIL_REPLY_DOMAIN` | `supportdesk.local` | Domain of the reply addresses `<local>+<ticket token>@<domain>` and of generated `Message-ID`s. Inbound mail for this domain must reach the inbound webhook |
| `SMTP_HOST` | `localhost` | SMTP relay with `MAIL_BACKEND=smtp` (Mailpit locally) |
| `SMTP_PORT` | `4826` | SMTP port |

### AI and knowledge

| Variable | Default | Meaning |
| --- | --- | --- |
| `EMBEDDER` | `local` | The deployment's embedder: `local` (fastembed, ONNX on CPU) or `hash` (tests only, refused in production). Organisations may choose a remote embedder in Settings |
| `LOCAL_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | One of `BAAI/bge-small-en-v1.5`, `BAAI/bge-base-en-v1.5`, `sentence-transformers/all-MiniLM-L6-v2`, `intfloat/multilingual-e5-small` |
| `MODEL_CACHE_DIR` | `./.data/models` | Where the embedding model is downloaded (a volume in Compose) |
| `OLLAMA_URL` | `http://localhost:4834` | Default base URL for the `ollama` provider (`http://ollama:11434` in Compose) |
| `AI_ALLOW_PRIVATE_ENDPOINTS` | `true` | Allow AI and embedding endpoints on private addresses (Ollama or vLLM in the same network). Metadata addresses are always refused |
| `AI_TIMEOUT_S` | `60` | Timeout of one model call (0 to 600) |
| `MAX_UPLOAD_BYTES` | `25000000` | Largest knowledge upload, crawled page and inbound email |
| `MAX_ATTACHMENT_BYTES` | `10000000` | Largest email attachment kept |
| `MAX_CRAWL_PAGES` | `50` | Pages read from one sitemap (1 to 1000) |
| `ALLOW_PRIVATE_URLS` | `false` | Allow crawls and webhooks to private and loopback addresses (local demos). Refused in production |

### Limits and worker

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAX_BODY_BYTES` | `1000000` | Largest request body (uploads by admins and inbound email use `MAX_UPLOAD_BYTES`) |
| `WIDGET_RPM` | `20` | Messages per minute per widget visitor (3x per address; sessions 2x per address) |
| `LOGIN_RPM` | `20` | Sign-in attempts per minute per address (lockout is separate) |
| `SIGNUP_RPM` | `5` | Sign-ups and invitation acceptances per minute per address |
| `HTTP_KEEP_ALIVE_S` | `75` | Idle keep-alive of API connections; keep it above the load balancer's idle timeout (Terraform sets 310 against 300) |
| `WORKER_POLL_INTERVAL_S` | `5` | How often an idle worker checks for jobs when no notification arrives |
| `WORKER_CONCURRENCY` | `8` | Jobs one worker runs at once (1 to 64) |
| `JOB_LEASE_S` | `120` | Job lease; a dead worker's job is reclaimed after it (10 to 3600) |
| `WORKER_METRICS_PORT` | `9464` | Prometheus port of the worker (0 disables) |

### Read outside `Settings`

| Variable | Read by | Meaning |
| --- | --- | --- |
| `PORT` | `supportdesk serve` | Listen port (default 8080) |
| `FORWARDED_ALLOW_IPS` | `supportdesk serve` | Addresses trusted to set `X-Forwarded-For` (default `127.0.0.1`; `*` on the Compose network; the VPC CIDR on AWS) |
| `SUPPORTDESK_OWNER_PASSWORD` | `supportdesk create-owner` | The password, instead of a prompt |
| `SEED_AI_URL` | `supportdesk seed-demo` | When set, the demo organisation uses the `openai` provider at this URL (the mock AI in Compose); otherwise `extractive` |

## Web app

| Variable | Default | Meaning |
| --- | --- | --- |
| `API_URL` (or `API_INTERNAL_URL`) | `http://localhost:4830` | Where the web server proxies `/api` and asks for widget frame policies |
| `NEXT_PUBLIC_WS_URL` | empty | A WebSocket origin to allow in the CSP when sockets do not go through the web origin |

## Ports

Host ports are set in `deploy/compose/.env` (defaults shown):

| Variable | Default | Service |
| --- | --- | --- |
| `SD_WEB_PORT` | 4810 | Web app |
| `SD_DEMO_PORT` | 4815 | Demo customer site |
| `SD_MAILPIT_PORT` / `SD_SMTP_PORT` | 4825 / 4826 | Mailpit UI / SMTP |
| `SD_API_PORT` | 4830 | API |
| `SD_OLLAMA_PORT` | 4834 | Ollama (profile `ollama`) |
| `SD_PG_PORT` | 4842 | Postgres |
| `SD_MOCK_AI_PORT` | 4850 | Mock AI |
| `SD_FLOCI_PORT` | 4866 | Floci |
| `SD_REDIS_PORT` | 4879 | Redis |

## Organisation settings

`GET` and `PATCH /api/v1/org/settings` (read: any agent; write: admin). Each document is
validated by its Pydantic model (`org/schemas.py`); missing fields take their defaults.

### `ai`

| Field | Default | Meaning |
| --- | --- | --- |
| `provider` | `extractive` | `extractive`, `ollama`, `openai` (any compatible endpoint) or `anthropic` |
| `base_url` | provider default | `OLLAMA_URL`, `https://api.openai.com/v1` or `https://api.anthropic.com` |
| `answer_model` | provider default | `qwen2.5:1.5b`, `gpt-4o-mini`, `claude-haiku-4-5` |
| `triage_model` | the answer model | A cheaper model for triage and summaries (model routing) |
| `llm_triage` | `true` | Use the model for triage too; off means rules only (zero tokens) |
| `embedder` | `local` | `local`, `ollama` or `openai`; a remote one needs `embed_model` and `embed_dims` (64 to 4096). Changing it re-indexes everything |
| `embed_base_url`, `embed_model`, `embed_dims` | none | Remote embedder settings |
| `temperature` | `0.2` | 0 to 1.5 |
| `max_answer_tokens` | `400` | 50 to 4000 |
| `context_tokens` | `1800` | Passage budget in the prompt (200 to 16000) |
| `top_k` | `5` | Passages retrieved (1 to 20) |

The provider key is written separately (`ai_api_key`, write-only, empty string clears it)
and sealed.

### `policy`

| Field | Default | Meaning |
| --- | --- | --- |
| `mode` | `approval` | `off`, `draft`, `approval`, `auto` ([ai-agent.md](../architecture/ai-agent.md#the-policy-gate-and-reason-codes)) |
| `auto_categories` | technical, account, shipping, general, billing | Categories the AI may resolve alone |
| `min_relevance` | `0.5` | A passage must score at least this to be cited (0 to 1) |
| `sensitive_intents` | refund, cancellation, account_change, billing_dispute, legal, security, data_deletion | Intents that always need a person |
| `custom_sensitive_keywords` | none | Extra words (at most 100) that need a person |
| `escalate_negative_sentiment` | `true` | Frustrated customers go to a person |
| `escalate_vip` | `true` | VIP customers go to a person |
| `max_unhelpful` | `1` | Hand over after this many unhelpful marks (0 disables) |
| `max_ai_turns` | `6` | Hand over after this many AI answers in one conversation |

### `budgets`

| Field | Default | Meaning |
| --- | --- | --- |
| `daily_tokens`, `monthly_tokens` | `0` | Hard token limits (0 means unlimited) |
| `daily_cost_usd`, `monthly_cost_usd` | `0` | Hard USD limits |
| `on_exhausted` | `extractive` | `extractive` (quote passages, no model) or `human` (hand over) |

### `token_saver`

| Field | Default | Meaning |
| --- | --- | --- |
| `exact_cache` | `true` | Reuse an answer for the same normalised first question |
| `semantic_cache` | `true` | Reuse an answer for a near-identical first question |
| `semantic_threshold` | `0.92` | Cosine similarity needed (0.5 to 1) |
| `cache_ttl_hours` | `336` | Lifetime of a cached answer, exact and semantic (Postgres lookups ignore older rows; the KV copy expires with it). Changing the AI provider, models or the policy retires every cached answer |
| `history_turns` | `6` | Turns sent verbatim; older ones are folded into a line |

### `brand` and `categories`

`brand`: `company_name`, `support_email`, `accent_color` (`#rrggbb`), `help_center_title`,
`website`. `categories`: 1 to 30 lower-case names (default billing, technical, account,
shipping, general).

### Elsewhere in Settings

Inboxes (allowed origins, appearance, identity secret and requirement, email address,
inbound token, team, AI on or off), teams, agents (role, availability, capacity), SLA
policies per priority, canned replies, model prices, API keys, webhooks and the audit log.
