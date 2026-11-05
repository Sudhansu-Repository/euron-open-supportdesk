"""WebSockets: live updates for agents and for customers in the widget or portal.

Messages pushed are small invalidations (see ``core.hub``); clients fetch what changed
over REST. Agents authenticate with their session cookie (browsers send it on the
upgrade); widget visitors and portal customers pass their token as ``?token=``, because
browsers cannot set headers on a WebSocket. The Origin is checked like any other request.
Typing indicators travel the other way and are relayed without being stored.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any

import orjson
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from supportdesk.auth.dependencies import SESSION_COOKIE, is_revoked
from supportdesk.channels import portal
from supportdesk.channels.models import Inbox
from supportdesk.channels.service import check_origin, read_visitor
from supportdesk.core.container import Container
from supportdesk.core.errors import AppError
from supportdesk.core.hub import org_topic, ticket_topic
from supportdesk.core.security import decode_session
from supportdesk.observability.metrics import websockets
from supportdesk.tickets.models import Ticket
from supportdesk.users.models import User

router = APIRouter()


async def _refuse(ws: WebSocket, code: int) -> None:
    """Accept, then close with an application code: a close before accept is a bare HTTP
    403 to the browser, which then cannot tell "sign in again" (4401) from a network error."""
    await ws.accept()
    await ws.close(code=code)


PING_S = 25


async def _pump(
    ws: WebSocket,
    container: Container,
    topics: list[str],
    on_client: Any,
    kind: str,
    still_valid: Any = None,
) -> None:
    websockets.labels(kind).inc()
    try:
        async with container.hub.subscribe(*topics) as queue:
            await ws.send_text(orjson.dumps({"type": "ready"}).decode())

            async def outbound() -> None:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=PING_S)
                    except TimeoutError:
                        if still_valid is not None and not await still_valid():
                            await ws.close(code=4401)  # signed out, disabled or revoked meanwhile
                            return
                        event = {"type": "ping"}
                    await ws.send_text(orjson.dumps(event).decode())

            async def inbound() -> None:
                while True:
                    raw = await ws.receive_text()
                    if len(raw) > 2000:
                        continue
                    try:
                        data = orjson.loads(raw)
                    except orjson.JSONDecodeError:
                        continue
                    if isinstance(data, dict):
                        await on_client(data)

            tasks = [asyncio.create_task(outbound()), asyncio.create_task(inbound())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            for task in done:
                with contextlib.suppress(WebSocketDisconnect, Exception):
                    task.result()
    finally:
        websockets.labels(kind).dec()


def _origin_ok(container: Container, ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    return origin is None or origin in container.settings.cors_origins


@router.websocket("/ws/agent")
async def agent_socket(ws: WebSocket) -> None:
    container: Container = ws.app.state.container
    token = ws.cookies.get(SESSION_COOKIE) or ws.query_params.get("token")
    claims = decode_session(token, container.settings.session_secret) if token else None
    if claims is None or not _origin_ok(container, ws):
        await _refuse(ws, 4401)
        return
    async with container.db.sessionmaker() as session:
        user = await session.get(User, claims.user_id)
        revoked = await is_revoked(session, claims)
    if user is None or user.disabled or revoked or user.session_version != claims.session_version:
        await _refuse(ws, 4401)
        return
    await ws.accept()
    org_id = user.org_id
    claims_now = claims

    async def still_valid() -> bool:
        async with container.db.sessionmaker() as session:
            current = await session.get(User, claims_now.user_id)
            revoked_now = await is_revoked(session, claims_now)
        return bool(
            current is not None
            and not current.disabled
            and not revoked_now
            and current.session_version == claims_now.session_version
        )

    own_tickets: set[uuid.UUID] = set()

    async def on_client(data: dict[str, Any]) -> None:
        if data.get("type") == "typing" and data.get("ticket_id"):
            try:
                ticket_id = uuid.UUID(str(data["ticket_id"]))
            except ValueError:
                return
            if ticket_id not in own_tickets:
                # Only this organisation's conversations: never announce an agent to another
                # organisation's customers.
                async with container.db.sessionmaker() as session:
                    org = await session.scalar(select(Ticket.org_id).where(Ticket.id == ticket_id))
                if org != org_id:
                    return
                own_tickets.add(ticket_id)
            await container.hub.publish(
                ticket_topic(ticket_id), {"type": "typing", "who": "agent", "name": user.name}
            )

    with contextlib.suppress(WebSocketDisconnect):
        await _pump(ws, container, [org_topic(org_id)], on_client, "agent", still_valid)


async def _customer_ticket(
    container: Container, ticket_id: uuid.UUID, customer_id: uuid.UUID
) -> Ticket | None:
    async with container.db.sessionmaker() as session:
        ticket = await session.get(Ticket, ticket_id)
    return ticket if ticket is not None and ticket.customer_id == customer_id else None


@router.websocket("/ws/widget/{ticket_id}")
async def widget_socket(ws: WebSocket, ticket_id: uuid.UUID) -> None:
    container: Container = ws.app.state.container
    try:
        org_id, inbox_id, customer_id = read_visitor(container, ws.query_params.get("token"))
        async with container.db.sessionmaker() as session:
            inbox = await session.get(Inbox, inbox_id)
        if inbox is None:
            raise AppError("gone")
        check_origin(inbox, ws.headers.get("origin"), container.settings.public_url)
    except AppError:
        await _refuse(ws, 4401)
        return
    ticket = await _customer_ticket(container, ticket_id, customer_id)
    if ticket is None or ticket.org_id != org_id:
        await _refuse(ws, 4404)
        return
    await ws.accept()

    async def on_client(data: dict[str, Any]) -> None:
        if data.get("type") == "typing":
            await container.hub.publish(
                org_topic(org_id),
                {"type": "typing", "who": "customer", "ticket_id": str(ticket_id)},
            )

    with contextlib.suppress(WebSocketDisconnect):
        await _pump(ws, container, [ticket_topic(ticket_id)], on_client, "widget")


@router.websocket("/ws/portal/{ticket_id}")
async def portal_socket(ws: WebSocket, ticket_id: uuid.UUID) -> None:
    container: Container = ws.app.state.container
    try:
        org_id, customer_id = portal.read_portal(container, ws.query_params.get("token"))
    except AppError:
        await _refuse(ws, 4401)
        return
    ticket = await _customer_ticket(container, ticket_id, customer_id)
    if ticket is None or ticket.org_id != org_id:
        await _refuse(ws, 4404)
        return
    await ws.accept()

    async def on_client(_: dict[str, Any]) -> None:
        return None

    with contextlib.suppress(WebSocketDisconnect):
        await _pump(ws, container, [ticket_topic(ticket_id)], on_client, "portal")
