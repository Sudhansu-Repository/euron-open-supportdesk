# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────────────
# The API, the background worker, the CLI and the mock AI (one image):
#   docker build -f infra/docker/server.Dockerfile --target api -t supportdesk-api apps/api
#
#   supportdesk serve       the API (default command)
#   supportdesk worker      background jobs: AI turns, indexing, mail, webhooks, SLA, rollups
#   supportdesk migrate     database migrations (creates the pgvector extension too)
#   uvicorn mockai.app:app  the deterministic mock LLM for the demo and the tests
#
# The local embedding model (fastembed, BAAI/bge-small-en-v1.5, about 130 MB) is not
# baked in: it downloads once on first use into MODEL_CACHE_DIR, which Compose mounts
# as a named volume shared by the api and the worker (it survives `make down`).
# ─────────────────────────────────────────────────────────────────────────────
ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm

FROM ghcr.io/astral-sh/uv:0.11.19 AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /uvx /bin/
# Fewer parallel downloads and patient reads, so a slow link finishes each wheel instead
# of stalling every stream past the timeout (override with --build-arg).
ARG UV_CONCURRENT_DOWNLOADS=4
ARG UV_HTTP_TIMEOUT=300
# Bytecode is compiled here because the runtime root filesystem is read-only.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv UV_HTTP_RETRIES=8
WORKDIR /src
# Dependencies first (cached until uv.lock changes), then the project itself. --locked
# fails the build if uv.lock is out of date with pyproject.toml instead of re-resolving.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --extra local-embeddings --no-install-project
COPY pyproject.toml uv.lock README.md ./
COPY src src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra local-embeddings --no-editable

FROM ${PYTHON_IMAGE} AS api
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 HOME=/tmp PYTHONDONTWRITEBYTECODE=1 TZ=UTC PORT=8080 \
    MODEL_CACHE_DIR=/var/cache/supportdesk/models HF_HOME=/var/cache/supportdesk/models/hf \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HOME=/app
# tini reaps zombies and forwards SIGTERM, so services drain and finish in-flight work.
RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 supportdesk \
 && useradd --system --uid 10001 --gid supportdesk --home-dir /app --no-create-home \
      --shell /usr/sbin/nologin supportdesk \
 && mkdir -p /app /data/objects /var/cache/supportdesk/models \
 && chown -R supportdesk:supportdesk /app /data/objects /var/cache/supportdesk
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
USER 10001:10001
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
  CMD python -c "import os, sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8080'), timeout=2).status == 200 else 1)"
ENTRYPOINT ["/usr/bin/tini", "--", "supportdesk"]
EXPOSE 8080 4850 9464
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
