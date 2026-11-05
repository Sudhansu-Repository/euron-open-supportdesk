"""Pure ASGI middleware (no BaseHTTPMiddleware: it buffers streams and adds latency)."""

from __future__ import annotations

import json
import logging
import re
import secrets
import time

import orjson
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from supportdesk.core.config import Settings
from supportdesk.core.logs import request_id_var
from supportdesk.core.security import decode_session

log = logging.getLogger("supportdesk.http")

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]
_QUIET = {"/healthz", "/readyz", "/metrics"}


class RequestContextMiddleware:
    """Assigns a request id, adds security headers, logs one line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode()[:64]
        rid = incoming if incoming.replace("-", "").replace("_", "").isalnum() else ""
        rid = rid or secrets.token_hex(8)
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", rid.encode()))
                headers.extend(SECURITY_HEADERS)
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if path not in _QUIET:
                log.info(
                    "request",
                    extra={
                        "method": scope.get("method"),
                        "path": path,
                        "status": status,
                        "ms": round((time.perf_counter() - started) * 1000, 1),
                    },
                )
            request_id_var.reset(token)


_BODY_METHODS = {"POST", "PUT", "PATCH"}


# Knowledge uploads take large bodies, but only from a signed-in admin (checked from the
# token before any byte is read; the route authorizes fully).
_UPLOAD_PATH = re.compile(r"^/api/v1/knowledge/sources/upload/?$")
# Inbound email is streamed: the route checks the inbound token, then reads the body, so an
# anonymous client cannot make the API buffer megabytes before authentication.
_STREAMED_PATH = re.compile(r"^/api/v1/channels/email/inbound/[^/]+/?$")


def _bearer(headers: dict[bytes, bytes]) -> str:
    value = headers.get(b"authorization", b"").decode("latin-1")
    return value[7:].strip() if value.lower().startswith("bearer ") else ""


def _is_admin_session(headers: dict[bytes, bytes], secret: str) -> bool:
    """A genuine (signed, unexpired) admin or owner session token, checked without the
    database: this only decides whether a large body may be read at all, so forged or
    agent tokens stay at the small limit."""
    token = _bearer(headers)
    if not token:
        for part in headers.get(b"cookie", b"").decode("latin-1").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "sd_session":
                token = value
    claims = decode_session(token, secret) if token else None
    return claims is not None and claims.role in ("admin", "owner")


class PayloadTooLargeError(Exception):
    """Raised while a streamed body is read past its limit (mapped to 413)."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"The request body is larger than {limit:,} bytes")
        self.limit = limit


class BodySizeLimitMiddleware:
    """Refuses request bodies over the limit with 413, whatever their framing, and JSON
    bodies that are not valid UTF-8 text with 422.

    ``Content-Length`` is checked up front; chunked bodies are counted as they arrive and
    refused the moment they pass the limit, before any route parses them. JSON may escape
    a lone UTF-16 surrogate ("\\ud800"), which the standard parser accepts but Postgres
    cannot store; orjson refuses it, so such a body never reaches a route. Streamed paths
    are counted, not buffered.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        headers = dict(scope.get("headers") or [])
        limit = self.settings.max_body_bytes
        if _UPLOAD_PATH.match(path) and _is_admin_session(headers, self.settings.session_secret):
            limit = self.settings.max_upload_bytes + 64_000  # multipart framing
        streamed = bool(_STREAMED_PATH.match(path))
        if streamed:
            limit = self.settings.max_upload_bytes
        length = headers.get(b"content-length", b"")
        if length.isdigit() and int(length) > limit:
            await self._refuse(send, limit)
            return
        if streamed:
            await self.app(scope, self._counting(receive, limit), send)
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > limit:
                await self._refuse(send, limit)
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break
        whole = b"".join(chunks)
        if b"json" in headers.get(b"content-type", b"") and size:
            try:
                orjson.loads(whole)
            except orjson.JSONDecodeError as exc:
                await self._respond(
                    send,
                    422,
                    {
                        "code": "invalid_json",
                        "type": "invalid_request_error",
                        "message": (
                            "The request body is not valid JSON text "
                            "(UTF-8, no unpaired surrogates)"
                        ),
                        "details": {"reason": str(exc)[:200]},
                    },
                )
                return
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": whole, "more_body": False}
            return await receive()  # after the body: wait for a disconnect

        await self.app(scope, replay, send)

    @staticmethod
    def _counting(receive: Receive, limit: int) -> Receive:
        size = 0

        async def wrapped() -> Message:
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > limit:
                raise PayloadTooLargeError(limit)
            return message

        return wrapped

    async def _refuse(self, send: Send, limit: int) -> None:
        await self._respond(
            send,
            413,
            {
                "code": "payload_too_large",
                "type": "invalid_request_error",
                "message": f"The request body is larger than {limit:,} bytes",
                "details": {"limit_bytes": limit},
            },
        )

    async def _respond(self, send: Send, status: int, error: dict[str, object]) -> None:
        body = json.dumps({"error": error}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
