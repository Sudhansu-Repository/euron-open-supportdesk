"""``make bench``: real measurements of the hot paths, for the README.

Runs the real API and the real worker in-process against a throwaway database
(``supportdesk_bench`` on the configured Postgres), with the real local embedder
(fastembed bge-small, downloaded once) unless ``--embedder hash``, and the bundled mock
model for the model path (so the numbers measure SupportDesk, not a provider's latency).

Measures: knowledge ingestion throughput; answer latency per step and end to end for the
extractive (zero-key) path, the model path and an exact cache hit; how fast the API accepts
customer messages under concurrency and how fast one worker drains the AI turns; WebSocket
fan-out latency. Machine load is recorded with every run.

    uv run python bench.py [--embedder local|hash] [--json out.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).parent))

from tests.integration.conftest import CSRF, Served, WorkerThread, make_settings  # noqa: E402

DB = os.environ.get(
    "BENCH_DATABASE_URL", "postgresql+asyncpg://supportdesk:supportdesk@localhost:4842/supportdesk_bench"
)
QUESTIONS = [
    "How long does shipping take?", "How do I reset my password?", "What is your return policy?",
    "Can I track my order?", "How long is the warranty?", "What does Lumen Plus include?",
    "How do I change my plan?", "Which payment methods do you accept?", "Where can I download my invoice?",
    "Do the bulbs work without internet?", "How many bulbs can I connect?", "Why is my bulb flickering?",
    "Can I share control with my family?", "How much energy does a bulb use?", "What colours can the bulbs show?",
]


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))], 1)


def summary(values: list[float]) -> dict[str, float]:
    return {"p50": pct(values, 50), "p90": pct(values, 90), "mean": round(statistics.fmean(values), 1), "n": len(values)}


async def fresh_database() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    admin = DB.rsplit("/", 1)[0] + "/postgres"
    name = DB.rsplit("/", 1)[1]
    engine = create_async_engine(admin, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    await engine.dispose()
    from supportdesk.migrations.runner import upgrade

    await asyncio.to_thread(upgrade, DB)


async def wait_reply(client: httpx.AsyncClient, ticket_id: str, wait_s: float = 60) -> dict[str, Any]:
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        conv: dict[str, Any] = (await client.get(f"/api/v1/widget/tickets/{ticket_id}")).json()
        if conv["messages"] and conv["messages"][-1]["author_type"] != "customer":
            return conv
        await asyncio.sleep(0.01)
    raise RuntimeError("no reply")


async def visitor(api: str, key: str) -> httpx.AsyncClient:
    client = httpx.AsyncClient(base_url=api, timeout=60, headers={"origin": "http://localhost:4810"})
    token = (await client.post(f"/api/v1/widget/{key}/session", json={})).json()["token"]
    client.headers["authorization"] = f"Bearer {token}"
    return client


async def ask_many(
    api: str, key: str, questions: list[str], owner: httpx.AsyncClient
) -> tuple[list[float], list[dict[str, Any]]]:
    """Ask each question as a new visitor: end-to-end latency in ms, and the last message
    as agents see it (with the AI metadata the widget never shows customers)."""
    latencies, metas = [], []
    for q in questions:
        v = await visitor(api, key)
        started = time.perf_counter()
        conv = (await v.post("/api/v1/widget/messages", json={"body": q})).json()
        await wait_reply(v, conv["ticket_id"])
        latencies.append((time.perf_counter() - started) * 1000)
        detail = (await owner.get(f"/api/v1/tickets/{conv['ticket_id']}")).json()
        metas.append(detail["messages"][-1])
        await v.aclose()
    return latencies, metas


async def run(embedder: str) -> dict[str, Any]:
    from supportdesk.demo import content
    from supportdesk.demo.seed import _docx, _pdf
    from supportdesk.main import create_app

    await fresh_database()
    tmp = Path(tempfile.mkdtemp(prefix="sd-bench-"))
    settings = make_settings(DB, tmp, embedder=embedder, redis_url=os.environ.get("BENCH_REDIS_URL", "redis://localhost:4879/14"),
                             widget_rpm=100_000, signup_rpm=1000, model_cache_dir=os.environ.get(
                                 "MODEL_CACHE_DIR", str(Path.home() / ".cache" / "supportdesk-models")))
    mock = Served("mockai.app:app").start()
    api = Served(create_app(settings)).start()
    worker = WorkerThread(settings, "bench-worker").start()
    results: dict[str, Any] = {
        "embedder": embedder, "machine": platform.platform(), "cpus": os.cpu_count(),
        "load_before": [round(x, 2) for x in os.getloadavg()],
    }
    owner = httpx.AsyncClient(base_url=api.url, timeout=120, headers=CSRF)
    try:
        signup = (await owner.post("/api/v1/auth/signup", json={"org_name": "Lumen Bench", "name": "B",
                                                                "email": "bench@lumen.test", "password": "Bench-Pass-123"})).json()
        owner.headers["authorization"] = f"Bearer {signup['session_token']}"
        key = next(i["public_key"] for i in (await owner.get("/api/v1/inboxes")).json() if i["channel"] == "widget")

        # Warm the embedding model so the ingest number is not the model download.
        await owner.post("/api/v1/knowledge/test", json={"question": "warm up the model"})

        corpus = [("guide.md", content.GUIDE_MD.encode(), "text/markdown"), ("faq.csv", content.FAQ_CSV.encode(), "text/csv"),
                  ("shipping.html", content.SHIPPING_HTML.encode(), "text/html"),
                  ("warranty.pdf", _pdf(content.WARRANTY_TEXT), "application/pdf"),
                  ("business.docx", _docx(content.BUSINESS_DOC), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")]
        filler = " ".join(f"Topic {i}: the Lumen app setting number {i} changes how scenes behave at night." for i in range(60))
        corpus += [(f"notes-{n}.md", f"# Notes {n}\n\n## Section\n\n{filler}\n".encode(), "text/markdown") for n in range(40)]
        started = time.perf_counter()
        ids = []
        for name, data, ctype in corpus:
            ids.append((await owner.post("/api/v1/knowledge/sources/upload", files={"file": (name, data, ctype)})).json()["id"])
        while True:
            sources = (await owner.get("/api/v1/knowledge/sources")).json()
            if all(s["status"] in ("ready", "failed") for s in sources):
                break
            await asyncio.sleep(0.1)
        elapsed = time.perf_counter() - started
        chunks = sum(s["chunk_count"] for s in sources)
        results["ingest"] = {"sources": len(sources), "chunks": chunks, "seconds": round(elapsed, 2),
                             "chunks_per_s": round(chunks / elapsed, 1)}

        # Zero-key path: extractive answers.
        lat, metas = await ask_many(api.url, key, QUESTIONS, owner)
        results["extractive"] = {"end_to_end_ms": summary(lat),
                                 "answered": sum(1 for m in metas if m["author_type"] == "ai"),
                                 "of": len(metas)}
        play = [(await owner.post("/api/v1/knowledge/test", json={"question": q})).json() for q in QUESTIONS]
        results["steps_ms"] = {
            "embed_query": summary([p["timings_ms"].get("embed", 0) for p in play]),
            "retrieve": summary([p["timings_ms"].get("retrieve", 0) for p in play]),
        }

        # Model path (mock model: measures our overhead, not a provider's).
        await owner.patch("/api/v1/org/settings", json={"ai": {"provider": "openai", "base_url": f"{mock.url}/v1",
                                                               "answer_model": "gpt-4o-mini", "triage_model": "gpt-4o-mini"}})
        lat, metas = await ask_many(api.url, key, [q + " please" for q in QUESTIONS], owner)
        results["model_path"] = {"end_to_end_ms": summary(lat),
                                 "answered": sum(1 for m in metas if m["author_type"] == "ai"), "of": len(metas)}
        lat, metas = await ask_many(api.url, key, [q + " please" for q in QUESTIONS], owner)
        results["cache_hit"] = {"end_to_end_ms": summary(lat),
                                "from_cache": sum(1 for m in metas if (m.get("ai_meta") or {}).get("cache")),
                                "of": len(metas)}

        # Throughput: accept rate under concurrency, then drain rate of one worker.
        await owner.patch("/api/v1/org/settings", json={"ai": {"provider": "extractive"}})
        visitors = [await visitor(api.url, key) for _ in range(50)]
        started = time.perf_counter()
        convs = await asyncio.gather(*(v.post("/api/v1/widget/messages", json={"body": QUESTIONS[i % len(QUESTIONS)]})
                                       for i, v in enumerate(visitors) for _ in range(4)))
        accept_s = time.perf_counter() - started
        ticket_ids = [c.json()["ticket_id"] for c in convs]
        # Each visitor sent four messages (four conversations); its own client reads them.
        await asyncio.gather(*(wait_reply(visitors[i // 4], t, 300) for i, t in enumerate(ticket_ids)))
        drain_s = time.perf_counter() - started
        results["throughput"] = {"messages": len(convs), "accepted_per_s": round(len(convs) / accept_s, 1),
                                 "answered_per_s_one_worker": round(len(convs) / drain_s, 1)}
        for v in visitors:
            await v.aclose()

        # WebSocket fan-out: agent reply to the customer's socket.
        import websockets

        v = await visitor(api.url, key)
        conv = (await v.post("/api/v1/widget/messages", json={"body": "talk to a human please"})).json()
        await wait_reply(v, conv["ticket_id"])
        token = v.headers["authorization"][7:]
        fan: list[float] = []
        async with websockets.connect(api.url.replace("http", "ws") + f"/ws/widget/{conv['ticket_id']}?token={token}",
                                      origin="http://localhost:4810") as ws:  # type: ignore[arg-type]
            await ws.recv()
            for i in range(30):
                started = time.perf_counter()
                await owner.post(f"/api/v1/tickets/{conv['ticket_id']}/messages", json={"body": f"update {i}"})
                while "message.created" not in str(await ws.recv()):
                    pass
                fan.append((time.perf_counter() - started) * 1000)
        results["websocket_fanout_ms"] = summary(fan)
    finally:
        results["load_after"] = [round(x, 2) for x in os.getloadavg()]
        await owner.aclose()
        worker.stop()
        api.stop()
        mock.stop()
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embedder", choices=["local", "hash"], default="local")
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    results = asyncio.run(run(args.embedder))
    text = json.dumps(results, indent=2)
    print(text)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
