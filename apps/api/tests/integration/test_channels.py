"""AC9: the channels. Widget origins and identity, email in and out with threading, the
customer portal."""

from __future__ import annotations

import hashlib
import hmac

from supportdesk.core.mail import OUTBOX
from tests.integration.conftest import Stack, eventually


async def _widget_inbox(org: object) -> dict[str, object]:
    inboxes = await org.ok("GET", "/api/v1/inboxes")  # type: ignore[attr-defined]
    return dict(next(i for i in inboxes if i["channel"] == "widget"))


async def _email_token(org: object) -> str:
    inboxes = await org.ok("GET", "/api/v1/inboxes")  # type: ignore[attr-defined]
    inbox = next(i for i in inboxes if i["channel"] == "email")
    saved = await org.ok("PATCH", f"/api/v1/inboxes/{inbox['id']}", {"rotate_inbound_token": True})  # type: ignore[attr-defined]
    return str(saved["secret"])


def _email(
    sender: str,
    subject: str,
    body: str,
    *,
    to: str = "support@acme.test",
    message_id: str = "<m1@mail.example>",
    in_reply_to: str | None = None,
    extra: str = "",
) -> bytes:
    headers = [
        f"From: Pat Customer <{sender}>",
        f"To: {to}",
        f"Subject: {subject}",
        f"Message-ID: {message_id}",
        "Content-Type: text/plain; charset=utf-8",
    ]
    if in_reply_to:
        headers += [f"In-Reply-To: {in_reply_to}", f"References: {in_reply_to}"]
    if extra:
        headers.append(extra)
    return ("\r\n".join(headers) + "\r\n\r\n" + body).encode()


async def test_widget_refuses_sites_that_are_not_allowed(stack: Stack) -> None:
    org = await stack.org("Origins")
    inbox = await _widget_inbox(org)
    await org.ok(
        "PATCH", f"/api/v1/inboxes/{inbox['id']}", {"allowed_origins": ["https://www.acme.test"]}
    )
    key = inbox["public_key"]
    policy = await stack.client().get(f"/api/v1/widget/{key}/frame-policy")
    assert policy.json()["frame_ancestors"] == ["https://www.acme.test"]

    ok = await stack.client(origin="http://localhost:4810").post(
        f"/api/v1/widget/{key}/session", json={"parent_origin": "https://www.acme.test"}
    )
    assert ok.status_code == 200
    help_center = await stack.client(origin="http://localhost:4810").post(
        f"/api/v1/widget/{key}/session", json={"parent_origin": "http://localhost:4810"}
    )
    assert help_center.status_code == 200  # our own help center may always embed it
    embedded_elsewhere = await stack.client(origin="http://localhost:4810").post(
        f"/api/v1/widget/{key}/session", json={"parent_origin": "https://evil.example"}
    )
    assert embedded_elsewhere.status_code == 403
    direct = await stack.client(origin="https://evil.example").post(
        "/api/v1/widget/messages",
        json={"body": "hi"},
        headers={"authorization": f"Bearer {ok.json()['token']}"},
    )
    assert direct.status_code == 403 and direct.json()["error"]["code"] == "origin_not_allowed"


async def test_identity_verification_refuses_a_forged_customer(stack: Stack) -> None:
    org = await stack.org("Identity")
    inbox = await _widget_inbox(org)
    saved = await org.ok(
        "PATCH", f"/api/v1/inboxes/{inbox['id']}", {"rotate_identity_secret": True}
    )
    secret = saved["secret"]
    await org.ok("PATCH", f"/api/v1/inboxes/{inbox['id']}", {"identity_required": True})
    good = hmac.new(secret.encode(), b"user-42", hashlib.sha256).hexdigest()
    client = stack.client(origin="http://localhost:4810")
    resp = await client.post(
        f"/api/v1/widget/{inbox['public_key']}/session",
        json={"external_id": "user-42", "email": "pat@example.com", "signature": good},
    )
    assert resp.status_code == 200 and resp.json()["customer_email"] == "pat@example.com"
    forged = await client.post(
        f"/api/v1/widget/{inbox['public_key']}/session",
        json={"external_id": "user-42", "signature": "0" * 64},
    )
    assert forged.status_code == 401 and forged.json()["error"]["code"] == "identity_invalid"
    anonymous = await client.post(f"/api/v1/widget/{inbox['public_key']}/session", json={})
    assert anonymous.status_code == 401


async def test_visitor_cannot_read_another_visitors_conversation(stack: Stack) -> None:
    org = await stack.org("Visitors")
    alice, bob = await org.visitor(), await org.visitor()
    conv = await alice.say("hello there, talk to a human", wait=False)
    resp = await bob.client.get(f"/api/v1/widget/tickets/{conv['ticket_id']}")
    assert resp.status_code == 404


async def test_email_in_reply_out_and_threading(stack: Stack) -> None:
    org = await stack.org("Email")
    token = await _email_token(org)
    inbound = stack.client()
    resp = await inbound.post(
        f"/api/v1/channels/email/inbound/{token}",
        content=_email("pat@example.com", "Bridge offline", "My bridge shows a red light."),
        headers={"content-type": "message/rfc822"},
    )
    assert resp.status_code == 200 and resp.json()["outcome"] == "new", resp.text
    ticket_id = resp.json()["ticket_id"]
    ticket = await org.ticket(ticket_id)
    assert ticket["channel"] == "email" and ticket["subject"] == "Bridge offline"

    OUTBOX.clear()
    await org.ok(
        "POST",
        f"/api/v1/tickets/{ticket_id}/messages",
        {"body": "Please unplug it for 10 seconds."},
        status=201,
    )
    sent = await eventually(lambda: _sent_to("pat@example.com"))
    headers = dict(sent.headers)
    assert headers["In-Reply-To"] == "<m1@mail.example>"
    assert "+" in headers["Reply-To"] and sent.subject.startswith(f"Re: [#{ticket['number']}]")

    reply_to = headers["Reply-To"]
    again = await inbound.post(
        f"/api/v1/channels/email/inbound/{token}",
        content=_email(
            "pat@example.com",
            "Re: Bridge offline",
            "It works now, thanks!\n\nOn Mon, Support wrote:\n> Please unplug it",
            to=reply_to,
            message_id="<m2@mail.example>",
        ),
        headers={"content-type": "message/rfc822"},
    )
    assert again.json() == {"outcome": "reply", "ticket_id": ticket_id}
    by_reference = await inbound.post(
        f"/api/v1/channels/email/inbound/{token}",
        content=_email(
            "pat@example.com",
            "Re: Bridge",
            "One more thing",
            message_id="<m3@mail.example>",
            in_reply_to=headers["Message-ID"],
        ),
        headers={"content-type": "message/rfc822"},
    )
    assert by_reference.json()["ticket_id"] == ticket_id
    bodies = [m["body"] for m in (await org.ticket(ticket_id))["messages"]]
    assert "It works now, thanks!" in bodies and not any("> Please unplug" in b for b in bodies)


async def _sent_to(address: str) -> object:
    return next((m for m in reversed(OUTBOX) if m.to == address and m.headers), None)


async def test_auto_replies_duplicates_and_bad_tokens_are_ignored(stack: Stack) -> None:
    org = await stack.org("Loops")
    token = await _email_token(org)
    client = stack.client()
    auto = await client.post(
        f"/api/v1/channels/email/inbound/{token}",
        content=_email(
            "pat@example.com",
            "Out of office",
            "I am away",
            message_id="<ooo@x>",
            extra="Auto-Submitted: auto-replied",
        ),
    )
    assert auto.json()["outcome"] == "ignored"
    first = await client.post(
        f"/api/v1/channels/email/inbound/{token}",
        content=_email("lee@example.com", "Hi", "Hello", message_id="<dup@x>"),
    )
    dup = await client.post(
        f"/api/v1/channels/email/inbound/{token}",
        content=_email("lee@example.com", "Hi", "Hello", message_id="<dup@x>"),
    )
    assert first.json()["outcome"] == "new" and dup.json()["outcome"] == "ignored"
    bad = await client.post(
        "/api/v1/channels/email/inbound/inb_not-a-real-token", content=b"From: x@y.z\r\n\r\nhi"
    )
    assert bad.status_code == 401


async def test_portal_magic_link_shows_my_tickets(stack: Stack) -> None:
    org = await stack.org("Portal")
    await org.ok(
        "POST",
        "/api/v1/tickets",
        {"customer_email": "kim@example.com", "body": "Where is my order?"},
        status=201,
    )
    public = stack.client()
    OUTBOX.clear()
    resp = await public.post(f"/api/v1/portal/{org.slug}/link", json={"email": "kim@example.com"})
    assert resp.status_code == 200
    unknown = await public.post(
        f"/api/v1/portal/{org.slug}/link", json={"email": "nobody@example.com"}
    )
    assert unknown.json() == resp.json()  # the answer never reveals who is a customer
    mail = next(m for m in OUTBOX if m.to == "kim@example.com")
    token = mail.text.split("token=")[1].split()[0]
    session = await public.post(f"/api/v1/portal/{org.slug}/session", json={"token": token})
    assert session.status_code == 200
    reused = await public.post(f"/api/v1/portal/{org.slug}/session", json={"token": token})
    assert reused.status_code == 401  # single use

    portal = stack.client(authorization=f"Bearer {session.json()['token']}")
    tickets = (await portal.get(f"/api/v1/portal/{org.slug}/tickets")).json()
    assert [t["subject"] for t in tickets] == ["Where is my order?"]
    created = await portal.post(
        f"/api/v1/portal/{org.slug}/tickets",
        json={"subject": "Invoice copy", "body": "Please resend my invoice"},
    )
    assert created.status_code == 201
    other = await stack.org("Other portal")
    cross = await portal.get(f"/api/v1/portal/{other.slug}/tickets")
    assert cross.status_code == 401


async def test_help_center_is_public_and_shows_published_articles(stack: Stack) -> None:
    org = await stack.org("Help")
    await org.ok(
        "POST",
        "/api/v1/knowledge/articles",
        {
            "title": "Resetting a bulb",
            "body": "Switch it off and on five times.",
            "status": "published",
            "category": "technical",
        },
        status=201,
    )
    await org.ok(
        "POST",
        "/api/v1/knowledge/articles",
        {"title": "Secret draft", "body": "Not yet", "status": "draft"},
        status=201,
    )
    public = stack.client()
    home = (await public.get(f"/api/v1/help/{org.slug}")).json()
    assert [a["title"] for a in home["popular"]] == ["Resetting a bulb"] and home["widget_key"]
    found = (await public.get(f"/api/v1/help/{org.slug}/articles?q=reset bulb")).json()
    assert [a["title"] for a in found] == ["Resetting a bulb"]


async def test_a_widget_customer_who_left_an_email_gets_the_reply_by_email(stack: Stack) -> None:
    org = await stack.org("Offline")
    visitor = await org.visitor()
    conv = await visitor.say("talk to a human please")
    await visitor.client.post("/api/v1/widget/email", json={"email": "gone@example.com"})
    OUTBOX.clear()
    await org.ok(
        "POST",
        f"/api/v1/tickets/{conv['ticket_id']}/messages",
        {"body": "Here is the answer."},
        status=201,
    )
    sent = await eventually(lambda: _sent_to("gone@example.com"))
    assert "Here is the answer." in sent.text and "+" in dict(sent.headers)["Reply-To"]
