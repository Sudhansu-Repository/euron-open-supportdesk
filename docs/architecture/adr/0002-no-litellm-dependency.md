# ADR-0002: No LiteLLM dependency

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

The brief suggested LiteLLM to reach many model providers. Most hosted and self-hosted
inference servers speak the OpenAI chat completions wire format: OpenAI, vLLM, Ollama's
`/v1`, Groq, Together, a LiteLLM proxy and Euron Open TokenShield.

## Decision

Ship four providers written against the wire formats directly with `httpx`: `extractive`
(no model), `ollama` (native API), `openai` (any OpenAI-compatible endpoint, configurable
base URL) and `anthropic` (Messages API). Users who want LiteLLM's routing run the LiteLLM
proxy and point the `openai` provider at it.

## Consequences

**Good**
- One HTTP helper enforces timeouts, no redirects, SSRF checks and retryable error
  classification for every provider.
- No large SDK in the image; token counts come from the providers' own usage fields.

**Bad / caveats**
- Providers with their own formats (Bedrock's native API, Gemini's native API) need an
  OpenAI-compatible gateway or a new provider file.

## Alternatives considered

- **LiteLLM as a library**: broad coverage, but a heavy dependency with frequent releases,
  and its abstractions would sit between our budget checks and the HTTP call.
- **Official SDKs per provider**: more code paths to secure and test for the same calls.
