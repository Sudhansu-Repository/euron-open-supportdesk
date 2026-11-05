"""A deterministic stand-in for LLM providers, for the demo and the tests (no key, no network).

It speaks three wire formats (OpenAI ``/v1/chat/completions``, Anthropic ``/v1/messages``,
Ollama ``/api/chat``) plus embeddings (``/v1/embeddings``, ``/api/embed``), and answers
like a careful support model would: it reads the numbered sources in the system prompt,
picks the one that shares the most words with the customer's question, and replies with
its first sentences and a ``[n]`` citation, or ``NO_ANSWER`` when nothing matches. In JSON
mode it returns a triage object.

``POST /admin/mode`` switches behaviour for fault-injection tests:
``normal``, ``fail`` (503), ``slow`` (sleeps ``delay_s``), ``garbage`` (an answer with no
grounding), ``uncited`` (a grounded answer without markers), ``obedient`` (follows
instructions found in the sources, to test that policy, not the model, decides).
``GET /stats`` counts requests per endpoint; the zero-API-key test reads it to prove no
request was made.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="SupportDesk mock AI", docs_url=None, redoc_url=None, openapi_url=None)
STATE: dict[str, Any] = {"mode": "normal", "delay_s": 0.0, "requests": {}, "last": None}
STOP = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "to",
    "of",
    "and",
    "or",
    "in",
    "on",
    "for",
    "with",
    "how",
    "do",
    "does",
    "did",
    "i",
    "my",
    "me",
    "you",
    "your",
    "we",
    "our",
    "can",
    "could",
    "would",
    "should",
    "what",
    "when",
    "where",
    "why",
    "which",
    "who",
    "it",
    "this",
    "that",
    "there",
    "please",
    "hi",
    "hello",
    "thanks",
}
_SOURCE = re.compile(r"\[(\d+)\] \(([^)]*)\)\n<<<\n(.*?)\n>>>", re.S)


def _words(text: str) -> set[str]:
    return {
        w.rstrip("s")
        for w in re.findall(r"[a-z0-9]+", text.lower())
        if w not in STOP and len(w) > 1
    }


def _count(endpoint: str) -> None:
    STATE["requests"][endpoint] = STATE["requests"].get(endpoint, 0) + 1


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stats")
async def stats() -> dict[str, Any]:
    return {
        "requests": sum(STATE["requests"].values()),
        "by_endpoint": STATE["requests"],
        "last": STATE["last"],
        "mode": STATE["mode"],
    }


@app.post("/admin/reset")
async def reset() -> dict[str, str]:
    STATE.update(mode="normal", delay_s=0.0, requests={}, last=None)
    return {"status": "reset"}


@app.post("/admin/mode")
async def mode(request: Request) -> dict[str, Any]:
    body = await request.json()
    STATE["mode"] = str(body.get("mode", "normal"))
    STATE["delay_s"] = float(body.get("delay_s", 0.0))
    return {"mode": STATE["mode"], "delay_s": STATE["delay_s"]}


def _triage(text: str) -> dict[str, Any]:
    lowered = text.lower()
    sensitive = [
        i
        for i, words in {
            "refund": ["refund", "money back"],
            "cancellation": ["cancel"],
            "legal": ["lawyer", "sue"],
            "security": ["hacked", "breach"],
            "data_deletion": ["delete my data", "gdpr"],
        }.items()
        if any(w in lowered for w in words)
    ]
    category = next(
        (
            c
            for c, words in {
                "billing": ["invoice", "charge", "payment", "price", "plan", "refund"],
                "shipping": ["ship", "delivery", "order", "track", "parcel"],
                "account": ["password", "login", "account", "email", "sign in"],
                "technical": ["error", "bug", "api", "crash", "integration", "webhook"],
            }.items()
            if any(w in lowered for w in words)
        ),
        "general",
    )
    negative = any(
        w in lowered for w in ("angry", "terrible", "worst", "ridiculous", "furious", "useless")
    )
    return {
        "category": category,
        "priority": "high" if negative or sensitive else "normal",
        "sentiment": "negative" if negative else "neutral",
        "sensitive_intents": sensitive,
        "wants_human": "human" in lowered or "real person" in lowered,
        "language": "en",
    }


def _answer(system: str, question: str) -> str:
    sources = _SOURCE.findall(system)
    if STATE["mode"] == "garbage":
        return "Our premium plan includes unlimited moon landings and a free pony."
    if STATE["mode"] == "obedient":
        for _n, _title, body in sources:
            match = re.search(r"(?i)ignore (?:all|your|previous)[^.]*\.\s*(.+)", body)
            if match:
                return match.group(1).strip()
    if "Write a short help center article" in system:
        lines = [
            line
            for line in question.splitlines()
            if line.strip() and not line.startswith(("Questions", "Agent", "- "))
        ]
        return "How to fix this\n\n" + (" ".join(lines)[:600] or "NO_ANSWER")
    if "Summarize this support conversation" in system:
        return "The customer needs help and a person should follow up."
    asked = _words(question)
    best, best_score = None, 0.0
    for number, title, body in sources:
        overlap = len(asked & _words(f"{title} {body}")) / (len(asked) or 1)
        if overlap > best_score:
            best, best_score = (number, body), overlap
    if best is None or best_score < 0.34:
        return (
            "NO_ANSWER" if "NO_ANSWER" in system else "I am not sure; an agent should confirm this."
        )
    number, body = best
    text = body.split("\nA: ", 1)[1] if "\nA: " in body else body
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    reply = " ".join(sentences[:2]).strip()
    return reply if STATE["mode"] == "uncited" else f"{reply} [{number}]"


async def _complete(
    messages: list[dict[str, Any]], json_mode: bool, endpoint: str
) -> tuple[str, int, int]:
    _count(endpoint)
    STATE["last"] = {"endpoint": endpoint, "messages": messages}
    if STATE["mode"] == "slow":
        await asyncio.sleep(STATE["delay_s"])
    system = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
    user = next(
        (str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"), ""
    )
    text = json.dumps(_triage(user)) if json_mode else _answer(system, user)
    prompt_tokens = sum(len(str(m.get("content", ""))) for m in messages) // 4 + 1
    return text, prompt_tokens, len(text) // 4 + 1


def _failure() -> JSONResponse | None:
    if STATE["mode"] == "fail":
        return JSONResponse({"error": {"message": "mock provider failure"}}, status_code=503)
    return None


@app.post("/v1/chat/completions", response_model=None)
async def openai_chat(request: Request) -> dict[str, Any] | JSONResponse:
    if (failed := _failure()) is not None:
        _count("openai")
        return failed
    body = await request.json()
    json_mode = (body.get("response_format") or {}).get("type") == "json_object"
    text, pt, ct = await _complete(body.get("messages") or [], json_mode, "openai")
    return {
        "id": f"mock-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "mock"),
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
    }


@app.post("/v1/messages", response_model=None)
async def anthropic_messages(request: Request) -> dict[str, Any] | JSONResponse:
    if (failed := _failure()) is not None:
        _count("anthropic")
        return failed
    body = await request.json()
    messages = [
        {"role": "system", "content": body.get("system", "")},
        *(body.get("messages") or []),
    ]
    json_mode = "Respond with one JSON object" in str(body.get("system", ""))
    text, pt, ct = await _complete(messages, json_mode, "anthropic")
    return {
        "id": "msg_mock",
        "type": "message",
        "role": "assistant",
        "model": body.get("model", "mock"),
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": pt, "output_tokens": ct},
    }


@app.post("/api/chat", response_model=None)
async def ollama_chat(request: Request) -> dict[str, Any] | JSONResponse:
    if (failed := _failure()) is not None:
        _count("ollama")
        return failed
    body = await request.json()
    text, pt, ct = await _complete(
        body.get("messages") or [], body.get("format") == "json", "ollama"
    )
    return {
        "model": body.get("model", "mock"),
        "message": {"role": "assistant", "content": text},
        "done": True,
        "prompt_eval_count": pt,
        "eval_count": ct,
    }


def _embed(text: str, dims: int) -> list[float]:
    vec = [0.0] * dims
    for word in _words(text):
        digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
        vec[int.from_bytes(digest[:4], "big") % dims] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@app.post("/v1/embeddings")
async def openai_embeddings(request: Request) -> dict[str, Any]:
    _count("openai_embed")
    body = await request.json()
    inputs = body.get("input") or []
    inputs = [inputs] if isinstance(inputs, str) else inputs
    dims = int(body.get("dimensions") or 768)
    return {
        "object": "list",
        "model": body.get("model", "mock"),
        "data": [
            {"object": "embedding", "index": i, "embedding": _embed(t, dims)}
            for i, t in enumerate(inputs)
        ],
        "usage": {
            "prompt_tokens": sum(len(t) // 4 for t in inputs),
            "total_tokens": sum(len(t) // 4 for t in inputs),
        },
    }


@app.post("/api/embed")
async def ollama_embed(request: Request) -> dict[str, Any]:
    _count("ollama_embed")
    body = await request.json()
    inputs = body.get("input") or []
    inputs = [inputs] if isinstance(inputs, str) else inputs
    return {"model": body.get("model", "mock"), "embeddings": [_embed(t, 768) for t in inputs]}
