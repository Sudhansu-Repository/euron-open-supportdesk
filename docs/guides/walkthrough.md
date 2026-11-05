# Walkthrough

A guided tour of the product with the demo data. Start the stack and seed it first
([quickstart-local.md](quickstart-local.md)): `make up && make demo`. Every demo account
uses the password `Demo-Pass-2026`.

The demo company is **Lumen**, which sells smart bulbs and a hub, with a Lumen Plus
subscription. `make demo` creates five agents in two teams, a knowledge base built from
five real files (a Markdown help guide, an FAQ CSV, an HTML shipping page, a PDF warranty,
a DOCX business guide) and six published articles plus one draft, a month of
conversation history across the widget, email and portal, knowledge gaps, 31 days of
analytics, and a live inbox with escalations, an SLA breach and two answers waiting for
approval. The demo answers with the bundled mock model, so no key is needed.

## 1. The customer's side

Open the Lumen website at http://localhost:4815 (a different origin from the app, as on a
real site) and click the chat launcher.

- Ask **"How do I reset my password?"**. The AI answers from the FAQ and shows its source.
  Mark it helpful: the conversation is resolved by AI.
- In a new conversation ask **"My bulb will not pair"**. The answer comes from the help
  guide (the 2.4 GHz Wi-Fi section), with a citation.
- Ask **"I was charged twice, I want a refund"**. The AI does not send an answer: a
  teammate checks it first, and the customer is told so.
- Ask **"Can I talk to a human?"** or click **Talk to a person**. The handoff is
  immediate.
- Ask something the knowledge base does not cover. The AI says a teammate will help
  instead of guessing, and the question becomes a knowledge gap.

The help center and portal are at http://localhost:4810/help/lumen: search articles, or
sign in with a magic link (the email lands in Mailpit, http://localhost:4825).

## 2. The inbox

Sign in at http://localhost:4810 as **Sofia** (`sofia@lumen.example`, agent).

- **Inbox** views: Mine, Unassigned, AI handled, Needs approval, Escalated, SLA at risk,
  Resolved. Badges show the channel, priority, SLA state and whether the AI holds the
  conversation.
- Open the conversation you just escalated. The **AI panel** shows why it was handed over
  (reason codes in plain words), the summary, the triage (category, priority, sentiment),
  the best relevance score, tokens and cost. The transcript shows the AI's citations.
- Reply. The reply appears in the widget at once (WebSocket), and the conversation is now
  owned by people. Add an internal note: it never reaches the customer.
- Try **Draft with AI** (tone options) and a **canned reply** with placeholders.
- Change priority, category, tags, assignee; resolve. Everything lands in the
  conversation's history and the audit log.

## 3. Approvals

Sign in as **Maya** (`maya@lumen.example`, owner) and open **Approvals**. The refund
answers the AI prepared wait here with their citations. Approve one (optionally edited):
it is sent to the customer (and emailed if they left an address). Reject another: it is
discarded and the conversation stays with people.

## 4. Knowledge

**Knowledge** lists the five sources with their status, pages and chunks, and the articles.

- Upload a file (PDF, DOCX, Markdown, text, HTML or an FAQ CSV) or add a URL; watch it go
  from queued to ready, and inspect its chunks.
- **Test a question**: ask "how long is the warranty?" and see the retrieved passages, each
  with similarity, coverage and relevance against the threshold, and what the AI would do.
  Ask a refund question to see the policy decision instead.
- Publish the draft article and ask about it in the widget.

## 5. Knowledge gaps

**Gaps** groups the questions the AI could not answer by topic, most frequent first, with
examples. Open one, click **Draft article** (built from the agents' replies on those
conversations), edit, publish. Ask the question again in the widget: the AI now answers
and cites the new article.

## 6. Analytics

**Analytics** shows volume by channel, first response and resolution times (median and
p90), AI resolution rate, escalation rate and reasons, CSAT, sentiment, team workload,
and the AI costs: tokens, cost per AI resolution next to the $0.99 per resolution SaaS
price, cache savings and budget usage. Export the daily numbers as CSV.

## 7. Settings (owner or admin)

- **AI**: provider (extractive, Ollama, OpenAI-compatible, Anthropic), models for answers
  and triage, embedder, test connection, model prices.
- **Policy**: mode (off, draft, approval, auto), categories the AI may resolve, the
  relevance threshold, sensitive intents and custom keywords, VIP and frustration rules,
  turn limits.
- **Budgets and Token Saver**: daily and monthly limits with the fallback, caches, history
  length.
- **Inboxes**: the widget designer and snippet, allowed origins, identity verification,
  email address and inbound token.
- Team and agents (roles, availability, capacity), SLA policies, canned replies, API keys,
  webhooks with their delivery log, and the audit log.

Switch the provider to **extractive** and ask the widget a question again: the answer is
now a quoted passage, with no model call at all. See [zero-api-key.md](zero-api-key.md).
