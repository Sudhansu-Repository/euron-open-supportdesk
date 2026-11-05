"""AC10: API keys and webhooks; plus live events across API replicas and system endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import httpx

from tests.integration.conftest import Receiver, Served, Stack, eventually


async def test_api_key_scopes(stack: Stack) -> None:
    org = await stack.org("Keys")
    write = await org.ok(
        "POST", "/api/v1/api-keys", {"name": "CRM sync", "scope": "write"}, status=201
    )
    read = await org.ok(
        "POST", "/api/v1/api-keys", {"name": "BI export", "scope": "read"}, status=201
    )
    assert write["key"].startswith("sdk_")
    writer = stack.client(authorization=f"Bearer {write['key']}")
    reader = stack.client(authorization=f"Bearer {read['key']}")
    created = await writer.post(
        "/api/v1/tickets", json={"customer_email": "api@example.com", "body": "From the CRM"}
    )
    assert created.status_code == 201, created.text
    refused = await reader.post(
        "/api/v1/tickets", json={"customer_email": "api@example.com", "body": "Nope"}
    )
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "insufficient_scope"
    listed = await reader.get("/api/v1/tickets")
    assert [t["subject"] for t in listed.json()["items"]] == ["From the CRM"]
    assert (
        await reader.patch("/api/v1/org/settings", json={"name": "x"})
    ).status_code == 401  # keys never reach settings

    await org.ok("DELETE", f"/api/v1/api-keys/{read['id']}", status=204)
    assert (await reader.get("/api/v1/tickets")).status_code == 401


async def test_webhooks_are_signed_retried_and_disabled(
    stack: Stack, receiver: tuple[str, Receiver]
) -> None:
    url, rec = receiver
    rec.received.clear()
    rec.fail_next, rec.always_fail = 1, False
    org = await stack.org("Hooks")
    hook = await org.ok(
        "POST", "/api/v1/webhooks", {"url": url, "events": ["ticket.created"]}, status=201
    )
    secret = hook["secret"]
    await org.ok(
        "POST",
        "/api/v1/tickets",
        {"customer_email": "hook@example.com", "body": "Webhook please"},
        status=201,
    )

    async def delivered() -> list[dict[str, object]]:
        deliveries = await org.ok("GET", f"/api/v1/webhooks/{hook['id']}/deliveries")
        return [d for d in deliveries if d["status"] == "delivered"]

    done = (await eventually(delivered, wait_s=30))[0]
    assert done["attempts"] == 2  # the first attempt got a 500 and was retried
    request = rec.received[-1]
    signature = request["headers"]["x-supportdesk-signature"]
    timestamp, v1 = (part.split("=", 1)[1] for part in signature.split(","))
    expected = hmac.new(
        secret.encode(), f"{timestamp}.{request['body'].decode()}".encode(), hashlib.sha256
    ).hexdigest()
    assert hmac.compare_digest(v1, expected)
    payload = json.loads(request["body"])
    assert (
        payload["event"] == "ticket.created"
        and payload["data"]["ticket"]["subject"] == "Webhook please"
    )
    assert request["headers"]["x-supportdesk-delivery"] == payload["id"]


async def test_failing_webhook_is_switched_off(
    stack: Stack, receiver: tuple[str, Receiver]
) -> None:
    from supportdesk.integrations import service

    url, rec = receiver
    rec.always_fail = True
    org = await stack.org("Failing hooks")
    hook = await org.ok(
        "POST", "/api/v1/webhooks", {"url": url, "events": ["ticket.created"]}, status=201
    )
    try:
        original = service.DISABLE_AFTER
        for _ in range(service.DISABLE_AFTER):
            await org.ok("POST", "/api/v1/webhooks/" + hook["id"] + "/test", None)

        async def off() -> bool:
            hooks = await org.ok("GET", "/api/v1/webhooks")
            return not hooks[0]["active"] and "failed deliveries" in (
                hooks[0]["disabled_reason"] or ""
            )

        assert await eventually(off, wait_s=60)
        assert original == service.DISABLE_AFTER
    finally:
        rec.always_fail = False


async def test_private_and_metadata_webhook_urls_are_refused(
    stack: Stack, tmp_path: object
) -> None:
    from supportdesk.main import create_app
    from tests.integration.conftest import CSRF, PASSWORD, make_settings

    settings = make_settings(stack.settings.database_url, tmp_path, allow_private_urls=False)  # type: ignore[arg-type]
    served = Served(create_app(settings)).start()
    try:
        client = httpx.AsyncClient(base_url=served.url, headers=CSRF, timeout=20)
        signup = await client.post(
            "/api/v1/auth/signup",
            json={
                "org_name": "Strict",
                "name": "S",
                "email": "strict@acme.test",
                "password": PASSWORD,
            },
        )
        client.headers["authorization"] = f"Bearer {signup.json()['session_token']}"
        for url in (
            "http://127.0.0.1:9/hook",
            "http://10.0.0.5/hook",
            "http://169.254.169.254/latest",
            "http://2852039166/",
        ):
            resp = await client.post(
                "/api/v1/webhooks", json={"url": url, "events": ["ticket.created"]}
            )
            assert resp.status_code == 400, (url, resp.text)
    finally:
        served.stop()


async def test_live_events_reach_a_socket_on_another_api_replica(
    stack: Stack, tmp_path: object
) -> None:
    """An agent's socket on replica B hears a widget message sent to replica A."""
    import websockets

    from supportdesk.main import create_app
    from tests.integration.conftest import make_settings

    replica = Served(create_app(make_settings(stack.settings.database_url, tmp_path))).start()  # type: ignore[arg-type]
    try:
        org = await stack.org("Replicas")
        token = org.client.headers["authorization"][7:]
        url = replica.url.replace("http", "ws") + f"/ws/agent?token={token}"
        async with websockets.connect(url) as ws:
            assert "ready" in await asyncio.wait_for(ws.recv(), 5)
            visitor = await org.visitor()
            await visitor.say("hello, talk to a human", wait=False)

            async def heard() -> bool:
                while True:
                    if "message.created" in str(await asyncio.wait_for(ws.recv(), 5)):
                        return True

            assert await heard()
    finally:
        replica.stop()


async def test_health_readiness_metrics_and_system(stack: Stack) -> None:
    client = stack.client()
    assert (await client.get("/healthz")).json()["status"] == "ok"
    ready = (await client.get("/readyz")).json()
    assert ready["checks"]["postgres"]["ok"]
    assert "supportdesk_jobs_total" in (await client.get("/metrics")).text
    org = await stack.org("System")
    info = await org.ok("GET", "/api/v1/system")
    assert info["embedder"] == "hash:v1" and info["jobs"]["dead"] >= 0


async def test_large_and_malformed_bodies_are_refused_before_routes(stack: Stack) -> None:
    # Claim a 2 MB body and send none of it: the API answers 413 from the header alone,
    # before reading or parsing anything.
    host, port = stack.api_url.removeprefix("http://").split(":")
    reader, writer = await asyncio.open_connection(host, int(port))
    writer.write(
        b"POST /api/v1/auth/login HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
        b"Content-Length: 2000000\r\n\r\n"
    )
    await writer.drain()
    status_line = await asyncio.wait_for(reader.readline(), 5)
    writer.close()
    assert b" 413 " in status_line
    client = stack.client()
    surrogate = await client.post(
        "/api/v1/auth/login",
        content=b'{"email": "\\ud800@x.y", "password": "p"}',
        headers={"content-type": "application/json"},
    )
    assert surrogate.status_code == 422


async def test_a_socket_with_a_bad_session_is_closed_with_4401(stack: Stack) -> None:
    import websockets

    url = stack.api_url.replace("http", "ws") + "/ws/agent?token=not-a-session"
    import pytest

    async with websockets.connect(url) as ws:
        with pytest.raises(websockets.ConnectionClosed) as closed:
            await asyncio.wait_for(ws.recv(), 5)
    assert closed.value.code == 4401
