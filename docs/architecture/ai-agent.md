# The AI agent

The AI agent answers a customer only when the answer is grounded in the organisation's
knowledge and allowed by its policy. Everything else reaches a person with the transcript,
a summary and the reason. The model writes text; code decides what happens to it.

Code: `apps/api/src/supportdesk/ai/`. The step-by-step pipeline is in
[LLD.md](LLD.md#the-answer-pipeline-step-by-step); this page explains each mechanism.

## Providers

An organisation picks its provider in Settings > AI (`org_settings.ai`). Providers
implement the `ChatModel` Protocol (`ai/providers/base.py`); adding one is a new file and
one line in `ai/registry.py`.

| Provider | What it calls | Default models (answer / triage) | Notes |
| --- | --- | --- | --- |
| `extractive` (default for a new organisation) | Nothing. The best retrieved passage is quoted: the answer half of an FAQ row, or the two or three sentences of the best passage that cover the question best, plus the sentence after the best one | n/a | Zero network calls (`test_extractive_mode_answers_with_a_citation_and_calls_no_model`). Triage uses rules only; summaries are deterministic |
| `ollama` | Ollama's native `POST /api/chat` (`stream: false`, `num_predict`, `format: json` for triage) | `qwen2.5:1.5b` | Base URL defaults to `OLLAMA_URL`. See [zero-api-key.md](../guides/zero-api-key.md) |
| `openai` | `POST {base_url}/chat/completions` (OpenAI wire format, `response_format: json_object` for triage) | `gpt-4o-mini` | Any compatible endpoint: OpenAI, vLLM, Ollama's `/v1`, a LiteLLM proxy, Euron Open TokenShield, Groq, Together ([ADR-0002](adr/0002-no-litellm-dependency.md)) |
| `anthropic` | `POST {base_url}/v1/messages` with `anthropic-version: 2023-06-01`; system prompts joined into `system` | `claude-haiku-4-5` | |

All remote calls go through one helper (`providers/http.py`): `AI_TIMEOUT_S` (default
60 s), no redirects, the URL checked against instance metadata and resolved before the
call (private addresses allowed only with `AI_ALLOW_PRIVATE_ENDPOINTS`), and errors
classified: timeouts, 429 and 5xx are retryable; other 4xx, bad JSON and refused targets
are not. The provider key is sealed (local AES-GCM or KMS, encryption context
`org:<id>:ai_api_key`) and never returned by the API.

`POST /api/v1/org/ai/test` (admin) sends one short request and reports latency and a
sample, so a wrong key or URL shows up in Settings, not in a customer conversation.

## Embedders

| Embedder | Model | Dimensions | Where |
| --- | --- | --- | --- |
| `local` (default) | fastembed ONNX on CPU, `LOCAL_EMBEDDING_MODEL` (default `BAAI/bge-small-en-v1.5`; also `BAAI/bge-base-en-v1.5`, `sentence-transformers/all-MiniLM-L6-v2`, `intfloat/multilingual-e5-small`) | 384 (768 for bge-base) | In the API and worker processes, in a thread. About 130 MB downloaded once into `MODEL_CACHE_DIR`; the worker warms it at start |
| `ollama` | Any Ollama embedding model (`POST /api/embed`) | as configured (`embed_dims`) | Remote |
| `openai` | Any OpenAI-compatible `/embeddings` endpoint | as configured | Remote |
| `hash` | Hashed word unigrams and bigrams | 384 | Tests only; `guard()` refuses it in production |

Vectors are normalised to unit length. Changing the embedder (provider, model or size)
schedules a re-index of every source and published article, because old and new vectors
cannot be compared; until each finishes, retrieval for that content runs on full text.
Sizes with an HNSW index: 384, 768, 1024, 1536 ([data-model.md](data-model.md#vector-indexes)).

## Triage

Every customer message is triaged (`ai/triage.py`) into intent, sensitive intents,
category, priority, sentiment, wants-human and language.

**Rules** (always, zero tokens): phrase patterns per sensitive intent (refund,
cancellation, account change, billing dispute, legal, security, data deletion) plus the
organisation's custom keywords (reported as `custom`); patterns for "talk to a human";
a sentiment score from negative and positive words, shouting and exclamation marks;
urgency and high-priority patterns (a sensitive intent is at least `high`); the category
whose vocabulary matches most; the script-based language (Devanagari, Bengali, Tamil,
Telugu, Arabic, CJK, Hangul, Cyrillic, otherwise `en`).

**Model** (when a chat model is configured and `llm_triage` is on): the triage model gets
the message as fenced data and returns JSON. The merge (`triage.merge`) can **only add
caution**: it may add a known sensitive intent, raise priority, make sentiment more
negative, set wants-human, pick a known category or refine a Latin-script language. It can
never remove a sensitive intent or lower priority the rules found, so a message crafted to
talk the model out of flagging a refund is still flagged
(`test_a_customer_cannot_talk_the_ai_out_of_flagging_a_refund`, `test_merge_only_adds_caution`).
A triage failure falls back to the rules.

## The policy gate and reason codes

`ai/policy.py` is pure functions over plain values; every rule is unit tested and none
asks the model.

**Modes** (`policy.mode`, default `approval`):

| Mode | Behaviour |
| --- | --- |
| `off` | No AI answers; customers get an acknowledgement and a person takes over |
| `draft` | The AI prepares a draft for an agent on every message; nothing is sent by the AI |
| `approval` | In-policy questions are answered; a sensitive intent (and nothing else) waits for an agent's approval |
| `auto` | Like `approval`, but a sensitive intent becomes a draft for a person instead of an approval |

**Gate** (before retrieval), in order: `off` mode or AI disabled on the inbox, the
customer asked for a person, `max_unhelpful` unhelpful marks reached (default 1),
`max_ai_turns` reached (default 6), a spent budget with `on_exhausted = human`: hand over
at once. Then the *prepare* reasons are collected: a sensitive intent in the
organisation's list (or a custom keyword), a VIP customer (`escalate_vip`), negative
sentiment (`escalate_negative_sentiment`), a category outside `auto_categories`. Any of
them means the AI may only prepare an answer for a person.

**Finalize** (after generation): a handover stays a handover; an ungrounded answer is
always an escalation with `no_grounded_answer`; a prepared, grounded answer becomes an
approval (approval mode, sensitive intent the only reason) or a draft; otherwise send.

| Code | Label (`REASON_LABELS`) | Raised by |
| --- | --- | --- |
| `customer_requested` | Customer asked for a person | Triage wants-human, or the widget's "Talk to a person" button |
| `sensitive_intent` | Sensitive request | Triage found an intent in `policy.sensitive_intents` or a custom keyword |
| `negative_sentiment` | Customer is frustrated | Triage sentiment negative, `escalate_negative_sentiment` on |
| `vip_customer` | VIP customer | `customers.vip`, `escalate_vip` on |
| `category_not_allowed` | Category needs a person | Category not in `policy.auto_categories` |
| `no_grounded_answer` | Not covered by the knowledge base | No passage at or above `min_relevance`, `NO_ANSWER`, or an answer that cannot be traced to a passing passage |
| `answer_unhelpful` | AI answer did not help | The customer marked answers unhelpful `max_unhelpful` times |
| `max_ai_turns` | Long AI conversation | `max_ai_turns` AI answers in one conversation |
| `ai_off` | AI is off | Mode `off`, or AI disabled on the inbox |
| `ai_unavailable` | AI provider unavailable | Provider timeout or error on the last attempt, a non-retryable error, or a dead job |
| `budget_exhausted` | AI budget spent | A budget would be exceeded and `on_exhausted = human` |
| `sensitive_answer` (`engine.SENSITIVE_ANSWER`) | none in `REASON_LABELS`; the summary shows the code and the web app humanises it | The answer text mentions a sensitive intent the customer did not raise (outbound screening) |

The reasons are stored on the ticket (`escalation_reasons`), on the handoff message, in the
`escalated` event and the webhook payload, and counted in analytics.

## Grounding

Retrieval ([knowledge.md](knowledge.md)) returns hits with a **relevance** score that is
independent of the fusion rank and explainable:

```
relevance = max(calibrated cosine similarity, coverage)
calibrated = clamp((cosine - floor) / (ceiling - floor), 0, 1)
coverage   = share of the question's content words found in the passage (title, heading, text)
```

Calibration per embedder family: bge models `(0.55, 0.85)` (they place unrelated text
around 0.5), the test hash embedder `(0.05, 0.75)`, anything else `(0.35, 0.80)`. A passage
must reach `policy.min_relevance` (default 0.5) to be shown to the model and to be cited.

The answer prompt numbers the passages `[1]`, `[2]` and asks for citations and for
exactly `NO_ANSWER` when the sources do not answer. `answer.validate` then decides:

1. Empty, or `NO_ANSWER` within the first 40 characters: not answered.
2. Citation markers that point at passages scoring at or above the threshold: grounded,
   the markers are stripped and the cited passages become the citations.
3. **Overlap fallback** for a model that forgot its markers (and only then): grounded if
   at least 50% of the answer's content words appear in one passing passage
   (`test_uncited_but_faithful_answer_is_grounded_by_overlap`).
4. Anything else, including markers pointing at low-scoring or non-existent passages:
   not grounded. An ungrounded answer is never shown to the customer
   (`test_an_ungrounded_answer_is_never_sent`); the customer gets an honest handoff and a
   knowledge gap is recorded.

Citations carry `chunk_id`, `source_id` or `article_id`, `title`, `heading`, `url` (a deep
link such as `#page=3` for PDFs, or the help center article URL) and `relevance`.

## Outbound screening

After a grounded answer, the triage rules run on the **answer text**. If it mentions a
sensitive intent (refund, cancellation, account change and so on) the customer did not
raise, the decision changes from send to prepare with `sensitive_answer`: an approval in
approval mode, a draft otherwise. This catches a poisoned document that tells the model to
promise refunds (`test_instructions_in_a_document_cannot_get_a_refund_promise_sent`, run
against the mock AI's `obedient` mode, which follows instructions found in sources).

## Prompt injection stance

Prompts label customer text and knowledge passages as data (fenced with `<<<` and `>>>`)
and tell the model to ignore instructions inside them. That is a mitigation, not the
defence. The defence is that nothing the model writes can trigger an action:

- the model never decides to send, approve, refund or escalate; `policy.gate` and
  `policy.finalize` do, from triage rules and scores;
- the model cannot remove a sensitive flag (the merge only adds caution);
- an answer must trace back to a passage that scored above the threshold;
- the answer itself is screened for sensitive topics before it can be sent;
- there are no tools: the model has no way to call an API or read other data.

What remains possible: a poisoned source can make the model write wrong but harmless
text that is grounded in that same source (it is cited, so an agent can find and fix the
source), and a prompt can make a model refuse or answer `NO_ANSWER`, which hands over.
Only admins can add knowledge sources.

## Redaction

`ai/redact.py` runs on the question and the history before any model call, local or
remote, and before anything enters the answer cache. It replaces payment card numbers
(13 to 19 digits that pass the Luhn check), `sk-` and `sk-ant-` keys, AWS access key ids,
GitHub and Slack tokens, JWTs, and `password:`, `pin=`, `otp:` style values. The
original message stays in the conversation for the agent.

Note: knowledge gap article drafts (`gaps/service.py`) send agent replies and customer
questions to the model without redaction.

## Token Saver

| Mechanism | How | Setting (default) |
| --- | --- | --- |
| Exact cache | SHA-256 of the normalised question (lower case, no punctuation, no stopwords), keyed by organisation and `kb_version`; KV first, Postgres second | `token_saver.exact_cache` (on), `cache_ttl_hours` (336) for the KV copy |
| Semantic cache | Cosine similarity of the question embedding against previous cached questions with the same `kb_version` and size | `semantic_cache` (on), `semantic_threshold` (0.92) |
| First question only | Caches are read and written only for the first question of a conversation, where the answer cannot depend on earlier turns, and only when the gate says proceed | fixed |
| What is cached | Only grounded, model-generated answers that were sent; one a customer marks unhelpful is disabled for good | fixed |
| Context budget | Passages above the threshold are added best first until `context_tokens` would be exceeded (at least one) | `ai.context_tokens` (1800), `ai.top_k` (5) |
| Short history | The last `history_turns` turns verbatim, older customer turns folded into one line of at most 120 tokens | `token_saver.history_turns` (6) |
| Model routing | Triage and summaries use `triage_model`, answers and drafts use `answer_model` | `ai.triage_model`, `ai.answer_model` |
| Rules triage | Turn off LLM triage to classify with zero tokens | `ai.llm_triage` (on) |
| Bounded output | `max_answer_tokens` per answer; triage 120, summaries 150, drafts 500 | `ai.max_answer_tokens` (400) |

A cache hit is recorded in the ledger with zero tokens, `cache = exact|semantic` and the
tokens and cost it saved (the original answer's), and counts in the dashboard's savings.

### Hard budgets

`org_settings.budgets` sets daily and monthly token and USD limits (0 means unlimited) and
what happens when one is spent (`on_exhausted`: `extractive` or `human`).

Every model call (triage, answer, summary, draft, playground) goes through
`Engine.call`:

1. Estimate input tokens (about 3.5 characters per token for ASCII, more for other
   scripts) and take the worst case: estimate plus `max_tokens`, priced at the model's
   price.
2. **Reserve** in both the daily and the monthly `budget_usage` row with one conditional
   `UPDATE ... SET reserved = reserved + :n WHERE used + reserved + :n <= limit RETURNING id`.
   Postgres locks the row and re-checks the condition against the latest committed values,
   so concurrent callers cannot jointly overspend. Both periods or neither (the first
   reservation is rolled back if the second fails). The reservation commits at once and
   is not held across the call.
3. A refused reservation records a `budget_blocked` ledger row and returns no text: the
   answer falls back to extractive or a handoff, as configured; the customer never sees
   an error.
4. After the call (success or failure) the reservation is **settled** to what the
   provider reported.

`test_hard_budget_is_never_exceeded_under_concurrency` fires 50 concurrent questions at a
tight budget and checks the spend never passes it.

Not covered by the reservation: the knowledge gap article draft calls the model directly
and is recorded in the ledger but not reserved against the budget.

## The ledger and cost per AI resolution

`llm_calls` has one row per model call or avoided call: purpose, provider, model, input
and output tokens, cost (from `model_prices`, editable per organisation in Settings > AI;
built-in defaults for `gpt-4o-mini` at $0.15 / $0.60 and `claude-haiku-4-5` at $1.00 /
$5.00 per million tokens; `extractive` and `ollama` cost 0), cache kind and savings,
latency, status and error. Ticket totals (`ai_tokens`, `ai_cost_usd`) are updated in the
same transaction as the AI turn.

**Cost per AI resolution** = all model spend in the period (including failed attempts,
escalated conversations, drafts, triage and the playground) divided by the conversations
resolved by AI in the period. The dashboard shows it next to Intercom Fin's published
$0.99 per resolution. Definitions: [analytics.md](analytics.md).
