# Troubleshooting

## The widget does not appear, or says the site is not allowed

| Symptom | Cause | Fix |
| --- | --- | --- |
| Blank frame where the chat should be; the browser console mentions `frame-ancestors` | The page's origin is not in the inbox's allowed origins, so the browser refuses to embed the frame | Settings > Inboxes > Website chat > allowed origins: add the exact origin (`https://www.example.com`, with the port if not 443/80). Changes reach each web replica within 60 s (the frame policy cache) |
| "This website is not allowed to use this chat widget" | The API refused the `Origin` or the reported parent origin (`origin_not_allowed`) | Same fix. `http` and `https`, `www` and the bare domain are different origins |
| No launcher at all | `widget.js` did not load, or the `data-key` attribute is missing | Check the script tag (`<script src="https://<app>/widget.js" data-key="pk_..." async>`) and the browser console |
| "This chat widget is not active" | Unknown key, or the inbox is switched off | Copy the snippet again from Settings > Inboxes; check the inbox is active |
| "This chat needs a signed-in customer" | **Identity required** is on and the page did not identify the customer | Add `data-user-id` and `data-user-hash` to the script tag (or call `SupportDesk.identify(...)`), or turn identity required off; you can also call the session endpoint from your own client with `external_id` and `signature` ([channels.md](../architecture/channels.md#identity-verification)) |
| "The customer's identity signature is wrong" | The HMAC was computed with another secret, over another string, or not in lower-case hex | Use the current identity secret and sign exactly the `external_id` sent |
| "You are sending messages too quickly" | `WIDGET_RPM` | Raise it if real customers hit it |

Locally, the demo inbox allows `http://localhost:4810` and `http://localhost:4815`.

## The first start is slow, or ingestion hangs at "processing"

The worker downloads the embedding model (fastembed `BAAI/bge-small-en-v1.5`, about
130 MB) on its first start into the `models` volume; later starts reuse it, even after
`make down`. On a slow route the first uploads wait for it. Check
`make logs SERVICE=worker` for "embedding model warm-up failed"; the model then loads on
first use. A source that stays `failed` shows the reason on the Knowledge page; fix the
cause and re-index.

Ollama models are larger (about 1 GB for `qwen2.5:1.5b`): `make ollama-pull` prints
progress.

## The AI always hands over

Open the conversation's AI panel (reasons, best relevance, method) or ask the same
question in Knowledge > **Test a question**, which shows every retrieved passage with its
similarity, coverage and relevance and the threshold.

| Reason shown | What to check |
| --- | --- |
| `no_grounded_answer` with a best relevance just under the threshold | `min_relevance` (Settings > Policy, default 0.5) may be too strict for your content; lower it a little and re-test |
| `no_grounded_answer` with no relevant passage | The knowledge base does not cover it: check Knowledge gaps and write the article |
| `no_grounded_answer` with a good passage | The model answered `NO_ANSWER` or without usable citations: try another answer model, or the extractive provider to confirm retrieval is fine |
| `category_not_allowed` | The triaged category is not in `auto_categories` |
| `sensitive_intent`, `sensitive_answer` | Working as intended: these need a person (approval in approval mode) |
| `negative_sentiment`, `vip_customer` | Policy switches `escalate_negative_sentiment`, `escalate_vip` |
| `ai_off` | Policy mode `off`, or AI disabled on the inbox (the API inbox is off by default) |
| `ai_unavailable` | The provider failed: Settings > AI > Test connection; check the key, base URL and `AI_TIMEOUT_S`; worker logs |
| `budget_exhausted` | A budget is spent and `on_exhausted = human` |
| `max_ai_turns`, `answer_unhelpful` | Limits in Settings > Policy |

Also check that sources are `ready` and that the embedder did not change recently (a
re-index runs after a change; until then retrieval relies on full text).

## Emails are not threading

| Symptom | Fix |
| --- | --- |
| Customer replies open new conversations | The reply must reach the inbound webhook with the `+<token>` reply address intact, or carry `In-Reply-To`/`References`. Check the provider forwards plus-addressed mail for `MAIL_REPLY_DOMAIN`, and that the sender is the same customer (a reply from another address opens a new conversation by design) |
| Inbound posts return 401 | The URL's token is wrong or was rotated: Settings > Inboxes > rotate and update the provider |
| Inbound posts return 400 "notification carries no message content" | SES via SNS without raw content, or an SNS message with an invalid signature (see [deploy-aws.md](deploy-aws.md#inbound-email-with-ses)) |
| Inbound returns `ignored` | Automatic mail (auto-reply headers, mailing lists, daemon senders), our own `MAIL_FROM_ADDRESS`, or a duplicate `Message-ID` |
| Replies never arrive | The message's delivery shows `failed` or `no_address`; check `MAIL_BACKEND`, SMTP or SES settings, SES production access, and the worker logs. Locally every mail is in Mailpit (http://localhost:4825) |

Try it locally with `make send-test-email TOKEN=<inbound token>`.

## Webhooks were switched off

After 10 consecutive failed deliveries a webhook is disabled with the reason (Settings >
Webhooks, delivery log with status codes and timings). Fix the receiver (it must answer
2xx within 10 s), then switch the webhook back on and send a test ping. URLs that resolve
to private, loopback or metadata addresses are refused (allowed locally only with
`ALLOW_PRIVATE_URLS=true`, never in production). Redirects are not followed.

## Other

| Symptom | Fix |
| --- | --- |
| The API refuses to start with "unsafe production configuration" | Read the listed settings; each maps to a boot guard ([security.md](../architecture/security.md#production-boot-guards)) |
| "Missing CSRF header" from a script | Use a bearer token or an API key instead of the cookie, or send `X-SupportDesk-CSRF: 1` |
| "Too many failed attempts" | Lockout for 15 minutes for that address and account; `make admin EMAIL=...` resets an owner's password |
| Live updates stop across replicas | Set `REDIS_URL` on every API and worker replica (without it each process falls back to Postgres `LISTEN/NOTIFY`, which still works across processes on one database) |
| A port is taken | Override it in `deploy/compose/.env` ([configuration.md](configuration.md#ports)) |
