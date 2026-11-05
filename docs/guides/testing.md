# Testing

Every gate runs locally against Docker; nothing needs an AWS account or an API key.

| Gate | Command | Needs |
| --- | --- | --- |
| Static | `make lint typecheck` | uv, pnpm |
| Unit | `make test` | nothing running |
| Integration | `make test-integration` | Postgres and Redis (started for you) |
| Backend matrix | `make test-matrix` | `make up` (Floci for S3 and KMS) |
| Stack acceptance | `make test-stack` | `make up && make demo` |
| Real Ollama | `make test-ollama` | `make ollama-pull` |
| OpenAPI drift | part of `make test` | nothing |
| End to end | `make e2e` | `make up && make demo` |
| Browser QA | `make qa` | `make up && make demo` |
| Infrastructure | `make tf-validate tf-lint tf-security tf-aws-on-floci` | Docker |
| Sanitization | `make sanitize` | nothing |
| Benchmarks | `make bench` | Postgres (the bench uses its own database) |

Test counts at release 0.1.0: 133 API unit, 96 web unit, 84 integration (each of the 8
matrix combinations), 16 end-to-end, 188 QA page views. Line coverage of `apps/api/src`
from unit plus integration: 87%.

## Unit tests

`apps/api/tests/unit/` mirrors the source tree and needs no database or network: policy
decisions and reason labels, triage rules and the cautious merge, grounding and citation
validation, the extractive answerer, redaction, text normalisation, parsing of each file
type, chunking, calibration, RRF inputs and the context budget, the KV store (expiry, LRU,
byte budget, rate windows), configuration and every production boot guard, SSRF host
checks, email parsing, quote stripping, SES unwrapping, webhook signatures, token
audiences, API key parsing, origin normalisation, routing choice and SLA states, mail
backends (SMTP and SES with threading headers), worker and CLI registration, and the
OpenAPI drift test (`test_the_committed_openapi_document_matches_the_app`: regenerate with
`make openapi` when you change an endpoint).

The web app's Vitest suite (`apps/web/test/`) covers the API client and error mapping,
live-event parsing and query invalidation, routing and the CSP and frame policy helpers,
inbox logic, SLA badges, labels, formatting and the widget state machine.

## Integration tests

`make test-integration` makes sure the Compose Postgres (pgvector) and Redis are
reachable (`scripts/test-db.sh` starts just those two if the stack is down), then runs
`apps/api/tests/integration` with coverage.

How the harness works (`tests/integration/conftest.py`):

- **Real processes.** The real API (uvicorn) and the real worker (`Worker.run`) each run on
  their own thread and event loop, against real Postgres and Redis. Nothing is mocked
  inside the application.
- **A fresh database per run.** `supportdesk_test` is dropped and rebuilt by the
  migrations, so the migrations are tested on every run. The suite refuses a database
  whose name lacks `test` and any non-local host unless `ALLOW_REMOTE_TEST_DB=true`.
- **A tenant per test.** Every test signs up its own organisation, so tests are isolated
  and tenant scoping is exercised on every request.
- **The mock AI** (`apps/api/src/mockai/app.py`) runs as a server speaking the OpenAI,
  Anthropic and Ollama wire formats plus embeddings. It answers from the numbered sources
  in the prompt with a citation, or `NO_ANSWER`, and returns triage JSON. `POST /admin/mode`
  switches it for fault injection: `normal`, `fail` (503), `slow` (sleeps), `garbage`
  (ungrounded text), `uncited` (grounded, no markers), `obedient` (follows instructions in
  the sources). `GET /stats` counts requests per endpoint, which is how the zero-API-key
  test proves no request was made.
- **Fixture servers**: a small web site (pages, a sitemap, `robots.txt`, redirects to
  metadata addresses) for crawl tests, and a webhook receiver that records deliveries and
  can fail on demand.
- **Fast settings**: the hash embedder, `job_lease_s=10`, a 0.5 s poll, the `log` mail
  backend, high rate limits.

What it proves, by file:

| File | Covers |
| --- | --- |
| `test_ai_acceptance.py` | Extractive answers with no outbound call; Ollama wire format; in-policy answer and AI resolution; refund waits for approval, sent only when approved, rejection leaves it with people; draft mode never sends; every escalation reason with its context; VIP; routing to an available agent and the reply reaching the widget over its WebSocket; ungrounded answers never sent; overlap grounding; knowledge gaps; prompt injection in a document and in a message; ledger and cache; knowledge change invalidates the cache; hard budget under 50 concurrent questions; budget fallback to a person; provider outage retried then handed over; a crashed worker's job reclaimed and answered once; message stored before the AI runs |
| `test_knowledge.py` | Each source type searchable and cited; sitemap with robots and same-host rules; unreadable files fail with a reason; metadata URLs refused through redirects; deleting a source retires its answers; atomic re-index; published vs unpublished articles; the playground; gap to article to answer |
| `test_helpdesk.py` | Lifecycle with notes and audit; notes never reach the customer; macros and bulk actions; search and views; keyset pagination; SLA breach flagged by the worker; AI triage fields; role and tenant isolation; lockout per address; password change ends sessions; last owner; logout revokes; concurrent ticket numbers |
| `test_channels.py` | Widget origins; identity verification; visitor isolation; email in, reply out, customer reply threaded; auto replies, duplicates and bad tokens ignored; portal magic link; public help center |
| `test_integrations.py` | API key scopes; webhook signatures, retries and auto-disable; private and metadata webhook URLs refused; live events across two API replicas; health, readiness, metrics, system; large and malformed bodies refused before routes |
| `test_admin_surfaces.py` | Settings validation and key sealing; AI connection test; Anthropic provider; teams, prices, agents; customer edit, search and merge; drafts, macros, SLA policies; widget feedback, rating and email capture; portal reply, feedback and rating |
| `test_analytics.py` | The overview against a hand-computed fixture |
| `test_migrations.py` | Migrations match the models; downgrade and upgrade again |

## Backend matrix

`make test-matrix` reruns the whole integration suite under every combination the app
supports: storage local or S3 (Floci), sealing local or KMS (Floci), Redis on or off
(memory caches and Postgres `LISTEN/NOTIFY`). Eight runs, each in its own database. It
needs `make up` so Floci has the bucket and key from the `local-floci` Terraform.

## Stack acceptance and Ollama

`make test-stack` runs `apps/api/tests/stack` (marker `stack`) against the running stack
and Mailpit. `make test-ollama` runs the tests marked `ollama` against a real Ollama with
the demo model pulled ([zero-api-key.md](zero-api-key.md)).

## End to end

`make e2e` installs the Playwright suite in `e2e/`, installs Chromium and runs it against
the running stack (`make up && make demo`), with the demo customer site and Mailpit URLs
passed in (`E2E_BASE_URL`, `E2E_DEMO_SITE_URL`, `E2E_MAILPIT_URL`, `E2E_PASSWORD`).

## Browser QA

`make qa` runs `scripts/qa/qa.mjs` (Puppeteer, Chromium): every page in light and dark
mode at desktop and phone width, failing on console errors, failed requests, broken
images, horizontal overflow and empty unexplained states, and saving screenshots under
`scripts/qa/output/`. `make screenshots` produces the curated set in
`docs/assets/screenshots/` and the tour GIF.

## Infrastructure

`make tf-validate` (every environment), `make tf-lint` (tflint), `make tf-security`
(checkov, every skip with its reason inline) and `make tf-aws-on-floci`: the full
`aws-dev` environment planned, applied, re-planned (no changes expected) and destroyed
against a throwaway Floci on port 4896. The `local-floci` environment is applied on every
`make up`.

## Benchmarks

`make bench` runs `apps/api/bench.py`: the real API and worker in process against a
throwaway `supportdesk_bench` database, the real local embedder (or `--embedder hash`)
and the mock model, measuring ingest throughput, answer latency per step (extractive,
model, cache hit), message acceptance under concurrency, worker drain rate and WebSocket
fan-out latency. Results are in `docs/bench.json` and the README Performance table.
