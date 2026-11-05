# Euron Open SupportDesk: developer entry points. `make` lists every target.
SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

COMPOSE_DIR := deploy/compose
FLOCI       := docker compose --env-file $(COMPOSE_DIR)/.env -f $(COMPOSE_DIR)/compose.yaml -f $(COMPOSE_DIR)/compose.floci.yaml
AWS_LOCAL   := docker compose --env-file $(COMPOSE_DIR)/.env -f $(COMPOSE_DIR)/compose.yaml -f $(COMPOSE_DIR)/compose.aws.yaml
API         := cd apps/api &&
WEB         := cd apps/web &&
TF_IMAGE    := hashicorp/terraform:1.16.6
TF_ENVS     := local-floci aws-dev aws-prod
# Use a local terraform when installed, otherwise the pinned container (providers cached
# in a named volume, so repeated runs do not download them again).
TF          := $(shell command -v terraform >/dev/null 2>&1 && echo terraform || echo docker run --rm -v $(CURDIR)/infra/terraform:/infra -v supportdesk-tf-plugins:/plugins -e TF_PLUGIN_CACHE_DIR=/plugins -w /infra $(TF_IMAGE))
TF_ROOT     := $(shell command -v terraform >/dev/null 2>&1 && echo infra/terraform || echo /infra)
ENV         ?= aws-dev
# Host ports, overridable in deploy/compose/.env (the same variables compose reads).
envport      = $(or $(shell grep -s '^$(1)=' $(COMPOSE_DIR)/.env | cut -d= -f2),$(2))
WEB_PORT     = $(call envport,SD_WEB_PORT,4810)
API_PORT     = $(call envport,SD_API_PORT,4830)
DEMO_PORT    = $(call envport,SD_DEMO_PORT,4815)
MAIL_PORT    = $(call envport,SD_MAILPIT_PORT,4825)
PG_PORT      = $(call envport,SD_PG_PORT,4842)
REDIS_PORT   = $(call envport,SD_REDIS_PORT,4879)
FLOCI_PORT   = $(call envport,SD_FLOCI_PORT,4866)
OLLAMA_PORT  = $(call envport,SD_OLLAMA_PORT,4834)
MOCK_AI_PORT = $(call envport,SD_MOCK_AI_PORT,4850)
# The seeded demo logins' password (published, not a secret); the seed, e2e, qa and test-stack use it.
DEMO_PW      = $(or $(shell grep -s '^SD_DEMO_PASSWORD=' $(COMPOSE_DIR)/.env | cut -d= -f2),Demo-Pass-2026)
OLLAMA_MODEL ?= qwen2.5:1.5b
# The integration suite's own databases on the Compose Postgres (never the app's).
TEST_ENV     = TEST_DATABASE_URL=postgresql+asyncpg://supportdesk:supportdesk@localhost:$(PG_PORT)/supportdesk_test \
               TEST_REDIS_URL=redis://localhost:$(REDIS_PORT)/15

.PHONY: help env up up-aws down logs ps demo admin test test-integration test-matrix test-stack test-ollama \
        e2e qa screenshots bench lint typecheck build openapi sanitize tf-fmt tf-validate tf-lint tf-security \
        tf-aws-on-floci aws-deploy aws-migrate aws-admin aws-plan backup restore ollama-pull send-test-email clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n\n"} /^[a-zA-Z0-9_-]+:.*##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ─── Local ───────────────────────────────────────────────────────────────────

env: ## Generate deploy/compose/.env with random local-only secrets
	@scripts/gen-local-env.sh

up: env ## Start everything on emulated AWS (Floci), provisioned by the same Terraform as production
	$(FLOCI) up -d --build --wait
	@echo ""
	@echo "  app        http://localhost:$(WEB_PORT)"
	@echo "  api docs   http://localhost:$(API_PORT)/docs"
	@echo "  demo site  http://localhost:$(DEMO_PORT)   (a customer website with the chat widget)"
	@echo "  mail       http://localhost:$(MAIL_PORT)   (every email the app sends lands here)"
	@echo ""
	@echo "  Next: make demo   (the Lumen demo company: agents, knowledge, conversations, history)"
	@echo "  Local LLM (optional): docker compose --profile ollama ... see make ollama-pull"

up-aws: env ## Start the stack against real AWS resources (needs deploy/compose/.env.aws)
	@test -f $(COMPOSE_DIR)/.env.aws || { echo "copy $(COMPOSE_DIR)/.env.aws.example to .env.aws first"; exit 1; }
	$(AWS_LOCAL) up -d --build --wait

demo: ## Seed the Lumen demo company, print the logins, and wire the demo site's widget key
	$(FLOCI) exec -T api supportdesk seed-demo
	@scripts/demo-site-config.sh "http://localhost:$(API_PORT)"
	@echo ""
	@echo "  Sign in at http://localhost:$(WEB_PORT) with a login above"
	@echo "  Try the widget on http://localhost:$(DEMO_PORT)"

admin: ## Create an organisation and its owner, or reset an owner (EMAIL=you@example.com; prompts for the password)
	@test -n "$(EMAIL)" || { echo "usage: make admin EMAIL=you@example.com [ORG='My Company']"; exit 1; }
	$(FLOCI) exec api supportdesk create-owner --email "$(EMAIL)" --org "$(or $(ORG),My Company)"

backup: ## Back up the local stack: Postgres dump and the objects bucket, into backups/
	@scripts/backup.sh

restore: ## Restore a backup into the running stack (BACKUP=backups/<timestamp>)
	@test -n "$(BACKUP)" || { echo "usage: make restore BACKUP=backups/<timestamp>"; exit 1; }
	@scripts/restore.sh "$(BACKUP)"

ollama-pull: ## Start the optional Ollama service and pull the zero-API-key model (OLLAMA_MODEL=qwen2.5:1.5b)
	$(FLOCI) --profile ollama up -d --wait ollama
	$(FLOCI) --profile ollama exec -T ollama ollama pull $(OLLAMA_MODEL)
	@echo "  Ollama on http://localhost:$(OLLAMA_PORT) (http://ollama:11434 inside the stack), model $(OLLAMA_MODEL)"

send-test-email: ## POST a sample email to an email inbox (TOKEN=<inbound token from Settings > Inboxes>)
	@test -n "$(TOKEN)" || { echo "usage: make send-test-email TOKEN=<inbound token> [FROM=customer@example.com]"; exit 1; }
	@scripts/send-test-email.sh "$(TOKEN)" "$(FROM)"

down: ## Stop the stack (the Ollama models and the embedding model cache survive; data is deleted)
	-$(FLOCI) --profile ollama down --remove-orphans
	-docker volume rm supportdesk_pgdata supportdesk_redisdata supportdesk_objects supportdesk_flocidata supportdesk_tfdata 2>/dev/null
	-$(AWS_LOCAL) down --remove-orphans 2>/dev/null

logs: ## Tail logs (SERVICE=api|worker|web|demo-site|floci|terraform|migrate|mockai|mailpit)
	$(FLOCI) logs -f --tail 100 $(SERVICE)

ps: ## Show stack status
	$(FLOCI) ps

# ─── Quality ─────────────────────────────────────────────────────────────────

lint: ## Lint the API (ruff) and the web app (eslint)
	$(API) uv run ruff check src tests && uv run ruff format --check src tests
	$(WEB) pnpm lint

typecheck: ## Typecheck the API (mypy --strict) and the web app (tsc)
	$(API) uv run mypy --strict src
	$(WEB) pnpm typecheck

test: ## Unit tests: API (pytest) and web (vitest). No database, no network
	$(API) uv run pytest tests/unit -q
	$(WEB) pnpm test

test-integration: ## API integration tests against real Postgres (pgvector) and Redis (started if needed)
	@scripts/test-db.sh
	$(API) $(TEST_ENV) uv run pytest tests/integration -m integration -q --cov --cov-report=term-missing:skip-covered

test-matrix: ## Integration tests under every backend: storage local|s3 x keys local|kms x Redis on|off
	@scripts/test-matrix.sh

test-stack: ## Acceptance tests against the running stack (make up && make demo first)
	$(API) SD_STACK=1 SD_API_URL=http://localhost:$(API_PORT) SD_MAILPIT_URL=http://localhost:$(MAIL_PORT) \
	  SD_DEMO_PASSWORD='$(DEMO_PW)' uv run pytest tests/stack -m stack -q

test-ollama: ## Zero-API-key acceptance against a real Ollama (make ollama-pull first)
	$(API) OLLAMA_URL=http://localhost:$(OLLAMA_PORT) OLLAMA_MODEL=$(OLLAMA_MODEL) uv run pytest tests/ollama -m ollama -q

e2e: ## Browser end-to-end tests (Playwright) against the running stack (make up && make demo)
	cd e2e && pnpm install --frozen-lockfile && pnpm exec playwright install chromium && \
	  WEB_URL=http://localhost:$(WEB_PORT) MAILPIT_URL=http://localhost:$(MAIL_PORT) \
	  E2E_DEMO_SITE_URL=http://localhost:$(DEMO_PORT) SD_DEMO_PASSWORD='$(DEMO_PW)' E2E_PASSWORD='$(DEMO_PW)' pnpm test

qa: ## Browser QA sweep (Puppeteer): every page, light and dark, desktop and phone
	cd scripts/qa && pnpm install --frozen-lockfile && \
	  QA_BASE=http://localhost:$(WEB_PORT) QA_MAILPIT=http://localhost:$(MAIL_PORT) QA_DEMO_SITE_URL=http://localhost:$(DEMO_PORT) \
	  SD_DEMO_PASSWORD='$(DEMO_PW)' QA_PASSWORD='$(DEMO_PW)' node qa.mjs

screenshots: ## Curated screenshots (docs/assets/screenshots) and the tour GIF, from the seeded stack
	cd scripts/qa && pnpm install --frozen-lockfile && \
	  QA_BASE=http://localhost:$(WEB_PORT) QA_MAILPIT=http://localhost:$(MAIL_PORT) QA_DEMO_SITE_URL=http://localhost:$(DEMO_PORT) \
	  SD_DEMO_PASSWORD='$(DEMO_PW)' QA_PASSWORD='$(DEMO_PW)' node screenshots.mjs && ./make-tour.sh

bench: ## Benchmarks (answer latency per step, ingest, messages per second) into docs/bench.json
	@scripts/test-db.sh
	@mkdir -p $(CURDIR)/.cache/models
	$(API) BENCH_DATABASE_URL=postgresql+asyncpg://supportdesk:supportdesk@localhost:$(PG_PORT)/supportdesk_bench \
	  BENCH_REDIS_URL=redis://localhost:$(REDIS_PORT)/14 MODEL_CACHE_DIR=$(CURDIR)/.cache/models \
	  uv run python bench.py --json ../../docs/bench.json

build: ## Build the container images
	$(FLOCI) build

openapi: ## Regenerate docs/api/openapi.yaml from the FastAPI app
	@mkdir -p docs/api
	$(API) uv run supportdesk openapi > ../../docs/api/openapi.yaml

sanitize: ## Scan committable files for credentials, cloud identifiers and em/en dashes
	@scripts/check-sanitization.sh

# ─── Terraform ───────────────────────────────────────────────────────────────

tf-fmt: ## Format all Terraform
	$(TF) fmt -recursive $(TF_ROOT)

tf-validate: ## terraform validate every environment (no backend, no credentials)
	@for env in $(TF_ENVS); do \
	  echo "== $$env"; \
	  $(TF) -chdir=$(TF_ROOT)/envs/$$env init -backend=false -input=false -no-color >/dev/null && \
	  $(TF) -chdir=$(TF_ROOT)/envs/$$env validate -no-color || exit 1; \
	done

tf-lint: ## tflint every module and environment (plugins cached in a docker volume)
	docker run --rm -v $(CURDIR)/infra/terraform:/data -v supportdesk-tflint:/plugins -e TFLINT_PLUGIN_DIR=/plugins -w /data ghcr.io/terraform-linters/tflint:v0.64.0 --init
	docker run --rm -v $(CURDIR)/infra/terraform:/data -v supportdesk-tflint:/plugins -e TFLINT_PLUGIN_DIR=/plugins -w /data ghcr.io/terraform-linters/tflint:v0.64.0 --recursive --format compact

tf-security: ## checkov policy scan of the Terraform (every skip carries its reason inline)
	docker run --rm -v $(CURDIR)/infra/terraform:/tf -w /tf bridgecrew/checkov:3.3.30 -d /tf --config-file /tf/.checkov.yaml

tf-aws-on-floci: ## Plan, apply, re-plan and destroy the full aws-dev environment against a throwaway Floci (port 4896)
	@scripts/tf-aws-on-floci.sh

aws-deploy: ## One shot, migrate first: registries, images, infrastructure, migrations, rollout (ENV=aws-dev|aws-prod TAG=...)
	@test -n "$(TAG)" || { echo "usage: make aws-deploy ENV=aws-dev TAG=0.1.0"; exit 1; }
	@scripts/aws-deploy.sh $(ENV) $(TAG)

aws-migrate: ## Run database migrations as a one-off ECS task (ENV=...)
	@scripts/aws-run-task.sh $(ENV) migrate

aws-admin: ## Create the first owner as a one-off ECS task (ENV=... EMAIL=...; SUPPORTDESK_OWNER_PASSWORD in your env)
	@test -n "$(EMAIL)" || { echo "usage: SUPPORTDESK_OWNER_PASSWORD=... make aws-admin ENV=aws-dev EMAIL=you@example.com [ORG='Acme']"; exit 1; }
	@test -n "$$SUPPORTDESK_OWNER_PASSWORD" || { echo "set SUPPORTDESK_OWNER_PASSWORD (at least 10 characters, upper and lower case and a digit)"; exit 1; }
	@scripts/aws-run-task.sh $(ENV) create-owner --email "$(EMAIL)" --org "$(or $(ORG),My Company)"

aws-plan: ## terraform plan for ENV (aws-dev | aws-prod); needs terraform.tfvars and AWS credentials
	cd infra/terraform/envs/$(ENV) && terraform init -input=false && terraform plan

clean: ## Remove build output and caches
	rm -rf apps/web/.next apps/api/.pytest_cache apps/api/.mypy_cache apps/api/.ruff_cache apps/api/.coverage \
	  e2e/test-results e2e/playwright-report scripts/qa/output
