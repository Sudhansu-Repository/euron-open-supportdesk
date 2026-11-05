# ADR-0009: Local embeddings by default

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

Retrieval needs embeddings for every chunk and every question. The promise is a support
desk that works with no API key and sends no customer text to a third party unless the
organisation chooses to.

## Decision

The default embedder is fastembed running `BAAI/bge-small-en-v1.5` (384 dimensions) on
ONNX Runtime on the CPU, inside the API and worker processes, in a thread. The model
(about 130 MB) is downloaded once into `MODEL_CACHE_DIR`, a Compose volume that survives
`make down`; the worker warms it at start. Organisations may switch to an Ollama or
OpenAI-compatible embedder. A deterministic hash embedder exists for tests only and the
production guard refuses it.

## Consequences

**Good**
- Zero-API-key mode is real: knowledge is indexed and searched with no outbound call
  (`test_extractive_mode_answers_with_a_citation_and_calls_no_model`).
- No GPU needed; small enough for a single small server.

**Bad / caveats**
- English-first quality; `intfloat/multilingual-e5-small` is supported for other
  languages.
- The first start downloads the model; a slow route makes the first ingest slow
  ([troubleshooting.md](../../guides/troubleshooting.md)).
- Embedding runs on the API's and worker's CPU.

## Alternatives considered

- **OpenAI embeddings by default**: better quality per dimension, but needs a key and
  sends text out.
- **sentence-transformers with PyTorch**: heavier image for the same models.
