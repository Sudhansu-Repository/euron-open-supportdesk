"""Integration harness: the real API and the real worker, each on its own thread and event
loop, against real Postgres (pgvector) and Redis, with the mock AI and two small fixture
servers (a web site to import, a webhook receiver).

    make test-integration      (starts Postgres and Redis if needed)

Every test signs up its own organisation, so tests are isolated by tenant, which also
exercises tenant scoping on every request. The database is dropped and rebuilt by the
migrations once per run (so the migrations are tested too). The suite refuses any
database whose name does not contain "test" and any non-local host unless
ALLOW_REMOTE_TEST_DB=true.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pytest
import redis.asyncio as aioredis
import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from supportdesk.core.config import Settings

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://supportdesk:supportdesk@localhost:4842/supportdesk_test",
)
TEST_REDIS = os.environ.get("TEST_REDIS_URL", "redis://localhost:4879/15")
CSRF = {"x-supportdesk-csrf": "1"}
PASSWORD = "Test-Pass-12345"


def _guard(url: str) -> None:
    parsed = urlparse(url.replace("+asyncpg", ""))
    if "test" not in (parsed.path or ""):
        raise RuntimeError(f"refusing {parsed.path!r}: the test database name must contain 'test'")
    if (
        parsed.hostname not in ("localhost", "127.0.0.1", "postgres")
        and os.environ.get("ALLOW_REMOTE_TEST_DB") != "true"
    ):
        raise RuntimeError("refusing a non-local test database (set ALLOW_REMOTE_TEST_DB=true)")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Served:
    """An ASGI app (or import string) served by uvicorn on a thread, with its own loop."""

    def __init__(self, app: Any, port: int | None = None) -> None:
        self.port = port or free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(
            app, host="127.0.0.1", port=self.port, log_level="warning", ws="websockets"
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self, health: str = "/healthz") -> Served:
        self.thread.start()
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                if httpx.get(self.url + health, timeout=1).status_code < 500:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise RuntimeError(f"server on {self.url} did not start")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=15)


class WorkerThread:
    """The real background worker on its own thread and event loop."""

    def __init__(self, settings: Settings, name: str = "test-worker") -> None:
        self.settings = settings
        self.name = name
        self.loop = asyncio.new_event_loop()
        self.worker: Any = None
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    async def _main(self) -> None:
        from supportdesk.core.container import Container
        from supportdesk.worker import Worker, import_handlers

        import_handlers()
        container = Container.build(self.settings)
        self.worker = Worker(container, self.name)
        self.ready.set()
        try:
            await self.worker.run()
        finally:
            await container.close()

    def start(self) -> WorkerThread:
        self.thread.start()
        self.ready.wait(30)
        return self

    def stop(self) -> None:
        if self.worker is not None:
            self.loop.call_soon_threadsafe(self.worker.stopping.set)
        self.thread.join(timeout=30)


# ----- fixture servers -----

SITE: dict[str, tuple[str, str]] = {
    "/robots.txt": ("text/plain", "User-agent: *\nDisallow: /private\n"),
    "/sitemap.xml": (
        "application/xml",
        "<urlset><url><loc>/docs/billing</loc></url><url><loc>/docs/teams</loc></url>"
        "<url><loc>/private/secret</loc></url></urlset>",
    ),
    "/docs/billing": (
        "text/html",
        "<html><head><title>Billing help</title></head><body><nav>menu</nav><main><h1>Billing</h1>"
        "<h2>Invoices</h2><p>Invoices are emailed on the first business day of every month and can be "
        "downloaded from the Billing page.</p></main></body></html>",
    ),
    "/docs/teams": (
        "text/html",
        "<html><head><title>Teams</title></head><body><main><h1>Teams</h1><p>Owners can invite up to "
        "twenty teammates on the Growth plan.</p></main></body></html>",
    ),
    "/private/secret": ("text/html", "<html><body><p>Do not import this page.</p></body></html>"),
    "/redirect-to-metadata": ("redirect", "http://169.254.169.254/latest/meta-data/"),
}


async def _site(request: Request) -> Response:
    entry = SITE.get(request.url.path)
    if entry is None:
        return PlainTextResponse("not found", status_code=404)
    kind, body = entry
    if kind == "redirect":
        return Response(status_code=302, headers={"location": body})
    return Response(body, media_type=kind)


@dataclass
class Receiver:
    """A webhook receiver that records requests and can fail on purpose."""

    received: list[dict[str, Any]] = field(default_factory=list)
    fail_next: int = 0
    always_fail: bool = False

    async def __call__(self, request: Request) -> Response:
        body = await request.body()
        self.received.append({"headers": dict(request.headers), "body": body, "at": time.time()})
        if self.always_fail or self.fail_next > 0:
            self.fail_next = max(0, self.fail_next - 1)
            return PlainTextResponse("nope", status_code=500)
        return PlainTextResponse("ok")


# ----- session fixtures -----


@pytest.fixture(scope="session")
def mock_ai() -> Iterator[str]:
    served = Served("mockai.app:app").start()
    yield served.url
    served.stop()


@pytest.fixture(scope="session")
def site() -> Iterator[str]:
    app = Starlette(routes=[Route("/{path:path}", _site)])
    served = Served(app).start("/robots.txt")
    yield served.url
    served.stop()


@pytest.fixture(scope="session")
def receiver() -> Iterator[tuple[str, Receiver]]:
    rec = Receiver()

    async def hook(request: Request) -> Response:
        # A plain function: Starlette would treat a callable instance as a raw ASGI app.
        return await rec(request)

    async def healthz(_: Request) -> Response:
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/hook", hook, methods=["POST"]), Route("/healthz", healthz)])
    served = Served(app).start()
    yield f"{served.url}/hook", rec
    served.stop()


@pytest.fixture(scope="session")
async def database() -> AsyncIterator[str]:
    """A fresh database built by the migrations."""
    _guard(TEST_DB)
    admin_url = TEST_DB.rsplit("/", 1)[0] + "/postgres"
    name = TEST_DB.rsplit("/", 1)[1]
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    await engine.dispose()
    from supportdesk.migrations.runner import upgrade

    await asyncio.to_thread(upgrade, TEST_DB)
    if TEST_REDIS:
        r = aioredis.Redis.from_url(TEST_REDIS)
        await r.flushdb()
        await r.aclose()
    yield TEST_DB


def make_settings(database: str, tmp: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "database_url": database,
        "redis_url": TEST_REDIS,
        "session_secret": "test-only-session-secret-with-32-plus-bytes",
        "token_pepper": "test-only-token-pepper-with-32-plus-bytes!",
        "local_master_key": "test-only-master-key-with-32-plus-bytes-ok",
        "local_storage_dir": str(tmp / "objects"),
        "public_url": "http://localhost:4810",
        "public_api_url": "http://localhost:4830",
        "cors_origins": ["http://localhost:4810"],
        "mail_backend": "log",
        "embedder": "hash",
        "allow_private_urls": True,
        "ai_allow_private_endpoints": True,
        "ai_timeout_s": 5,
        "worker_poll_interval_s": 0.5,
        "job_lease_s": 10,
        "widget_rpm": 1000,
        "signup_rpm": 10_000,
        "login_rpm": 10_000,
        # The option matrix (make test-matrix) reruns the suite against Floci S3 and KMS.
        "key_mode": os.environ.get("TEST_KEY_MODE", "local"),
        "storage": os.environ.get("TEST_STORAGE", "local"),
        "aws_endpoint_url": os.environ.get("TEST_AWS_ENDPOINT"),
        "s3_force_path_style": True,
        "kms_key_id": os.environ.get("TEST_KMS_KEY_ID", "alias/supportdesk-local"),
        "objects_bucket": os.environ.get("TEST_OBJECTS_BUCKET", "supportdesk-local-objects"),
    }
    values.update(overrides)
    return Settings(**values)


@dataclass
class Stack:
    api_url: str
    settings: Settings
    mock_ai_url: str
    site_url: str
    worker: WorkerThread

    def client(self, **headers: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.api_url, timeout=30, headers=headers)

    async def org(self, name: str = "Acme", **ai: Any) -> Org:
        """Sign up a fresh organisation and return a helper signed in as its owner."""
        client = self.client(**CSRF)
        email = f"owner-{time.monotonic_ns()}@acme.test"
        resp = await client.post(
            "/api/v1/auth/signup",
            json={"org_name": name, "name": "Olivia Owner", "email": email, "password": PASSWORD},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        client.headers["authorization"] = f"Bearer {data['session_token']}"
        org = Org(self, client, data["user"], email, data["org_slug"])
        if ai:
            await org.set_ai(**ai)
        return org


@dataclass
class Org:
    stack: Stack
    client: httpx.AsyncClient
    owner: dict[str, Any]
    email: str
    slug: str
    _widget_key: str | None = None

    async def ok(
        self, method: str, path: str, json: Any = None, status: int = 200, **kw: Any
    ) -> Any:
        resp = await self.client.request(method, path, json=json, **kw)
        assert resp.status_code == status, f"{method} {path}: {resp.status_code} {resp.text}"
        return resp.json() if resp.content else None

    async def set_ai(self, provider: str = "openai", **config: Any) -> None:
        ai: dict[str, Any] = {"provider": provider}
        if provider in ("openai", "ollama", "anthropic"):
            base = self.stack.mock_ai_url + ("/v1" if provider == "openai" else "")
            ai.update(base_url=base, answer_model="gpt-4o-mini", triage_model="gpt-4o-mini")
        ai.update(config)
        await self.ok(
            "PATCH", "/api/v1/org/settings", {"ai": ai, "ai_api_key": "sk-test-not-a-real-key"}
        )

    async def patch_settings(self, **body: Any) -> dict[str, Any]:
        result: dict[str, Any] = await self.ok("PATCH", "/api/v1/org/settings", body)
        return result

    async def upload(
        self, filename: str, data: bytes, content_type: str, title: str | None = None
    ) -> dict[str, Any]:
        files = {"file": (filename, data, content_type)}
        form = {"title": title} if title else {}
        resp = await self.client.post("/api/v1/knowledge/sources/upload", files=files, data=form)
        assert resp.status_code == 201, resp.text
        return await self.wait_source(resp.json()["id"])

    async def wait_source(self, source_id: str, wait_s: float = 30) -> dict[str, Any]:
        deadline = time.monotonic() + wait_s
        while True:
            sources = await self.ok("GET", "/api/v1/knowledge/sources")
            source = next(s for s in sources if s["id"] == source_id)
            if source["status"] in ("ready", "failed"):
                return dict(source)
            if time.monotonic() > deadline:
                raise AssertionError(f"source never finished: {source}")
            await asyncio.sleep(0.2)

    async def faq(self, rows: list[tuple[str, str]] | None = None) -> dict[str, Any]:
        rows = rows or FAQ
        csv = "question,answer\n" + "\n".join(f'"{q}","{a}"' for q, a in rows)
        return await self.upload("faq.csv", csv.encode(), "text/csv", "FAQ")

    async def widget_key(self) -> str:
        if self._widget_key is None:
            inboxes = await self.ok("GET", "/api/v1/inboxes")
            self._widget_key = next(i["public_key"] for i in inboxes if i["channel"] == "widget")
        return self._widget_key

    async def visitor(self, **identity: Any) -> Visitor:
        key = await self.widget_key()
        client = self.stack.client(origin="http://localhost:4810")
        resp = await client.post(f"/api/v1/widget/{key}/session", json=identity)
        assert resp.status_code == 200, resp.text
        client.headers["authorization"] = f"Bearer {resp.json()['token']}"
        return Visitor(client, resp.json())

    async def ticket(self, ticket_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await self.ok("GET", f"/api/v1/tickets/{ticket_id}")
        return result

    async def agent(self, role: str = "agent", availability: str = "online") -> httpx.AsyncClient:
        """Invite an agent, accept the invitation, and return a signed-in client."""
        from supportdesk.core.mail import OUTBOX

        email = f"{role}-{time.monotonic_ns()}@acme.test"
        await self.ok("POST", "/api/v1/invitations", {"email": email, "role": role}, status=201)
        mail = next(m for m in reversed(OUTBOX) if m.to == email)
        token = mail.text.split("token=")[1].split()[0]
        client = self.stack.client(**CSRF)
        resp = await client.post(
            "/api/v1/auth/invitations/accept",
            json={"token": token, "name": f"{role.title()} Person", "password": PASSWORD},
        )
        assert resp.status_code == 201, resp.text
        client.headers["authorization"] = f"Bearer {resp.json()['session_token']}"
        if availability != "online":
            await client.patch("/api/v1/me", json={"availability": availability})
        client.user = resp.json()["user"]  # type: ignore[attr-defined]
        return client


@dataclass
class Visitor:
    client: httpx.AsyncClient
    session: dict[str, Any]
    ticket_id: str | None = None

    async def say(self, body: str, wait: bool = True, wait_s: float = 20) -> dict[str, Any]:
        resp = await self.client.post(
            "/api/v1/widget/messages", json={"body": body, "ticket_id": self.ticket_id}
        )
        assert resp.status_code == 201, resp.text
        conv: dict[str, Any] = resp.json()
        self.ticket_id = conv["ticket_id"]
        if not wait:
            return conv
        return await self.wait_reply(wait_s)

    async def conversation(self) -> dict[str, Any]:
        resp = await self.client.get(f"/api/v1/widget/tickets/{self.ticket_id}")
        assert resp.status_code == 200, resp.text
        result: dict[str, Any] = resp.json()
        return result

    async def wait_reply(self, wait_s: float = 20) -> dict[str, Any]:
        """The conversation once the last message is no longer the customer's."""
        deadline = time.monotonic() + wait_s
        while True:
            conv = await self.conversation()
            if conv["messages"] and conv["messages"][-1]["author_type"] != "customer":
                return conv
            if time.monotonic() > deadline:
                raise AssertionError(f"no reply: {conv['messages'][-1:]}")
            await asyncio.sleep(0.1)

    def last(self, conv: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = conv["messages"][-1]
        return result


FAQ = [
    (
        "How do I reset my password?",
        "Open the sign-in page, click Forgot password and enter your email. The reset link works for 30 minutes.",
    ),
    (
        "How long does shipping take?",
        "Standard shipping takes 3 to 5 business days. Express shipping takes 1 to 2 business days.",
    ),
    (
        "What is your return policy?",
        "Unused products can be returned within 30 days for a full refund.",
    ),
    (
        "How do I change my plan?",
        "Open Settings, Billing and pick a new plan. Upgrades apply immediately.",
    ),
    (
        "Which payment methods do you accept?",
        "We accept Visa, Mastercard, American Express and PayPal.",
    ),
]


@pytest.fixture(scope="session")
async def stack(
    database: str, mock_ai: str, site: str, tmp_path_factory: pytest.TempPathFactory
) -> AsyncIterator[Stack]:
    from supportdesk.main import create_app

    tmp = tmp_path_factory.mktemp("stack")
    settings = make_settings(database, tmp)
    served = Served(create_app(settings)).start()
    worker = WorkerThread(settings).start()
    try:
        yield Stack(served.url, settings, mock_ai, site, worker)
    finally:
        worker.stop()
        served.stop()


@pytest.fixture
async def mock(stack: Stack) -> AsyncIterator[httpx.AsyncClient]:
    """The mock AI's admin interface, reset before and after each test."""
    async with httpx.AsyncClient(base_url=stack.mock_ai_url, timeout=10) as client:
        await client.post("/admin/reset")
        yield client
        await client.post("/admin/reset")


async def eventually(check: Any, wait_s: float = 20, every: float = 0.2) -> Any:
    """Poll ``check`` (an async callable) until it returns something truthy."""
    deadline = time.monotonic() + wait_s
    last: Any = None
    while time.monotonic() < deadline:
        last = await check()
        if last:
            return last
        await asyncio.sleep(every)
    raise AssertionError(f"condition never held; last value: {last!r}")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
