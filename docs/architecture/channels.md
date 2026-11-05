# Channels

Where conversations come from. Every organisation starts with four inboxes: **Website
chat** (widget), **Email**, **Customer portal** and **API** (AI off by default). Each inbox
can route to a team and switch the AI on or off. A conversation from any channel is one
ticket with one message history ([ADR-0007](adr/0007-conversation-equals-ticket.md)).

Code: `apps/api/src/supportdesk/channels/`, the loader `apps/web/public/widget.js`, the
frame page `apps/web/src/app/widget/`.

## Website widget

### How it is embedded

```html
<script src="https://support.example.com/widget.js" data-key="pk_..." async></script>
```

The loader (served by the web app, `Cache-Control: public, max-age=300`) adds a launcher
button and an iframe pointing at `https://support.example.com/widget/frame?key=...&origin=<host page origin>`.
The chat runs entirely inside the iframe, on the SupportDesk origin: the host page never
sees the visitor token or the messages. The loader and the frame exchange only open,
close and appearance events through `postMessage`, checked against the frame's origin.
Optional attributes: `data-position="left|right"`, `data-color="#4f46e5"` (the inbox's
settings win once loaded).

### Which sites may use it

Two independent checks, both driven by the inbox's **allowed origins** (Settings >
Inboxes):

| Check | Enforced by | Effect |
| --- | --- | --- |
| Who may **embed** the frame | The browser, from the frame page's `Content-Security-Policy: frame-ancestors 'self' <allowed origins>`. The web middleware asks `GET /api/v1/widget/{key}/frame-policy` and caches the answer for 60 s per key; an unknown key or an unreachable API yields `'self'` only (fails closed) | A site that is not listed gets a blank frame |
| Who may **call** the widget API | The API, on every widget request and on the widget WebSocket: the request `Origin` must be an allowed origin or the app's own origin (`PUBLIC_URL`). `POST /session` also checks the `parent_origin` the frame reports, to turn a silently blocked frame into a clear `origin_not_allowed` message | 403 `origin_not_allowed` |

Origins are normalised (`scheme://host[:port]`, lower case). **An inbox with no allowed
origins accepts any site**, which is convenient while trying it out; list your sites
before going live. `test_widget_refuses_sites_that_are_not_allowed` covers both checks.

### Visitors and their tokens

`POST /api/v1/widget/{public_key}/session` returns a **visitor token** (JWT, audience
`supportdesk-widget`, 30 days, bound to the organisation, the inbox and a customer
record), the widget configuration (title, greeting, colour, position, suggested
questions, launcher label, company name, whether agents are online, whether AI is on) and
the visitor's latest open conversation. The frame stores the token in `localStorage` per
widget key and presents it on every call as `Authorization: Bearer` (and as `?token=` on
the WebSocket, since browsers cannot set headers there). A visitor can only read their own
conversations (`test_visitor_cannot_read_another_visitors_conversation`).

Visitor endpoints: send a message (`POST /widget/messages`), read the conversation, ask for
a person (`POST /widget/tickets/{id}/human`, escalates with `customer_requested`), mark an
AI answer helpful or unhelpful, rate the conversation (1 to 5, once resolved), and leave an
email for follow-up when nobody is online (`POST /widget/email`). Rate limits: sessions
`2 x WIDGET_RPM` per address, messages `WIDGET_RPM` per visitor and `3 x WIDGET_RPM` per
address, over a 60 s sliding window.

Helpful marks resolve the conversation (an AI resolution when no person replied).
Unhelpful marks disable the cached answer, record a knowledge gap question, and hand over
once `policy.max_unhelpful` is reached.

### Identity verification

The widget's public key is not a secret: anyone can start an anonymous session. To let
signed-in customers see their history and be recognised (VIP, name, email) without letting
anyone claim to be them, turn on identity verification for the inbox:

1. Settings > Inboxes > the widget inbox > generate an **identity secret** (`ids_...`,
   shown once, stored sealed with the context `inbox:<id>:identity`).
2. Your backend computes `HMAC-SHA256(identity secret, external_id)` as lower-case hex for
   the signed-in user, where `external_id` is your own stable user id.
3. The session request carries `external_id`, `signature` and optionally `email` and
   `name`. A wrong signature is refused with 401 `identity_invalid`
   (`test_identity_verification_refuses_a_forged_customer`). A verified visitor is matched
   to (or creates) the customer with that `external_id` only: the signature covers the id,
   not the email, so a signed-in user who sends someone else's email never gets that
   person's record (`test_a_verified_visitor_cannot_claim_another_customers_record_by_email`).
   On the bundled widget, pass the identity as `data-external-id`, `data-signature`,
   `data-email` and `data-name` on the script tag, or call
   `window.SupportDesk.identify({externalId, signature, email, name})`.
4. Optionally set **identity required**: anonymous sessions are then refused with
   `identity_required`.

An email a visitor types into the widget's "email me" form is kept as an unverified
contact address (`attributes.contact_email`): replies are emailed there, but it is never
used to find or merge customers, so nobody can claim another person's email this way.
Visitor and portal tokens never follow a customer merge: after an agent merges a
duplicate into another record, the old token is refused instead of opening the other
person's conversations.

Node.js (your backend):

```js
import { createHmac } from "node:crypto";

export function supportdeskSignature(externalId) {
  return createHmac("sha256", process.env.SUPPORTDESK_IDENTITY_SECRET)
    .update(String(externalId), "utf8")
    .digest("hex");
}
```

Python (your backend):

```python
import hashlib
import hmac
import os


def supportdesk_signature(external_id: str) -> str:
    secret = os.environ["SUPPORTDESK_IDENTITY_SECRET"].encode()
    return hmac.new(secret, external_id.encode(), hashlib.sha256).hexdigest()
```

Never compute the signature in the browser: the secret would be public.

**With the bundled widget**, put the values on the script tag, or call the JavaScript API
once the customer signs in (calls made before the script loads are queued):

```html
<script src="https://support.example.com/widget.js" data-key="pk_..."
        data-api="https://api.support.example.com"
        data-user-id="user-42" data-user-hash="<HMAC from your backend>"
        data-email="dana@example.com" data-name="Dana Whitfield" async></script>
<script>
  // Or later, after sign-in:
  SupportDesk.identify({ userId: "user-42", userHash: "<HMAC>", email: "dana@example.com", name: "Dana" });
  // On sign-out:
  SupportDesk.logout();
</script>
```

The loader hands the identity to the frame with `postMessage`, addressed to the frame's
origin only; the frame accepts it only from its parent page's origin. A wrong or missing
hash, when the inbox has an identity secret, is refused by the API and the widget shows
that chat is unavailable, so check the signature in your backend first.

### Offline and live behaviour

The frame opens `/ws/widget/{ticket_id}` and refetches the conversation on each
`message.created` or `ticket.updated` event; while the socket is down it polls (every 3 s
while waiting for a reply, otherwise every 15 s). When no agent is online the widget
offers to leave an email. Once the customer has an address, agent replies, approved AI
answers and AI answers on that widget conversation are also emailed (they may have closed
the page), and their email reply threads back into the same conversation.

## Email

### Inbound

A mail provider posts each received message to the email inbox's inbound URL:

```
POST https://<api host>/api/v1/channels/email/inbound/<inbound token>
```

The token (`inb_...`) is generated in Settings > Inboxes and shown once; only its peppered
hash is stored. Two body formats are accepted:

| Content type | Body |
| --- | --- |
| anything but JSON (`message/rfc822`, `application/octet-stream`, `text/plain`) | The raw RFC 822 message (Mailgun and Postmark raw forwarding, `scripts/send-test-email.sh`) |
| `application/json` | An SES receipt notification, optionally wrapped in an SNS `Notification` envelope; the raw message is read from `content` (Base64). Enable raw content in the SES SNS action |

The route authenticates the token **before** reading the body; the body is streamed and
counted up to `MAX_UPLOAD_BYTES`, so an anonymous client cannot make the API buffer
megabytes.

**SNS envelopes** (`channels/sns.py`): every SNS message is checked against its signature
(SignatureVersion 1 and 2) with Amazon's signing certificate, fetched only from
`sns.<region>.amazonaws.com` over HTTPS and cached. A `SubscriptionConfirmation` is then
confirmed by visiting its `SubscribeURL` (again only an Amazon SNS host), so the HTTPS
subscription the `email` Terraform module creates confirms itself on the first request.
A failed signature is refused with 401 `invalid_sns_message`. The secret token in the URL
remains the first check; the signature is defence in depth against a leaked token.

Parsing (`channels/email.py`):

- The sender is the `From` address (refused without one).
- The text is the plain part (or the HTML part converted to text), with quoted history
  removed (`On ... wrote:`, `Original Message`, `From:`/`Sent:` blocks, `>` lines), cut at
  50,000 characters.
- Up to 10 attachments, each at most `MAX_ATTACHMENT_BYTES`, are stored in object storage
  (larger ones are skipped).

Threading, in order:

1. A recipient (`To`, `Cc`, `Delivered-To`, `X-Original-To`) of the form
   `<local>+<24 hex reply token>@<domain>` names the conversation directly.
2. Otherwise, an `In-Reply-To` or `References` id that matches a stored message's
   `email_message_id` in the same organisation.
3. The message joins that conversation only if the sender is the conversation's customer;
   otherwise (or with no match) it opens a new conversation, subject without `Re:`,
   `Fwd:` or `AW:`.

A customer reply to a resolved or closed conversation reopens it.

### Loop protection

A message is ignored without being stored (outcome `ignored`) when it is automatic: `Auto-Submitted`
other than `no`, `Precedence: bulk|list|junk|auto_reply`, `X-Autoreply`, `X-Autorespond`,
`List-Id`, or a sender starting with `mailer-daemon@`, `postmaster@`, `no-reply@` or
`noreply@`. Mail from our own `MAIL_FROM_ADDRESS` is ignored. A repeated `Message-ID` in
the same organisation is ignored (providers retry). Together these stop two
auto-responders from looping (`test_auto_replies_duplicates_and_bad_tokens_are_ignored`).
Outgoing replies do not set `Auto-Submitted` themselves.

### Outbound

Agent replies, approved AI answers and sent AI answers enqueue a `mail.reply` job (dedupe
`mail:<message id>`) through `tickets.service.email_customer`: always on email tickets, and
on widget and portal tickets when the customer has an email address. The job sends through `MAIL_BACKEND` (SMTP, or SES with
`SendRawEmail` so headers survive):

| Header | Value |
| --- | --- |
| `From` | `<Company> Support <MAIL_FROM_ADDRESS>` |
| `To` | the customer's email |
| `Subject` | `Re: [#<number>] <subject>` |
| `Message-ID` | `<random hex@MAIL_REPLY_DOMAIN>`, stored on the message before sending so a retry reuses it |
| `Reply-To` | `<local part of MAIL_FROM_ADDRESS>+<reply token>@MAIL_REPLY_DOMAIN` |
| `In-Reply-To` | the last known message id in the conversation |
| `References` | up to the last 10 message ids |

The body is the reply text plus a footer naming the conversation number. Delivery status
(`sent`, `failed`, `no_address`) is recorded on the message. Internal notes and drafts are
never emailed. `test_email_in_reply_out_and_threading` sends a message in, a reply out
through Mailpit-compatible SMTP, and a customer reply back into the same ticket.

## Customer portal

At `/help/<org slug>` customers sign in by magic link:

1. `POST /api/v1/portal/{slug}/link` with an email. The response is identical whether or
   not the address is known; an unknown address gets a customer record so the link works.
   Rate limits: 5 per minute per address, 3 per minute per email.
2. The emailed link (`/help/<slug>/signin?token=...`) is single use, expires after 15
   minutes, and is stored only as a peppered hash.
3. `POST /api/v1/portal/{slug}/session` redeems it for a **portal token** (JWT, audience
   `supportdesk-portal`, 7 days, bound to the customer and organisation).

Signed in, customers list their conversations, open one, reply, create a new one (through
the portal inbox, with the AI turn as on any channel), mark AI answers helpful or not and
rate resolved conversations; messages are limited to 10 per minute per customer. Live
updates on `/ws/portal/{ticket_id}`. A portal token is refused on another organisation's
slug, and the audience keeps it from being accepted as a visitor or agent token
(`test_portal_magic_link_shows_my_tickets`, `test_tokens_are_bound_to_their_audience`).

## Help center

Public, no sign-in: `GET /api/v1/help/{slug}` (title, accent colour, categories, popular
articles, the widget key), `GET /api/v1/help/{slug}/articles?q=` (full-text search over
published articles), `GET /api/v1/help/{slug}/articles/{article slug}` (counts a view),
and `POST .../feedback` (was this helpful). Drafts are never public
(`test_help_center_is_public_and_shows_published_articles`). Published articles are also
knowledge the AI answers from, and their citations link back here.

## REST API

Integrations authenticate with an API key (`Authorization: Bearer sdk_...`), created by an
admin in Settings > API keys, shown once, stored as a peppered HMAC.

| Endpoint | Scope |
| --- | --- |
| `GET /api/v1/tickets` (views, filters, `q` full-text or `#123`, keyset `cursor`, `limit` up to 100) | read |
| `GET /api/v1/tickets/{id}` | read |
| `POST /api/v1/tickets` (opens a conversation in the API inbox) | write |
| `POST /api/v1/tickets/{id}/messages` (reply or internal note) | write |
| `PATCH /api/v1/tickets/{id}` (status, priority, category, tags, assignee, team) | write |
| `GET /api/v1/customers`, `GET /api/v1/customers/{id}` | read |
| `PATCH /api/v1/customers/{id}` | write |
| `GET /api/v1/knowledge/articles`, `GET /api/v1/knowledge/articles/{id}` | read |
| `GET /api/v1/attachments/{id}` | read |

A read key cannot write (`test_api_key_scopes`). The full contract is
[docs/api/openapi.yaml](../api/openapi.yaml), also served at `/docs`.

### Webhooks

Admins subscribe HTTPS endpoints to `ticket.created`, `ticket.updated`,
`ticket.escalated`, `ticket.resolved` and `message.created`. Each delivery is a JSON body
`{"id", "event", "created_at", "data"}` with headers `X-SupportDesk-Event`,
`X-SupportDesk-Delivery` (dedupe on it) and
`X-SupportDesk-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>.<body>">` keyed by
the webhook's secret (`whsec_...`, shown once, stored sealed). Verify it like this:

```python
import hashlib
import hmac
import time


def verify(secret: str, header: str, body: bytes, tolerance_s: int = 300) -> bool:
    parts = dict(item.split("=", 1) for item in header.split(","))
    t, v1 = int(parts["t"]), parts["v1"]
    if abs(time.time() - t) > tolerance_s:
        return False  # refuse replays
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)
```

Deliveries are retried with backoff (up to 8 attempts); a webhook that fails 10 times in a
row is switched off with the reason shown in Settings; a test ping is one click. Targets
must be public addresses, checked when saved and again after DNS resolution at send time,
and redirects are not followed ([security.md](security.md#outbound-requests-ssrf)).
