# Zero-API-key mode

SupportDesk runs with no API key and no outbound model call. Two tiers, both self-hosted:

| Tier | Answers | Triage and summaries | Needs |
| --- | --- | --- | --- |
| **Extractive** (the default for a new organisation) | The best retrieved passage, quoted: the answer half of an FAQ row, or the two or three sentences of the best passage that cover the question best | Deterministic rules | Nothing beyond the stack |
| **Ollama** | A local model writes the answer from the retrieved passages, with citations | The local model, merged with the rules (it can only add caution) | The `ollama` Compose profile and a pulled model |

In both tiers the embeddings are computed locally (fastembed, `BAAI/bge-small-en-v1.5`,
ONNX on the CPU), so indexing and search make no network calls either. Policy, grounding,
redaction, escalation and the ledger work the same as with a hosted model.

## Extractive

Settings > AI > provider **Extractive**. That is all. Every answer is a citation by
construction: it is the cited passage. `test_extractive_mode_answers_with_a_citation_and_calls_no_model`
proves the process makes no request to any model endpoint.

What to expect:

- Very good for FAQ-shaped knowledge (CSV rows, articles with one answer per section) and
  instant (retrieval only).
- The wording is the document's, not conversational, and it does not combine facts from
  two passages or follow up on earlier turns.
- The same grounding threshold applies: when nothing scores above `min_relevance`, the
  customer gets an honest handoff.
- It is also the fallback when a budget is spent (`on_exhausted = extractive`).

## Ollama

```bash
make up                 # if the stack is not running
make ollama-pull        # starts the ollama profile and pulls qwen2.5:1.5b (OLLAMA_MODEL=... for another)
```

Then Settings > AI:

- provider **Ollama**;
- base URL: leave empty to use `OLLAMA_URL` (`http://ollama:11434` inside the stack);
- answer and triage model `qwen2.5:1.5b` (the default), or what you pulled;
- **Test connection**.

The model files live in the `ollama` volume, which survives `make down`. The Ollama API
is also on http://localhost:4834 for your own checks. `make test-ollama` runs the tests
marked for a real Ollama against it.

Embeddings stay local (fastembed) unless you also pick the `ollama` embedder with an
embedding model and its size (changing the embedder re-indexes everything).

### Quality and speed on a CPU

Be realistic about small local models:

- `qwen2.5:1.5b` on a laptop CPU typically takes several seconds per answer, longer for
  the first request while the model loads, and more with long contexts. Lower
  `context_tokens` and `max_answer_tokens`, and turn off **LLM triage** (rules only) to
  save one model call per message.
- Small models forget citation markers or answer loosely more often than hosted models.
  The grounding check catches answers it cannot trace to a passage (they become handoffs,
  not wrong answers), so expect more escalations; the overlap fallback accepts faithful
  answers without markers.
- If answers time out, raise `AI_TIMEOUT_S` (default 60 s); timeouts are retried, then
  handed to a person with `ai_unavailable`.
- A GPU, or a larger model on a bigger machine, improves both. Any OpenAI-compatible
  local server (vLLM, llama.cpp server, Ollama's `/v1`) also works through the `openai`
  provider.

Compare the tiers on your own content with Knowledge > **Test a question**, which shows the
decision, the passages and the timings per step for the current provider.

## Privacy

With either tier, customer messages, knowledge and embeddings never leave your servers.
Card numbers and secrets are redacted before any model call even when the model is local.
