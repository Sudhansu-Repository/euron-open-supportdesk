"""Settings, agents, customers, drafts, canned replies, SLAs and the rest of the widget and
portal actions: every admin surface answers, validates and stays inside its organisation."""

from __future__ import annotations

import httpx

from supportdesk.core.mail import OUTBOX
from tests.integration.conftest import Stack


async def test_settings_validate_and_seal_the_key(stack: Stack) -> None:
    org = await stack.org("Settings")
    current = await org.ok("GET", "/api/v1/org/settings")
    assert current["ai"]["provider"] == "extractive" and current["ai_key_set"] is False
    bad = await org.client.patch("/api/v1/org/settings", json={"categories": ["Has Spaces"]})
    assert bad.status_code == 422
    remote = await org.client.patch(
        "/api/v1/org/settings", json={"ai": {"provider": "openai", "embedder": "openai"}}
    )
    assert remote.status_code == 422  # a remote embedder needs a model and a size
    meta = await org.client.patch(
        "/api/v1/org/settings",
        json={"ai": {"provider": "openai", "base_url": "http://169.254.169.254"}},
    )
    assert meta.status_code == 422
    saved = await org.patch_settings(
        name="Renamed",
        ai_api_key="sk-secret-value",
        categories=["billing", "bugs"],
        brand={"company_name": "Renamed Co", "accent_color": "#123456"},
    )
    assert (
        saved["org"]["name"] == "Renamed"
        and saved["ai_key_set"]
        and saved["categories"] == ["billing", "bugs"]
    )
    assert "sk-secret-value" not in str(saved)
    cleared = await org.patch_settings(ai_api_key="")
    assert cleared["ai_key_set"] is False


async def test_ai_connection_test(stack: Stack, mock: httpx.AsyncClient) -> None:
    org = await stack.org("AI test")
    extractive = await org.ok("POST", "/api/v1/org/ai/test")
    assert extractive["ok"] and extractive["provider"] == "extractive"
    await org.set_ai("anthropic")
    anthropic = await org.ok("POST", "/api/v1/org/ai/test")
    assert anthropic["ok"] and anthropic["provider"] == "anthropic"
    await mock.post("/admin/mode", json={"mode": "fail"})
    failing = await org.ok("POST", "/api/v1/org/ai/test")
    assert failing["ok"] is False and "503" in failing["message"]


async def test_anthropic_provider_answers(stack: Stack, mock: httpx.AsyncClient) -> None:
    org = await stack.org("Anthropic", provider="anthropic")
    await org.faq()
    visitor = await org.visitor()
    answer = visitor.last(await visitor.say("Which payment methods do you accept?"))
    assert answer["author_type"] == "ai" and "Visa" in answer["body"]
    assert (await mock.get("/stats")).json()["by_endpoint"]["anthropic"] >= 1


async def test_teams_prices_and_agents(stack: Stack) -> None:
    org = await stack.org("People")
    agent = await org.agent("agent")
    users = await org.ok("GET", "/api/v1/users")
    agent_id = next(u["id"] for u in users if u["role"] == "agent")
    team = await org.ok(
        "POST", "/api/v1/org/teams", {"name": "Tier 2", "member_ids": [agent_id]}, status=201
    )
    other = await stack.org("Elsewhere")
    stranger = (await other.ok("GET", "/api/v1/users"))[0]["id"]
    bad = await org.client.post(
        "/api/v1/org/teams", json={"name": "Mixed", "member_ids": [stranger]}
    )
    assert bad.status_code == 400
    renamed = await org.ok(
        "PUT", f"/api/v1/org/teams/{team['id']}", {"name": "Tier Two", "member_ids": []}
    )
    assert renamed["member_ids"] == []
    await org.ok("DELETE", f"/api/v1/org/teams/{team['id']}", status=204)

    prices = await org.ok("GET", "/api/v1/org/prices")
    assert any(p["model"] == "gpt-4o-mini" and p["default"] for p in prices)
    custom = await org.ok(
        "PUT",
        "/api/v1/org/prices",
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "input_per_mtok": "0.2",
            "output_per_mtok": "0.8",
        },
    )
    assert not any(
        p["default"]
        for p in await org.ok("GET", "/api/v1/org/prices")
        if p["model"] == "gpt-4o-mini"
    )
    await org.ok("DELETE", f"/api/v1/org/prices/{custom['id']}", status=204)

    updated = await org.ok("PATCH", f"/api/v1/users/{agent_id}", {"capacity": 3, "role": "admin"})
    assert updated["capacity"] == 3 and updated["role"] == "admin"
    assert (await agent.get("/api/v1/auth/me")).status_code == 401  # a new role ends old sessions
    disabled = await org.ok("PATCH", f"/api/v1/users/{agent_id}", {"disabled": True})
    assert disabled["disabled"] and disabled["availability"] == "offline"
    self_disable = await org.client.patch(
        f"/api/v1/users/{org.owner['id']}", json={"disabled": True}
    )
    assert self_disable.status_code == 400

    invite = await org.ok(
        "POST", "/api/v1/invitations", {"email": "later@acme.test", "role": "agent"}, status=201
    )
    assert [i["email"] for i in await org.ok("GET", "/api/v1/invitations")] == ["later@acme.test"]
    await org.ok("DELETE", f"/api/v1/invitations/{invite['id']}", status=204)
    token = (
        next(m for m in reversed(OUTBOX) if m.to == "later@acme.test")
        .text.split("token=")[1]
        .split()[0]
    )
    gone = await stack.client().get(f"/api/v1/auth/invitations/{token}")
    assert gone.status_code == 410
    duplicate = await org.client.post(
        "/api/v1/invitations", json={"email": org.email, "role": "agent"}
    )
    assert duplicate.status_code == 409


async def test_customers_edit_search_and_merge(stack: Stack) -> None:
    org = await stack.org("Customers")
    first = await org.ok(
        "POST",
        "/api/v1/tickets",
        {"customer_email": "ann@example.com", "customer_name": "Ann", "body": "One"},
        status=201,
    )
    second = await org.ok(
        "POST",
        "/api/v1/tickets",
        {"customer_external_id": "crm-7", "customer_name": "Ann B", "body": "Two"},
        status=201,
    )
    keep, drop = first["customer"]["id"], second["customer"]["id"]
    clash = await org.client.patch(f"/api/v1/customers/{drop}", json={"email": "ann@example.com"})
    assert clash.status_code == 400 and clash.json()["error"]["code"] == "email_taken"
    found = await org.ok("GET", "/api/v1/customers?q=ann")
    assert {c["id"] for c in found} == {keep, drop}
    merged = await org.ok("POST", "/api/v1/customers/merge", {"keep_id": keep, "drop_id": drop})
    assert merged["external_id"] == "crm-7"
    profile = await org.ok("GET", f"/api/v1/customers/{keep}")
    assert profile["ticket_count"] == 2 and len(profile["tickets"]) == 2
    assert (await org.ok("GET", f"/api/v1/customers/{drop}"))[
        "id"
    ] == keep  # the old id follows the merge
    vip = await org.ok(
        "PATCH",
        f"/api/v1/customers/{keep}",
        {"vip": True, "name": "Ann Archer", "attributes": {"plan": "Plus"}},
    )
    assert (
        vip["vip"]
        and (await org.ok("GET", "/api/v1/customers?vip=true"))[0]["name"] == "Ann Archer"
    )


async def test_drafts_macros_and_sla_policies(stack: Stack, mock: httpx.AsyncClient) -> None:
    org = await stack.org("Agent tools")
    await org.faq()
    ticket = await org.ok(
        "POST",
        "/api/v1/tickets",
        {"customer_email": "q@example.com", "body": "How long does shipping take?"},
        status=201,
    )
    draft = await org.ok("POST", f"/api/v1/tickets/{ticket['id']}/draft", {"tone": "friendly"})
    assert (
        draft["method"] == "extractive" and "business days" in draft["body"] and draft["citations"]
    )
    await org.set_ai("openai")
    model_draft = await org.ok(
        "POST",
        f"/api/v1/tickets/{ticket['id']}/draft",
        {"tone": "formal", "instructions": "be brief"},
    )
    assert model_draft["method"] == "model" and model_draft["tokens"] > 0

    macro = await org.ok("POST", "/api/v1/macros", {"title": "Hi", "body": "Hello!"}, status=201)
    edited = await org.ok(
        "PUT", f"/api/v1/macros/{macro['id']}", {"title": "Hello", "body": "Hello there!"}
    )
    assert edited["title"] == "Hello"
    await org.ok("DELETE", f"/api/v1/macros/{macro['id']}", status=204)
    assert (
        await org.client.post(
            f"/api/v1/tickets/{ticket['id']}/messages", json={"body": "x", "macro_id": macro["id"]}
        )
    ).status_code == 404

    policies = await org.ok("GET", "/api/v1/sla-policies")
    assert [p["priority"] for p in policies] == ["urgent", "high", "normal", "low"]
    updated = await org.ok(
        "PUT",
        "/api/v1/sla-policies",
        [
            {
                "priority": "urgent",
                "first_response_minutes": 15,
                "resolution_minutes": 120,
                "enabled": True,
            }
        ],
    )
    assert next(p for p in updated if p["priority"] == "urgent")["first_response_minutes"] == 15
    tagged = await org.ok(
        "PATCH",
        f"/api/v1/tickets/{ticket['id']}",
        {"priority": "urgent", "unassign": True, "clear_team": True},
    )
    assert tagged["assignee_id"] is None and tagged["team_id"] is None


async def test_widget_feedback_rating_and_email_capture(
    stack: Stack, mock: httpx.AsyncClient
) -> None:
    org = await stack.org("Widget extras", provider="openai")
    await org.faq()
    visitor = await org.visitor()
    answer = visitor.last(await visitor.say("How long does shipping take?"))
    unhelpful = await visitor.client.post(
        f"/api/v1/widget/messages/{answer['id']}/feedback", json={"helpful": False}
    )
    assert unhelpful.status_code == 200
    ticket = await org.ticket(str(visitor.ticket_id))
    assert "answer_unhelpful" in ticket["escalation_reasons"] and ticket["handled_by"] == "human"
    early = await visitor.client.post(
        f"/api/v1/widget/tickets/{visitor.ticket_id}/rating", json={"score": 5}
    )
    assert early.status_code == 400  # rate once resolved
    await org.ok("PATCH", f"/api/v1/tickets/{visitor.ticket_id}", {"status": "resolved"})
    rated = await visitor.client.post(
        f"/api/v1/widget/tickets/{visitor.ticket_id}/rating", json={"score": 4, "comment": "ok"}
    )
    assert (
        rated.status_code == 200 and (await org.ticket(str(visitor.ticket_id)))["csat_score"] == 4
    )
    email = await visitor.client.post(
        "/api/v1/widget/email", json={"email": "Visitor@Example.com", "name": "Vic"}
    )
    assert email.status_code == 200
    customer_id = (await org.ticket(str(visitor.ticket_id)))["customer"]["id"]
    profile = await org.ok("GET", f"/api/v1/customers/{customer_id}")
    # An address typed into the widget is an unverified contact, not the identity.
    assert (
        profile["email"] is None and profile["attributes"]["contact_email"] == "visitor@example.com"
    )
    resumed = await stack.client(origin="http://localhost:4810").post(
        f"/api/v1/widget/{await org.widget_key()}/session", json={"token": visitor.session["token"]}
    )
    assert (
        resumed.json()["ticket_id"] == visitor.ticket_id
        and resumed.json()["customer_name"] == "Vic"
    )
    human = await visitor.client.post(f"/api/v1/widget/tickets/{visitor.ticket_id}/human")
    assert human.status_code == 200


async def test_portal_reply_feedback_and_rating(stack: Stack, mock: httpx.AsyncClient) -> None:
    org = await stack.org("Portal extras", provider="openai")
    await org.faq()
    public = stack.client()
    await public.post(f"/api/v1/portal/{org.slug}/link", json={"email": "pia@example.com"})
    token = (
        next(m for m in reversed(OUTBOX) if m.to == "pia@example.com")
        .text.split("token=")[1]
        .split()[0]
    )
    session = (
        await public.post(f"/api/v1/portal/{org.slug}/session", json={"token": token})
    ).json()
    portal = stack.client(authorization=f"Bearer {session['token']}")
    created = (
        await portal.post(
            f"/api/v1/portal/{org.slug}/tickets",
            json={"subject": "Shipping", "body": "How long does shipping take?"},
        )
    ).json()

    async def answered() -> dict[str, object] | None:
        detail = (await portal.get(f"/api/v1/portal/{org.slug}/tickets/{created['id']}")).json()
        return next((m for m in detail["messages"] if m["author_type"] == "ai"), None)

    import asyncio

    ai = None
    for _ in range(100):
        ai = await answered()
        if ai:
            break
        await asyncio.sleep(0.1)
    assert ai is not None
    ok = await portal.post(
        f"/api/v1/portal/{org.slug}/messages/{ai['id']}/feedback", json={"helpful": True}
    )
    assert ok.status_code == 200
    rated = await portal.post(
        f"/api/v1/portal/{org.slug}/tickets/{created['id']}/rating", json={"score": 5}
    )
    assert rated.status_code == 200
    reply = await portal.post(
        f"/api/v1/portal/{org.slug}/tickets/{created['id']}/messages", json={"body": "Thanks!"}
    )
    assert reply.status_code == 200
    assert reply.json()["status"] == "open"  # a new message reopens the conversation
