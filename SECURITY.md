# Security Policy

SupportDesk holds customer conversations, an organisation's internal knowledge and the
keys to its model providers, and its AI answers customers on the organisation's behalf. We
take reports seriously and respond quickly.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.x (latest minor) | Yes |
| Older minors | No |

## Reporting a vulnerability

**Please do not open a public issue for security issues.**

Report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository ("Security" tab, "Report a vulnerability").

Please include:

- the affected component (`apps/api`, `apps/web`, the widget loader, `infra/terraform/...`)
  and version or commit,
- a description of the issue and its impact,
- steps to reproduce, or a proof of concept (for prompt injection: the message or document
  and the provider and policy settings used),
- any suggested mitigation.

What to expect:

| Stage | Target |
| ----- | ------ |
| Acknowledgement | within 3 business days |
| Initial assessment and severity | within 7 business days |
| Fix or mitigation for critical and high issues | within 30 days |
| Coordinated public disclosure | after a fix is released, credited to you unless you prefer otherwise |

## Scope

In scope: the code in this repository and the infrastructure it provisions with its
default settings. We are especially interested in:

- reading or changing another organisation's conversations, customers, knowledge or
  settings; a widget visitor or portal customer reading someone else's conversation;
- a way for a customer message or a knowledge document to make the AI **send** an answer
  the policy should have held for approval, drafted or escalated (a refund, cancellation or
  account change promise), or to remove a sensitive flag;
- an AI answer sent without a citation to a passage above the threshold;
- forging a verified widget identity, a visitor, portal or session token, an API key, an
  inbound email post, or a webhook signature;
- requests from the API or worker reaching an address they should not (instance metadata,
  private networks) through AI endpoints, crawled URLs, sitemaps or webhooks;
- recovering a secret (`SESSION_SECRET`, `TOKEN_PEPPER`, `LOCAL_MASTER_KEY`, an AI
  provider key, a webhook or identity secret) from the API, logs or the database;
- spending past a hard budget, or bypassing rate limits or lockout;
- authentication or authorization bypasses, CSRF, stored XSS in the agent app, widget or
  help center.

Out of scope:

- **The demo seed.** `make demo` creates well-known demo accounts with a published
  password, on purpose.
- **The mock AI** (`apps/api/src/mockai`), a test fixture never deployed to AWS.
- A model producing wrong but harmless text that is grounded in the organisation's own
  documents (that is a content issue; the policy and grounding design is documented in
  [docs/architecture/ai-agent.md](docs/architecture/ai-agent.md)).
- Known limitations documented in [docs/architecture/threat-model.md](docs/architecture/threat-model.md).
- Admins abusing admin powers (admins can read every conversation and change the policy
  by design).
- Findings that require a compromised host, compromised AWS account, or leaked deployment
  secrets.
- Denial of service through resource exhaustion of a deployment you operate yourself.

## Hardening checklist for operators

See [docs/architecture/security.md](docs/architecture/security.md#operator-checklist).
