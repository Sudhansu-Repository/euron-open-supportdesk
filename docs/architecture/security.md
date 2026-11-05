# Security

How SupportDesk protects customer conversations, the organisation's knowledge and its
credentials. The STRIDE analysis is in [threat-model.md](threat-model.md); how to report a
vulnerability is in [SECURITY.md](../../SECURITY.md).

## Tenant isolation

One install can host many organisations. Every tenant-owned table carries `org_id`
(foreign key, cascade, indexed). Every service query filters by the caller's organisation,
and every lookup by primary key compares `row.org_id` with the caller's scope before
returning, answering 404 rather than 403 so ids of other organisations are not confirmed.
Visitor and portal tokens carry their organisation and are checked against the inbox or
the slug in the path. WebSocket topics are per organisation and per ticket, and a socket
is subscribed only after its ticket's ownership is checked.
`test_agents_cannot_change_settings_and_orgs_cannot_see_each_other` and the per-test
organisations of the integration suite exercise this on every endpoint.

## Authentication

- **Agents**: Argon2id password hashes; passwords need 10 characters, upper and lower
  case and a digit. Sessions are HS256 JWTs (audience `supportdesk-dashboard`,
  `SESSION_TTL_HOURS`, default 12) in an HttpOnly, `SameSite=Lax` cookie (`Secure` with
  `COOKIE_SECURE`). Sign-out stores the token's `jti` in `revoked_sessions` (Postgres, never
  a cache, so eviction cannot revive a session); a password change bumps
  `session_version`, ending every other session.
- **CSRF**: cookie-authenticated mutations must send `X-SupportDesk-CSRF: 1`. A cross-site
  page cannot add a custom header without a CORS preflight, which the `CORS_ORIGINS`
  allowlist refuses.
- **Lockout**: 5 failed sign-ins per (email, address) lock that pair for 15 minutes, so a
  stranger cannot lock the owner out from elsewhere; 50 per account in the window lock the
  account. Failure keys are HMACs, so emails and addresses are not stored in the clear.
  Unknown emails cost the same Argon2 verification as known ones. Sign-in, sign-up and
  invitation acceptance are also rate limited per address (`LOGIN_RPM`, `SIGNUP_RPM`).
- **API keys**: `sdk_<prefix>_<secret>`, shown once, stored as a peppered HMAC
  (`TOKEN_PEPPER`), compared in constant time; read or write scope; revocable.
- **Customers**: visitor tokens (audience `supportdesk-widget`, 30 days) and portal tokens
  (audience `supportdesk-portal`, 7 days). The audience keeps one kind of token from being
  accepted as another. Portal magic links and invitations are single use, short lived, and
  stored only as peppered hashes.
- **Widget identity**: optional `HMAC-SHA256(identity secret, external_id)` signed by the
  company's backend ([channels.md](channels.md#identity-verification)).

## Authorization

Roles: `agent` (work the inbox, read settings), `admin` (settings, inboxes, knowledge,
macros, SLA, API keys, webhooks, audit log, export), `owner` (as admin; the last owner
cannot be demoted). API keys act with role `api`, limited to the REST endpoints and their
scope. Internal notes and AI drafts are never returned to visitors or portal customers and
never announced on customer sockets (`test_internal_notes_never_reach_the_customer`).

## Secrets

| Secret | Protection |
| --- | --- |
| AI provider keys, webhook signing secrets, widget identity secrets | Sealed before storage: AES-256-GCM with a key derived from `LOCAL_MASTER_KEY`, or AWS KMS (`KEY_MODE=kms`) with an encryption context bound to the record (`org:<id>:ai_api_key`, `webhook:<id>`, `inbox:<id>:identity`), so a sealed value copied to another row does not open. Never returned by the API |
| API keys, inbound email tokens, invitation and portal tokens | Peppered HMAC only |
| `SESSION_SECRET`, `TOKEN_PEPPER`, `LOCAL_MASTER_KEY` | Environment (Secrets Manager on AWS); refused in production when weak or reused |

Database errors never echo bound parameters (`hide_parameters=True`), the `log` mail
backend never logs bodies (they carry one-time links), and the request log records method,
path, status and duration only.

## Production boot guards

With `ENVIRONMENT=production`, `Settings.guard()` refuses to start (listing every unsafe setting)
when:

1. `SESSION_SECRET` or `TOKEN_PEPPER` is a known placeholder, contains
   `not-for-production`, or is shorter than 32 characters;
2. `KEY_MODE=local` and `LOCAL_MASTER_KEY` is insecure in the same way;
3. `SESSION_SECRET` equals `TOKEN_PEPPER`;
4. `SUPPORTDESK_CLOUD=aws` and `AWS_ENDPOINT_URL` is set (an emulator in production);
5. `COOKIE_SECURE` is false;
6. `MAIL_BACKEND=log` (ticket email would go nowhere);
7. `EMBEDDER=hash` (the test embedder);
8. `CORS_ORIGINS` contains `*`;
9. `ALLOW_PRIVATE_URLS` is true (SSRF);
10. `PUBLIC_URL` or `PUBLIC_API_URL` is not `https://`.

`test_unsafe_production_settings_are_refused` covers each.

## Input and transport

- **Body limits** (`BodySizeLimitMiddleware`, before any route): `MAX_BODY_BYTES` (1 MB)
  by `Content-Length` and by counting chunked bodies; the knowledge upload route gets
  `MAX_UPLOAD_BYTES` plus multipart framing only when the request carries a valid admin or
  owner session token (checked from the signed token, no database call); the inbound email
  route is streamed and counted up to `MAX_UPLOAD_BYTES`, and the route checks its inbound
  token before reading the body. JSON bodies that are not valid UTF-8 text (including lone
  surrogates Postgres cannot store) are a 422 before any route
  (`test_large_and_malformed_bodies_are_refused_before_routes`).
- **Validation**: Pydantic on every request; lengths bounded on every string field.
- **Rate limits**: per address and per visitor or customer on public routes
  ([HLD.md](HLD.md#caching-layers)); throttling is best effort if Redis is down.
- **Headers**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy: same-origin`,
  `Permissions-Policy` on every API response. The web app sets a Content Security Policy
  with `frame-ancestors 'none'` everywhere except the widget frame, whose ancestors are the
  inbox's allowed origins.
- **Proxy headers**: the API trusts `X-Forwarded-For` only from `FORWARDED_ALLOW_IPS`.

## Outbound requests (SSRF)

The API and worker call URLs that users configure: AI endpoints, embedding endpoints,
crawled pages and sitemaps, webhooks. All of them:

- accept only `http` and `https`;
- canonicalise the host (integer, hex, octal IPv4 forms, trailing dots) and refuse
  link-local addresses (instance metadata `169.254.169.254`), `fd00:ec2::254`, unspecified
  addresses and metadata host names, always;
- resolve the name at call time and refuse it if any address is forbidden;
- refuse private and loopback addresses for crawls and webhooks unless
  `ALLOW_PRIVATE_URLS` (refused in production), and for AI endpoints unless
  `AI_ALLOW_PRIVATE_ENDPOINTS` (on by default so an Ollama in the same network works; in
  production it is refused while `SIGNUP_ENABLED` is on, since any stranger who signs up
  becomes a tenant admin able to set the endpoint);
- check the address the connection actually reached (from the socket) before using a
  response, and refuse it when it is forbidden;
- never follow redirects automatically; the crawler re-checks every hop itself (at most 4);
- use bounded timeouts and body sizes.

Residual risk: the name is resolved for the check and again by the HTTP client. The
connected-peer check means a rebinding name cannot get a response from a forbidden address
used, but the request itself has been sent by then. On AWS, the `ai_egress` and security
group rules limit where tasks can connect at all.

## AI-specific controls

Policy outside the model, a triage merge that only adds caution, grounding with
citations, outbound screening of answers, redaction of cards and secrets before any
model call, and hard budgets reserved before each call. See [ai-agent.md](ai-agent.md)
and [ADR-0008](adr/0008-policy-outside-the-model.md).

## Audit

Every mutation by an agent, admin, owner or API key writes an `audit_log` row in the same
transaction as the change (sign-in, failed sign-in, settings, inboxes, knowledge, tickets,
approvals, API keys, webhooks, users). The table is append-only: a database trigger
refuses `UPDATE` and `DELETE`. Admins read it at `GET /api/v1/audit` (keyset paginated,
filter by action prefix).

## Operator checklist

- Set `ENVIRONMENT=production` so the boot guards run; generate secrets with
  `openssl rand -hex 32`.
- Use `KEY_MODE=kms` on AWS.
- List every site in each widget inbox's allowed origins (an empty list accepts any site).
- Turn off `SIGNUP_ENABLED` after creating your organisation on a private install.
- Turn off `AI_ALLOW_PRIVATE_ENDPOINTS` if you only use public model providers.
- Set budgets in Settings > AI before connecting a paid provider.
- Rotate the inbound email token and identity secrets if they leak (Settings > Inboxes).
- Keep `FORWARDED_ALLOW_IPS` to the load balancer's network.
