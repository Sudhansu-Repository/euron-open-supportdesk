"""AC8: the helpdesk. Lifecycle, notes, canned replies, SLAs, triage, audit, roles and
tenant isolation; plus sign-in, lockout and invitations."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.conftest import CSRF, PASSWORD, Stack


async def _api_ticket(
    org: object, body: str = "My bulb keeps disconnecting", **extra: object
) -> dict[str, object]:
    result: dict[str, object] = await org.ok(
        "POST",
        "/api/v1/tickets",
        {  # type: ignore[attr-defined]
            "customer_email": "pat@example.com",
            "customer_name": "Pat Doe",
            "body": body,
            **extra,
        },
        status=201,
    )
    return result


async def test_ticket_lifecycle_with_notes_and_audit(stack: Stack) -> None:
    org = await stack.org("Lifecycle")
    ticket = await _api_ticket(org)
    assert ticket["status"] == "open" and ticket["handled_by"] == "human" and ticket["number"] == 1

    me = org.owner["id"]
    ticket = await org.ok(
        "PATCH",
        f"/api/v1/tickets/{ticket['id']}",
        {
            "priority": "urgent",
            "category": "technical",
            "tags": ["Bulb", "wifi"],
            "assignee_id": me,
        },
    )
    assert (
        ticket["priority"] == "urgent"
        and ticket["tags"] == ["bulb", "wifi"]
        and ticket["assignee_id"] == me
    )
    assert ticket["first_response_due_at"] is not None

    await org.ok(
        "POST",
        f"/api/v1/tickets/{ticket['id']}/messages",
        {"body": "Customer is on firmware 1.2", "note": True},
        status=201,
    )
    reply = await org.ok(
        "POST",
        f"/api/v1/tickets/{ticket['id']}/messages",
        {"body": "Please update the firmware."},
        status=201,
    )
    ticket = await org.ticket(str(ticket["id"]))
    assert ticket["status"] == "pending" and ticket["human_replied_at"] is not None
    assert reply["kind"] == "reply"

    ticket = await org.ok("PATCH", f"/api/v1/tickets/{ticket['id']}", {"status": "resolved"})
    assert ticket["resolved_at"] is not None
    ticket = await org.ok("PATCH", f"/api/v1/tickets/{ticket['id']}", {"status": "open"})
    assert ticket["reopened_count"] == 1 and ticket["resolved_at"] is None
    types = [e["type"] for e in ticket["events"]]
    assert {"priority", "category", "assigned", "note", "status"} <= set(types)

    audit = await org.ok("GET", "/api/v1/audit?action=ticket.")
    assert {"ticket.updated", "ticket.replied", "ticket.note"} <= {
        a["action"] for a in audit["items"]
    }


async def test_internal_notes_never_reach_the_customer(stack: Stack) -> None:
    org = await stack.org("Notes")
    visitor = await org.visitor()
    conv = await visitor.say("talk to a human please")
    await org.ok(
        "POST",
        f"/api/v1/tickets/{conv['ticket_id']}/messages",
        {"body": "VIP, be extra careful", "note": True},
        status=201,
    )
    await org.ok(
        "POST", f"/api/v1/tickets/{conv['ticket_id']}/messages", {"body": "Hello!"}, status=201
    )
    bodies = [m["body"] for m in (await visitor.conversation())["messages"]]
    assert "Hello!" in bodies and "VIP, be extra careful" not in bodies


async def test_canned_replies_and_bulk_actions(stack: Stack) -> None:
    org = await stack.org("Macros")
    macro = await org.ok(
        "POST",
        "/api/v1/macros",
        {"title": "Ask for order", "body": "What is your order number?"},
        status=201,
    )
    ticket = await _api_ticket(org)
    await org.ok(
        "POST",
        f"/api/v1/tickets/{ticket['id']}/messages",
        {"body": macro["body"], "macro_id": macro["id"]},
        status=201,
    )
    assert (await org.ok("GET", "/api/v1/macros"))[0]["uses"] == 1
    others = [await _api_ticket(org, f"Question {i}") for i in range(3)]
    result = await org.ok(
        "POST",
        "/api/v1/tickets/bulk",
        {"ids": [t["id"] for t in others], "status": "closed", "add_tags": ["batch"]},
    )
    assert result["updated"] == 3
    closed = await org.ok("GET", "/api/v1/tickets?view=resolved&tag=batch")
    assert len(closed["items"]) == 3


async def test_search_and_views(stack: Stack) -> None:
    org = await stack.org("Search")
    first = await _api_ticket(org, "The bridge shows a blinking orange light")
    await _api_ticket(org, "Invoice address is wrong")
    found = await org.ok("GET", "/api/v1/tickets?q=orange")
    assert [t["id"] for t in found["items"]] == [first["id"]]
    by_number = await org.ok("GET", f"/api/v1/tickets?q=%23{first['number']}")
    assert by_number["items"][0]["id"] == first["id"]
    counts = await org.ok("GET", "/api/v1/tickets/counts")
    assert counts["all"] == 2


async def test_keyset_pagination_returns_every_ticket_once(stack: Stack) -> None:
    org = await stack.org("Pages")
    created = {str((await _api_ticket(org, f"Question number {i}"))["id"]) for i in range(7)}
    seen: list[str] = []
    cursor = None
    while True:
        page = await org.ok(
            "GET", "/api/v1/tickets?limit=3" + (f"&cursor={cursor}" if cursor else "")
        )
        seen += [t["id"] for t in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == sorted(created) and len(seen) == 7


async def test_sla_breach_is_flagged_by_the_worker(stack: Stack) -> None:
    org = await stack.org("SLA")
    ticket = await _api_ticket(org)
    engine = create_async_engine(stack.settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE tickets SET sla_next_due_at = :due, first_response_due_at = :due WHERE id = :t"
            ),
            {"due": datetime.now(UTC) - timedelta(minutes=1), "t": ticket["id"]},
        )
    await engine.dispose()
    from supportdesk.core.container import Container
    from supportdesk.tickets.tasks import sla_scan

    container = Container.build(stack.settings)
    try:
        assert await sla_scan(container) >= 1
    finally:
        await container.close()
    detail = await org.ticket(str(ticket["id"]))
    assert detail["sla_state"] == "breached"
    assert any(e["type"] == "sla_breached" for e in detail["events"])


async def test_ai_triage_sets_category_priority_and_sentiment(
    stack: Stack, mock: httpx.AsyncClient
) -> None:
    org = await stack.org("Triage", provider="openai")
    visitor = await org.visitor()
    conv = await visitor.say("This is terrible!!! I was charged twice on my invoice, fix it")
    ticket = await org.ticket(conv["ticket_id"])
    assert ticket["category"] == "billing" and ticket["sentiment"] == "negative"
    assert ticket["priority"] in ("high", "urgent")


async def test_agents_cannot_change_settings_and_orgs_cannot_see_each_other(stack: Stack) -> None:
    acme = await stack.org("Acme")
    globex = await stack.org("Globex")
    secret = await _api_ticket(globex, "Globex internal question")
    agent = await acme.agent("agent")
    resp = await agent.patch("/api/v1/org/settings", json={"name": "Hacked"})
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "insufficient_role"
    assert (await agent.get(f"/api/v1/tickets/{secret['id']}")).status_code == 404
    assert (await acme.client.get(f"/api/v1/tickets/{secret['id']}")).status_code == 404
    assert all(t["id"] != secret["id"] for t in (await acme.ok("GET", "/api/v1/tickets"))["items"])
    patch = await acme.client.patch(f"/api/v1/tickets/{secret['id']}", json={"status": "closed"})
    assert patch.status_code == 404
    customers = await acme.ok("GET", "/api/v1/customers")
    assert all(c["email"] != "pat@example.com" for c in customers)


async def test_lockout_is_per_address_and_does_not_lock_the_owner_elsewhere(stack: Stack) -> None:
    org = await stack.org("Lockout")
    attacker = stack.client()
    for _ in range(5):
        resp = await attacker.post(
            "/api/v1/auth/login", json={"email": org.email, "password": "wrong-password-1"}
        )
        assert resp.status_code == 401
    locked = await attacker.post(
        "/api/v1/auth/login", json={"email": org.email, "password": PASSWORD}
    )
    assert locked.json()["error"]["code"] == "account_locked"
    # Only this (account, address) pair is locked, not the account: the per-account
    # threshold (50) is far away, so the owner can still sign in from anywhere else.
    from supportdesk.auth.service import PER_ACCOUNT, _key

    pepper = stack.settings.token_pepper
    engine = create_async_engine(stack.settings.database_url)
    async with engine.begin() as conn:
        account = await conn.execute(
            text("SELECT failures, locked_until FROM login_failures WHERE key = :k"),
            {"k": _key(pepper, "acct", org.email.lower())},
        )
        failures, locked_until = account.one()
    await engine.dispose()
    assert failures == 5 < PER_ACCOUNT and locked_until is None


async def test_password_change_ends_other_sessions(stack: Stack) -> None:
    org = await stack.org("Passwords")
    second = stack.client(**CSRF)
    login = await second.post("/api/v1/auth/login", json={"email": org.email, "password": PASSWORD})
    second.headers["authorization"] = f"Bearer {login.json()['session_token']}"
    old = org.client.headers["authorization"]
    fresh = await org.ok(
        "POST",
        "/api/v1/auth/password",
        {"current_password": PASSWORD, "new_password": "Brand-New-Pass-9"},
    )
    assert (await second.get("/api/v1/auth/me")).status_code == 401
    assert (await stack.client(authorization=old).get("/api/v1/auth/me")).status_code == 401
    renewed = stack.client(authorization=f"Bearer {fresh['session_token']}")
    assert (await renewed.get("/api/v1/auth/me")).status_code == 200


async def test_last_owner_cannot_be_demoted(stack: Stack) -> None:
    org = await stack.org("Owners")
    resp = await org.client.patch(f"/api/v1/users/{org.owner['id']}", json={"role": "admin"})
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "last_owner"


async def test_logout_revokes_the_session(stack: Stack) -> None:
    org = await stack.org("Logout")
    token = org.client.headers["authorization"]
    await org.ok("POST", "/api/v1/auth/logout")
    again = stack.client(authorization=token)
    assert (await again.get("/api/v1/auth/me")).status_code == 401


async def test_concurrent_ticket_numbers_are_unique(stack: Stack) -> None:
    org = await stack.org("Numbers")
    tickets = await asyncio.gather(*(_api_ticket(org, f"Parallel {i}") for i in range(20)))
    numbers = sorted(int(t["number"]) for t in tickets)  # type: ignore[call-overload]
    assert numbers == list(range(1, 21))
