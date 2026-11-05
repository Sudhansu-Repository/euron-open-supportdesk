# Quickstart (local)

Everything runs in Docker on one machine. No AWS account, no API keys.

## Prerequisites

- Docker with Compose v2 (Docker Desktop or Docker Engine on Linux)
- `make`, `bash`, `openssl`, `curl`
- About 4 GB of disk for the images, plus about 130 MB for the embedding model (and
  about 1 GB more if you add the optional Ollama model)
- Free local ports 4810, 4815, 4825, 4826, 4830, 4842, 4850, 4866, 4879 (change any of
  them in `deploy/compose/.env`, see [configuration.md](configuration.md#ports))

## Start

```bash
git clone https://github.com/euron-sde-team/euron-open-supportdesk.git
cd euron-open-supportdesk
make up      # Postgres (pgvector), Redis, Mailpit, Floci (provisioned by Terraform), mock AI, api, worker, web, demo site
make demo    # the Lumen demo company: agents, knowledge, a month of conversations, gaps and analytics
```

`make up` runs `make env` first, which writes `deploy/compose/.env` with random local-only
secrets (once; delete the file to regenerate). It then builds the images, applies the
`local-floci` Terraform against the emulator (objects bucket, KMS key, secrets, SES
identity), runs the migrations and waits until every service is healthy. The worker
downloads the embedding model on its first start (about 130 MB, kept in a volume that
survives `make down`).

When it is up:

| What | URL |
| --- | --- |
| Agent app | http://localhost:4810 |
| API docs (OpenAPI) | http://localhost:4830/docs |
| Demo customer website with the chat widget (another origin) | http://localhost:4815 |
| Mailpit: every email the app sends | http://localhost:4825 |
| Help center and portal | http://localhost:4810/help/lumen |

`make demo` prints the sign-in details. Every demo account uses the password
`Demo-Pass-2026`.

| Who | Email | Role |
| --- | --- | --- |
| Maya Chen | `maya@lumen.example` | owner |
| Ravi Patel | `ravi@lumen.example` | admin (also on the Billing team) |
| Sofia Alvarez | `sofia@lumen.example` | agent |
| Tom Becker | `tom@lumen.example` | agent |
| Aisha Khan | `aisha@lumen.example` | agent (away, Billing team) |

The demo organisation answers with the bundled **mock model** (an offline stand-in that
speaks the OpenAI wire format), so AI answers, drafts and costs appear without a key.
Switch it to `extractive`, Ollama or a real provider in Settings > AI.

## Five minutes

1. Open http://localhost:4815, the Lumen customer site. Click the chat launcher and ask
   "How do I reset my password?". The AI answers with a source you can click.
2. Ask "I want a refund for last month". The AI does not answer on its own: the reply
   waits for approval, and the customer sees that a teammate is checking.
3. Click "Talk to a person" (or type "I want to talk to a human").
4. Sign in at http://localhost:4810 as `sofia@lumen.example`. The conversation is in the
   inbox with the handoff reason, the AI summary and the transcript. Reply; the reply
   appears in the widget at once.
5. Sign in as `maya@lumen.example`, open **Approvals**, and approve or reject the refund
   answer.
6. **Knowledge**: upload a PDF or Markdown file, wait for it to be ready, then use
   **Test a question** to see the retrieved passages, their scores and what the AI would
   do.
7. **Analytics**: AI resolution rate, response times, escalation reasons and the cost per
   AI resolution next to the $0.99 SaaS price.

[walkthrough.md](walkthrough.md) is the long version of this tour.

## Optional: a local LLM

```bash
make ollama-pull     # starts the ollama profile and pulls qwen2.5:1.5b
```

Then Settings > AI > provider **Ollama** (base URL `http://ollama:11434` inside the
stack). See [zero-api-key.md](zero-api-key.md).

## Useful commands

| Command | What |
| --- | --- |
| `make ps` | Service status |
| `make logs SERVICE=worker` | Tail one service |
| `make admin EMAIL=you@example.com ORG='My Company'` | Create an organisation and its owner (prompts for the password) |
| `make send-test-email TOKEN=<inbound token>` | Post a sample email to an email inbox |
| `make backup` / `make restore BACKUP=backups/<timestamp>` | Database dump plus the objects bucket |
| `make down` | Stop everything and delete the data (the embedding and Ollama model volumes survive) |

## Next

- [Configuration](configuration.md): every setting.
- [Testing](testing.md): unit, integration, matrix, e2e and QA.
- [Deploy to AWS](deploy-aws.md).
- [Troubleshooting](troubleshooting.md).
