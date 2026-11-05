# Contributing

Thanks for helping improve Euron Open SupportDesk. This guide covers the workflow, the bar a
change has to clear, and the conventions the codebase follows.

## Ground rules

- **Open an issue first** for anything larger than a bug fix or a docs tweak, so we can
  agree on the approach before you invest time.
- **One concern per pull request.** A refactor and a feature are two PRs.
- **Security issues go through private reporting**, never a public issue. That includes
  any way to read another organisation's data, to make the AI send something policy should
  have held, or to reach internal addresses from the server. See [SECURITY.md](SECURITY.md).
- By contributing you agree your work is released under the [MIT License](LICENSE).

## Development setup

Requirements: Docker, Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 and
pnpm 9 (`corepack enable`).

```bash
make up          # Postgres (pgvector), Redis, Mailpit, Floci (provisioned by Terraform), mock AI, api, worker, web, demo site
make demo        # the Lumen demo company: agents, knowledge, a month of conversations, analytics
make test        # unit tests (API and web)
```

[docs/guides/quickstart-local.md](docs/guides/quickstart-local.md) walks through the local
stack in detail.

## Before you open a pull request

Each of these must pass:

```bash
make lint typecheck test
make test-integration                  # the API and worker against real Postgres and Redis
make test-matrix                       # when you touched storage, sealing, caches or live events
make e2e                               # when you touched a web flow
make tf-validate tf-lint tf-security   # when you touched infra/terraform
make tf-aws-on-floci                   # same: apply and destroy aws-dev against Floci
make openapi                           # when you changed an endpoint (the drift test checks it)
make sanitize                          # no credentials, account ids, hostnames or dashes
```

## Conventions

**Package by domain.** `apps/api/src/supportdesk/<domain>/` owns its `router.py` (HTTP
only), `schemas.py` (the public contract), `service.py` (rules) and `models.py`.
Dependencies point inward. A domain calls another domain's service, never its tables.

**Tenant scoping is not optional.** Every query on a tenant-owned table filters by
`org_id`; every lookup by id checks the row's organisation before returning it. Add an
integration test that a second organisation cannot see the new data.

**Policy stays outside the model.** Whether an AI answer is sent, held or escalated is
decided in `ai/policy.py` from deterministic inputs. Do not add a code path where model
output chooses an action, and do not let model triage remove caution the rules found
(see [ADR-0008](docs/architecture/adr/0008-policy-outside-the-model.md)). New reason codes
get a label in `REASON_LABELS` and in `apps/web/src/lib/labels.ts`.

**Every model call goes through `Engine.call`.** It reserves budget before the call,
records the ledger row and settles afterwards. Text sent to a model is redacted first.

**Work that follows a change is a job in the same transaction.** Use `core.jobs.enqueue`
in the caller's session (with a `dedupe_key` when a retry could enqueue twice), write
results through `JobContext.fenced()`, and keep handlers idempotent. Live events go
through `core.events.emit` so they are published only after commit.

**Providers plug in behind Protocols.** A new model provider is one file in
`ai/providers/` implementing `ChatModel` or `Embedder`, one line in `ai/registry.py`, and
support in the mock AI for the integration tests.

**Configuration is validated.** A new setting goes in `core/config.py`, is documented in
[docs/guides/configuration.md](docs/guides/configuration.md) in the same PR, and
security-relevant ones are enforced by `guard()` at boot.

**Database changes are new migrations.** Change the models, then autogenerate a revision
with `uv run supportdesk revision -m "what changed"` against a local database and review
it. Never edit an applied one. Indexes for every new filter the API exposes belong in the
same revision.

**Comments explain why.** The code says what it does. Comments are for the constraint,
the incident, or the trade-off that made it this way.

**Style.** ruff and mypy `--strict` for Python; ESLint and TypeScript strict for the web.
No em dashes or en dashes anywhere (the sanitization check enforces it).

## Commit messages

Imperative mood with an optional scope: `ai: screen answers for sensitive topics`,
`web: show the handoff reason in the inbox`. Explain the why in the body when it is not
obvious.

## Architecture decisions

Significant decisions are recorded in [docs/architecture/adr/](docs/architecture/adr/).
If your change reverses or extends one, add a new ADR rather than editing the old one.
