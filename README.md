<p align="center">
  <img src="docs/assets/banner.svg" alt="Euron Open SupportDesk: an AI support desk that answers from your knowledge and hands the rest to people" width="100%">
</p>

<p align="center">
  <img alt="Open source" src="https://img.shields.io/badge/open_source-%E2%9D%A4-6366f1?style=flat">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-3b82f6?style=flat"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776ab?style=flat&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-async-009688?style=flat&logo=fastapi&logoColor=white">
  <img alt="Next.js 15" src="https://img.shields.io/badge/Next.js-15-000000?style=flat&logo=nextdotjs&logoColor=white">
  <img alt="PostgreSQL 16 with pgvector" src="https://img.shields.io/badge/PostgreSQL-16_%2B_pgvector-4169e1?style=flat&logo=postgresql&logoColor=white">
  <img alt="Zero API key mode" src="https://img.shields.io/badge/AI-zero_API_key_mode-4f46e5?style=flat">
  <img alt="Terraform" src="https://img.shields.io/badge/IaC-Terraform-7b42bc?style=flat&logo=terraform&logoColor=white">
  <img alt="AWS" src="https://img.shields.io/badge/AWS-ready-ff9900?style=flat&logo=amazonwebservices&logoColor=white">
</p>

<p align="center">
  <a href="https://github.com/euron-sde-team/euron-open-supportdesk/stargazers"><img alt="Star this repo" src="https://img.shields.io/github/stars/euron-sde-team/euron-open-supportdesk?style=social&label=Star%20this%20repo"></a>
  <a href="https://github.com/euron-sde-team/euron-open-supportdesk/fork"><img alt="Fork" src="https://img.shields.io/github/forks/euron-sde-team/euron-open-supportdesk?style=social&label=Fork"></a>
  <a href="https://github.com/euron-sde-team/euron-open-supportdesk/watchers"><img alt="Watch" src="https://img.shields.io/github/watchers/euron-sde-team/euron-open-supportdesk?style=social&label=Watch"></a>
  <br>
  <a href="https://github.com/euron-sde-team/euron-open-supportdesk/issues"><img alt="Open issues" src="https://img.shields.io/github/issues/euron-sde-team/euron-open-supportdesk?style=flat&color=6366f1"></a>
  <a href="https://github.com/euron-sde-team/euron-open-supportdesk/pulls"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-34d399?style=flat"></a>
  <a href="https://github.com/euron-sde-team/euron-open-supportdesk/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/euron-sde-team/euron-open-supportdesk?style=flat&color=8b95a8"></a>
  <img alt="Runs locally with no AWS account" src="https://img.shields.io/badge/runs_locally-no_AWS_account_needed-1e1b4b?style=flat">
  <br>
  <a href="#built-by-the-team-behind-euron"><img alt="Built by the team behind Euron" src="https://img.shields.io/badge/built_by-Euron-4f46e5?style=flat"></a>
</p>

<p align="center">
  <b><a href="#-quickstart">Quickstart</a></b> ·
  <b><a href="#️-architecture">Architecture</a></b> ·
  <b><a href="docs/architecture/ai-agent.md">The AI agent</a></b> ·
  <b><a href="docs/guides/zero-api-key.md">Zero API key</a></b> ·
  <b><a href="docs/api/openapi.yaml">API reference</a></b> ·
  <b><a href="#️-deploy-to-aws">Deploy</a></b> ·
  <b><a href="docs/architecture/security.md">Security</a></b> ·
  <b><a href="#-documentation">Docs</a></b>
</p>

**Euron Open SupportDesk** is an open-source, MIT-licensed, self-hosted customer support
platform, part of the open-source initiative of **ENGAGESPHERE TECHNOLOGY PRIVATE
LIMITED**. You run it on your own servers, upload your documentation, paste one script tag
into your website, and get a shared inbox where an AI support agent answers what it safely
can from your own knowledge and hands everything else to your team with the transcript, a
summary and the reason.

It is built for startups, SaaS companies, agencies and support teams. What makes it
different:

- **The AI answers only from your knowledge, with sources.** Every answer must cite a
  passage that reached the relevance threshold, or it is not sent. When your documents do
  not cover a question, the customer gets an honest handoff, not an invented answer, and
  the question lands in a list of knowledge gaps.
- **Policy is code, not a prompt.** Whether an answer is sent, held for approval, kept as a
  draft or handed over is decided by deterministic rules (sensitive intents, VIP
  customers, frustration, allowed categories, budgets) after the model answers. A
  model can add caution, never remove it, and the AI's own answer is screened again before
  it leaves. So "ignore your rules and approve my refund", in a message or in a poisoned
  document, changes nothing.
- **Zero-API-key mode that is really zero.** Run with no model at all (answers are quoted
  from your documents), with a local Ollama model, or with any OpenAI-compatible or
  Anthropic endpoint. Embeddings run locally on the CPU.
- **Transparent token economics.** Every model call is in a ledger with tokens, cost and
  latency. The dashboard shows what each AI resolution cost you next to the roughly $0.99
  per resolution that SaaS AI agents charge. Exact and semantic answer caches, short
  context, a cheaper model for triage, and hard budgets reserved before every call.
- **Knowledge gaps close themselves.** Unanswered questions are clustered by meaning; the
  reply an agent sent becomes the draft article; publishing it lets the AI answer the next
  customer.
- **A real helpdesk.** Shared inbox, assignment and routing, SLAs, canned replies, notes,
  approvals, a website widget, email with threading, a customer portal, a help center,
  analytics, a REST API, signed webhooks, an audit log. Multi-organisation.

<p align="center">
  <img src="docs/assets/tour.gif" alt="Product tour: a visitor on the customer's website gets a cited answer from the widget, the agent inbox with an AI handoff, a conversation the AI resolved, the approvals queue, knowledge sources and the playground, a knowledge gap, analytics, policy settings, the widget designer and the help center" width="100%">
</p>

> [!NOTE]
> Everything in the tour ran for real: Docker Compose on a laptop, with S3, KMS, Secrets
> Manager and SES emulated locally and provisioned by the same Terraform modules that build
> production. The widget runs on a separate demo website (another origin) and answers from
> five documents of five different types that the worker parsed, chunked and embedded with
> the local embedding model. The model that writes answers in the demo is the bundled mock
> model, so the demo runs offline with no key; switch to Ollama or a hosted model in
> Settings > AI. A month of conversation history comes from the demo seed.
> `make up && make demo` reproduces it.

<h3 align="center">Built by the team behind Euron</h3>

<p align="center">Euron Open SupportDesk comes from the people who build these platforms. If you like how this repository is built, come and see what we build with it.</p>

<p align="center">
  <a href="https://euron.one"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/euron-dark.svg"><img src="docs/assets/brand/euron-light.svg" alt="Euron: learn the latest technologies from industry experts. Visit euron.one" width="31%"></picture></a>
  <a href="https://euronsystems.com"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/euron-systems-dark.svg"><img src="docs/assets/brand/euron-systems-light.svg" alt="Euron Systems: the SaaS platform for educators and creators. Visit euronsystems.com" width="31%"></picture></a>
  <a href="https://alphaeuron.com"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/alpha-euron-dark.svg"><img src="docs/assets/brand/alpha-euron-light.svg" alt="Alpha Euron: where school kids grow creativity and tech skills with AI. Visit alphaeuron.com" width="31%"></picture></a>
</p>

<p align="center">
  <a href="https://www.instagram.com/euron_official"><img src="https://img.shields.io/badge/Instagram-E4405F?style=flat-square&logo=instagram&logoColor=white" alt="Instagram"></a>
  <a href="https://www.linkedin.com/company/euronone/posts/"><img src="https://img.shields.io/badge/LinkedIn-0A66C2?style=flat-square&logo=linkedin&logoColor=white" alt="LinkedIn"></a>
  <a href="https://x.com/euron712"><img src="https://img.shields.io/badge/X-000000?style=flat-square&logo=x&logoColor=white" alt="X"></a>
  <a href="https://www.youtube.com/@Euron-official"><img src="https://img.shields.io/badge/YouTube-FF0000?style=flat-square&logo=youtube&logoColor=white" alt="YouTube"></a>
  <a href="https://whatsapp.com/channel/0029VaeeJwq9RZAfPW9P2l07"><img src="https://img.shields.io/badge/WhatsApp_channel-25D366?style=flat-square&logo=whatsapp&logoColor=white" alt="WhatsApp channel"></a>
</p>

---

## 📚 Table of contents

- [Why SupportDesk](#-why-supportdesk)
- [At a glance](#-at-a-glance)
- [Screenshots](#️-screenshots)
- [Features](#-features)
- [Architecture](#️-architecture)
- [Tech stack](#-tech-stack)
- [Prerequisites](#-prerequisites)
- [Quickstart](#-quickstart)
- [Explore the repository](#-explore-the-repository)
- [API](#-api)
- [Configuration](#️-configuration)
- [Deploy to AWS](#️-deploy-to-aws)
- [Security model](#-security-model)
- [Performance](#-performance)
- [Testing](#-testing)
- [Documentation](#-documentation)
- [Roadmap](#️-roadmap)
- [FAQ](#-faq)
- [Contributing, security and license](#-contributing-security-and-license)

## 💡 Why SupportDesk

AI support agents are sold per resolution (Intercom publishes $0.99 for Fin; others charge
more), on top of per-seat helpdesk pricing, and every conversation your customers have goes
through someone else's servers. Open-source helpdesks keep the data at home but leave the
AI to you.

SupportDesk is the AI-native version you can run yourself: the helpdesk, the AI agent, the
knowledge base and the economics in one place, under your control, with the decisions that
matter (what may be sent, what needs a person) made by rules you can read and test. It
does three things a support desk has to get right:

1. **Never lose a customer message.** A message and its AI turn are written in one
   transaction; a worker that crashes mid-answer is replaced and the reply is sent once; a
   provider outage hands the conversation to a person instead of dropping it.
2. **Get every conversation to an owner.** The AI or a person, with a clear status, SLA
   targets, routing to available agents with spare capacity, and live updates.
3. **Never guess.** No source, no answer; sensitive requests wait for a person.

## 📊 At a glance

| | |
| --- | --- |
| **Channels** | Website widget (one script tag, any site, identity verification), email (inbound webhook, SES, threading), customer portal (magic link), help center, REST API |
| **AI providers** | Extractive (no model), Ollama, any OpenAI-compatible endpoint (OpenAI, vLLM, LiteLLM, TokenShield), Anthropic |
| **Knowledge** | PDF, DOCX, Markdown, text, HTML, FAQ CSV, web pages and sitemaps (robots.txt honoured), articles written in the app; hybrid retrieval (pgvector plus full text, reciprocal rank fusion) |
| **Policy** | Off, draft only, approval for sensitive intents, auto; allowed categories, relevance threshold, sensitive intents and keywords, VIP, frustration, unhelpful answers, AI turn limit |
| **Token Saver** | Exact and semantic answer caches (keyed on the knowledge version), short context, model routing, daily and monthly token and cost budgets |
| **Helpdesk** | Views, assignment, round-robin routing by capacity, SLAs per priority, canned replies, notes, tags, bulk actions, approvals, CSAT, customer merge |
| **Analytics** | Volume, first response and resolution times, AI resolution, deflection, CSAT, escalation reasons, team workload, cost per AI resolution, CSV |
| **Infrastructure** | 10 Terraform modules, 3 environments; the full AWS stack (179 resources) applied end to end against Floci |
| **Tests** | 133 API unit, 96 web unit, 84 integration (run under 8 backend combinations), 16 browser end-to-end, browser QA over 188 page views |
| **License** | MIT |

## 🖼️ Screenshots

| | |
| --- | --- |
| <img src="docs/assets/screenshots/01-widget-cited-answer.png" alt="The widget on a customer's website answering with its source"><br>**The widget on your website**: answers come from your documents, with sources | <img src="docs/assets/screenshots/02-inbox-handoff.png" alt="An escalated conversation with the AI summary"><br>**Handoff with context**: the reason, the AI's summary, the transcript |
| <img src="docs/assets/screenshots/03-ai-resolved.png" alt="A conversation the AI resolved, with citations"><br>**Resolved by the AI**: citations, the decision and its cost | <img src="docs/assets/screenshots/04-approvals.png" alt="The approvals queue"><br>**Approvals**: refunds and cancellations wait for a person |
| <img src="docs/assets/screenshots/05-knowledge.png" alt="Knowledge sources"><br>**Knowledge**: files, web pages and articles, indexed by the worker | <img src="docs/assets/screenshots/06-playground.png" alt="The playground"><br>**Test a question**: the passages, their scores and the decision |
| <img src="docs/assets/screenshots/07-knowledge-gap.png" alt="A knowledge gap"><br>**Knowledge gaps**: what customers ask that your docs do not answer | <img src="docs/assets/screenshots/08-analytics.png" alt="Analytics"><br>**Analytics**: AI resolution rate, response times, CSAT, deflection, escalation reasons |
| <img src="docs/assets/screenshots/09-policy.png" alt="Policy settings"><br>**Policy**: when the AI may answer on its own | <img src="docs/assets/screenshots/10-widget-designer.png" alt="Widget designer"><br>**Widget designer**: colours, greeting, allowed sites, the snippet |
| <img src="docs/assets/screenshots/11-help-center.png" alt="Help center"><br>**Help center**: your published articles, searchable | <img src="docs/assets/screenshots/12-dark-inbox.png" alt="Dark mode"><br>**Dark mode** |
| <img src="docs/assets/screenshots/13-phone-widget.png" alt="The widget on a phone" width="60%"><br>**The widget on a phone** | <img src="docs/assets/screenshots/14-phone-inbox.png" alt="The inbox on a phone" width="60%"><br>**The inbox on a phone** |

## ✨ Features

#### 🤖 An AI agent that knows when not to answer

- Triage of every message: intent, category, priority, sentiment, language; rules first,
  a model on top, and the model can only add caution.
- Answers grounded in retrieved passages with citations; an answer that cannot be traced
  to a passage above the threshold is never sent.
- Escalation reasons you can see and measure: customer asked for a person, sensitive
  request, frustrated customer, VIP, category needs a person, not covered by the knowledge
  base, unhelpful answer, long AI conversation, provider down, budget spent.
- Approvals for refunds, cancellations, account changes, billing disputes, legal,
  security and data deletion; drafts for agents in any conversation.
- Card numbers and credentials are removed before anything reaches a model.

#### 📚 Knowledge that improves itself

- Upload files, import a page or a sitemap, or write articles; the worker parses, chunks
  and embeds them, and swaps the index atomically.
- The playground runs the real pipeline on a test question.
- Knowledge gaps cluster unanswered questions; an agent's reply becomes the article draft.

#### 💸 Costs you can see

- A ledger of every call; cost per conversation and per AI resolution; cache savings.
- Hard budgets reserved atomically before a call, never exceeded under concurrency; when a
  budget is spent the AI falls back to quoting your docs, or hands over.

#### 🗂️ The helpdesk around it

- Shared inbox with views, search, keyset pagination, bulk actions, live updates over
  WebSockets; routing to online agents with spare capacity; SLAs with breach flags.
- Website widget with origin checks and HMAC identity verification; email in and out with
  threading and loop protection; customer portal and public help center.
- REST API with read and write keys; webhooks signed with HMAC-SHA256, retried with
  backoff, switched off after repeated failure; append-only audit log.

## 🏗️ Architecture

<p align="center">
  <img src="docs/assets/diagrams/architecture.svg" alt="Architecture: customer channels, the web app, the API, the worker, Postgres with pgvector, Redis, S3 and the model providers" width="100%">
</p>

The API stores a customer message and its AI job in one Postgres transaction; workers claim
jobs with `FOR UPDATE SKIP LOCKED` and a lease, are woken by `NOTIFY`, and write results
through a fenced commit, so a crashed worker's job is reclaimed and answered exactly once.
Live updates are small invalidation events over Redis pub/sub (or Postgres `LISTEN/NOTIFY`
without Redis); clients fetch what changed over REST.

### The answer pipeline

<p align="center">
  <img src="docs/assets/diagrams/answer-pipeline.svg" alt="The answer pipeline: store, triage, gate, cache, retrieve, generate, ground, screen, then send, hold for approval, draft or hand over" width="100%">
</p>

[How the AI agent decides](docs/architecture/ai-agent.md) · [High-level design](docs/architecture/HLD.md) · [Low-level design](docs/architecture/LLD.md)

## 🧰 Tech stack

| Layer | Choice |
| --- | --- |
| API and worker | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, uv |
| Data | PostgreSQL 16 with pgvector (HNSW per embedding size), Redis 7 (optional) |
| AI | fastembed (bge-small, ONNX on CPU), Ollama, OpenAI-compatible and Anthropic over plain HTTP |
| Web | Next.js 15, React 19, TypeScript, Tailwind v4, shadcn/ui, TanStack Query |
| Infrastructure | Docker Compose, Floci (local AWS), Terraform (ECS Fargate, RDS, ElastiCache, S3, KMS, SES, CloudWatch) |
| Tests | pytest, Vitest, Playwright, Puppeteer, checkov, tflint |

## 📋 Prerequisites

- Docker with Compose v2 (that is all the stack needs)
- For running tests outside containers: [uv](https://docs.astral.sh/uv/) and Node.js 20 with pnpm

## 🚀 Quickstart

```bash
git clone https://github.com/euron-sde-team/euron-open-supportdesk.git
cd euron-open-supportdesk
make env     # local secrets in deploy/compose/.env
make up      # Postgres, Redis, Floci (S3, KMS, SES), Mailpit, API, worker, web, demo site
make demo    # the "Lumen" demo company, its knowledge, a month of history; prints logins
```

Then:

- **The agent app**: http://localhost:4810, sign in as `maya@lumen.example` with
  `Demo-Pass-2026`.
- **A customer website with the widget**: http://localhost:4815 (a different origin).
- **The help center and portal**: http://localhost:4810/help/lumen.
- **Mail**: http://localhost:4825 (Mailpit catches every email).

Use a local model instead of the bundled mock: `make ollama-pull`, then choose Ollama in
Settings > AI ([zero API key guide](docs/guides/zero-api-key.md)).

Your own company: sign up at http://localhost:4810/signup, upload your docs in Knowledge,
and copy the snippet from Settings > Inboxes into your site.

## 🧭 Explore the repository

| Path | What is there |
| --- | --- |
| [`apps/api/src/supportdesk/ai/`](apps/api/src/supportdesk/ai) | The engine: triage, policy gate, grounding, caches, budgets, ledger, providers |
| [`apps/api/src/supportdesk/knowledge/`](apps/api/src/supportdesk/knowledge) | Parsing, chunking, hybrid retrieval, ingestion jobs |
| [`apps/api/src/supportdesk/tickets/`](apps/api/src/supportdesk/tickets) | Conversations, routing, SLAs, queries |
| [`apps/api/src/supportdesk/channels/`](apps/api/src/supportdesk/channels) | Widget, email, portal, SNS |
| [`apps/api/src/supportdesk/core/jobs.py`](apps/api/src/supportdesk/core/jobs.py) | The transactional job outbox |
| [`apps/api/src/mockai/`](apps/api/src/mockai) | The mock model (OpenAI, Anthropic, Ollama formats, fault modes) |
| [`apps/web/`](apps/web) | The agent app, widget, portal and help center |
| [`apps/web/public/widget.js`](apps/web/public/widget.js) | The embeddable loader |
| [`e2e/`](e2e) | Playwright journeys |
| [`infra/terraform/`](infra/terraform) | Modules and the `local-floci`, `aws-dev`, `aws-prod` environments |
| [`deploy/`](deploy) | Compose files and the demo customer site |

## 🔌 API

The OpenAPI document is [docs/api/openapi.yaml](docs/api/openapi.yaml) (106 operations);
the running API serves it at http://localhost:4830/docs.

```bash
# Create a write key in Settings > API keys, then open a conversation:
curl -s http://localhost:4830/api/v1/tickets \
  -H "authorization: Bearer sdk_..." -H "content-type: application/json" \
  -d '{"customer_email": "pat@example.com", "body": "Where is my order?", "ai": true}'
```

Webhooks carry `X-SupportDesk-Signature: t=<unix>,v1=<hex>`, where `v1` is
HMAC-SHA256 of `<t>.<body>` with the webhook's secret.

## ⚙️ Configuration

Deployment settings are environment variables ([full reference](docs/guides/configuration.md));
each organisation's AI provider, models, policy, budgets and Token Saver are edited in
Settings and stored per organisation. Production refuses to boot with demo secrets,
insecure cookies, a wildcard CORS origin, private URL access, or private AI endpoints while
anyone may sign up.

## ☁️ Deploy to AWS

`infra/terraform/envs/aws-dev` and `aws-prod` build ECS Fargate services (api, worker, web)
behind an ALB with WAF, RDS PostgreSQL with pgvector, ElastiCache, S3 with KMS, Secrets
Manager, SES (with optional inbound mail through SNS) and CloudWatch alarms. Deploys run
migrations first. Nothing here has been applied to a real AWS account; the whole
environment is applied and destroyed against Floci on every `make tf-aws-on-floci`.
[Deploy guide](docs/guides/deploy-aws.md)

## 🔐 Security model

- **Tenant isolation** is structural: every row carries its organisation, every lookup is
  scoped, and the integration suite checks cross-tenant reads and writes return 404.
- **Customers** prove who they are with signed tokens of separate audiences (widget,
  portal); identity verification signs the customer id with your backend's secret;
  addresses typed into the widget never become an identity.
- **Prompt injection** cannot change decisions, because the model is never asked to make
  them; answers are screened again before they are sent.
- **SSRF**: model endpoints, crawled pages and webhooks are checked before the request
  (no metadata, no private addresses in production) and again on the connected peer.
- **Abuse**: rate limits on sign-in, sign-up, widget and portal; sign-in lockout per
  address that never locks the owner out; bodies bounded before parsing.
- **Secrets** are sealed with KMS (or a local key); the audit log is append-only in the
  database.

[Security](docs/architecture/security.md) · [Threat model](docs/architecture/threat-model.md)

## ⚡ Performance

Measured with `make bench` on a 12-core Apple Silicon laptop (load average 3.8 to 6.2
during the run), with the real local embedding model and the bundled mock model, so the
numbers are SupportDesk's own overhead, not a provider's:

| Measure | Result |
| --- | --- |
| Embedding a question (bge-small, CPU) | 2.6 ms p50 |
| Hybrid retrieval (vector plus full text) | 4.8 ms p50 |
| Widget question to answer, extractive (no model) | 70 ms p50, 96 ms p90 |
| Widget question to answer, model path (mock model) | 100 ms p50 |
| Widget question to answer, from the exact cache | 63 ms p50 (no model tokens) |
| Knowledge ingestion | 312 chunks from 45 sources in 5.7 s (55 chunks/s) |
| Messages accepted by the API | 55 per second (200 sent at once) |
| AI turns answered by one worker | 8.8 per second (embedding bound; add workers to scale) |
| WebSocket fan-out to the widget | 8 ms p50 |

With a real model, its own latency (usually 0.5 to 3 s) adds to the model path; a cache
hit skips it entirely. Raw results: [docs/bench.json](docs/bench.json).

## 🧪 Testing

| Suite | What it proves | Run |
| --- | --- | --- |
| Unit (133 API, 96 web) | Policy rules, triage, grounding, redaction, retrieval scoring, chunking, parsing, routing, SLAs, email parsing, tokens, signatures, settings guards; web logic | `make test` |
| Integration (84) | The real API and worker over HTTP against Postgres with pgvector and Redis, with the mock model in every failure mode: every acceptance criterion in [the plan](docs/PLAN.md), tenant isolation, injection, budgets under 50 concurrent questions, a crashed worker's job answered once, email threading, webhooks | `make test-integration` |
| Option matrix (8 x 84) | The integration suite under every backend combination: disk or S3, local key or KMS, Redis on or off | `make test-matrix` |
| Browser (16) | Playwright against the running stack: upload a document and get a cited answer in the widget on another website, hand over and reply live, approvals, email in and out with threading, portal sign-in by magic link, gap to article to answer, every main screen | `make e2e` |
| Browser QA (188 page views) | Every page as visitor, owner, agent and customer, in light and dark, at desktop and phone width: no console errors, failed requests, broken images, error states or overflow | `make qa` |
| Local model | The zero-API-key path against a real Ollama model (qwen2.5 1.5B, 3 tests): it answers from the sources, says NO_ANSWER when they do not cover the question, and triages in JSON mode | `make test-ollama` |
| Infrastructure | `terraform validate` (3 environments), tflint, checkov (333 passed, 0 failed), sanitization (secrets, account ids, em and en dashes) | `make tf-validate tf-lint tf-security sanitize` |
| AWS on Floci | The full production environment plans, applies, converges and destroys against an AWS API | `make tf-aws-on-floci` |

Line coverage of `apps/api/src` from unit plus integration tests: 87% (the CI floor is
85%). [Testing guide](docs/guides/testing.md)

## 📖 Documentation

| Architecture | Guides |
| --- | --- |
| [High-level design](docs/architecture/HLD.md) | [Quickstart (local)](docs/guides/quickstart-local.md) |
| [Low-level design](docs/architecture/LLD.md) | [Zero API key (extractive and Ollama)](docs/guides/zero-api-key.md) |
| [The AI agent](docs/architecture/ai-agent.md) | [Configuration reference](docs/guides/configuration.md) |
| [Knowledge](docs/architecture/knowledge.md) | [Deploy to AWS](docs/guides/deploy-aws.md) |
| [Channels](docs/architecture/channels.md) | [Local against real AWS](docs/guides/local-with-aws.md) |
| [Analytics](docs/architecture/analytics.md) | [Operations runbook](docs/guides/operations.md) |
| [Data model](docs/architecture/data-model.md) | [Testing](docs/guides/testing.md) |
| [Security](docs/architecture/security.md), [threat model](docs/architecture/threat-model.md) | [Troubleshooting](docs/guides/troubleshooting.md) |
| [Decision records](docs/architecture/adr/) | [Product walkthrough](docs/guides/walkthrough.md) |
| [API reference (OpenAPI)](docs/api/openapi.yaml) | [Build plan](docs/PLAN.md), [changelog](CHANGELOG.md) |

## 🗺️ Roadmap

- WhatsApp, Messenger, Telegram, Slack and SMS channels; voice
- AI actions through tools (look up an order, issue a refund after approval)
- Business hours and holidays in SLAs; visual automation rules
- Grounding that weighs rare terms (today a passage that shares common words with the
  question can pass the threshold; a capable model still answers NO_ANSWER, the mock and
  extractive paths do not)
- Multi-language help center; SSO (OIDC, SAML); a Helm chart; a GPU Ollama service in Terraform

Have an idea? [Open a feature request](https://github.com/euron-sde-team/euron-open-supportdesk/issues/new/choose).

## ❓ FAQ

**Do I need an API key?** No. The default provider quotes answers from your documents with
no model at all, and Ollama runs a local model. Hosted models are optional.

**Will the AI promise refunds?** No. Refunds, cancellations, account changes, disputes,
legal, security and data deletion always go to a person (held for approval, or handed
over), decided by rules outside the model; an answer that mentions them unprompted is held
too.

**What does it cost to run?** Your servers, plus whatever your model provider charges. The
analytics page shows the model spend per AI resolution from the ledger (the demo, priced
as gpt-4o-mini, comes to fractions of a cent).

**Can several companies share one installation?** Yes. Every organisation is isolated;
turn off open sign-up (`SIGNUP_ENABLED=false`) for a private installation.

**Is it production ready?** It is built and tested to production standards locally, with
the AWS Terraform validated and applied against an emulator. It has not been run by us on a
real AWS account; review the [operator checklist](docs/architecture/security.md) first.

## 🤝 Contributing, security and license

Contributions are welcome: read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[code of conduct](CODE_OF_CONDUCT.md). Report security issues privately as described in
[SECURITY.md](SECURITY.md).

Released under the [MIT License](LICENSE). Copyright (c) 2026 ENGAGESPHERE TECHNOLOGY
PRIVATE LIMITED and the Euron Open SupportDesk contributors.

<p align="center">
  If SupportDesk answers your customers, <b><a href="https://github.com/euron-sde-team/euron-open-supportdesk/stargazers">⭐ star the repository</a></b>.
</p>
