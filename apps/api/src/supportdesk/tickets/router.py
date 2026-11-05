"""Conversations: the shared inbox for agents and the REST API for integrations.

List, read, create and reply accept an agent session or an API key (read or write);
approvals, drafts, macros and SLA policies are for signed-in agents.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select

from supportdesk.ai import assist
from supportdesk.auth.dependencies import Admin, Agent, ApiRead, ApiWrite
from supportdesk.channels.service import inbox_for_channel
from supportdesk.core.deps import ContainerDep, SessionDep
from supportdesk.core.errors import AppError, NotFoundError
from supportdesk.core.events import commit
from supportdesk.core.schemas import Page
from supportdesk.customers.service import find_or_create
from supportdesk.tickets import queries, service
from supportdesk.tickets.models import Attachment, Macro, Message, SlaPolicy, Ticket
from supportdesk.tickets.schemas import (
    ApproveIn,
    BulkPatch,
    BulkResult,
    DraftIn,
    DraftOut,
    MacroIn,
    MacroOut,
    MessageOut,
    ReplyIn,
    SlaPolicyIn,
    SlaPolicyOut,
    TicketCreate,
    TicketDetail,
    TicketOut,
    TicketPatch,
    View,
    ViewCounts,
)

router = APIRouter(prefix="/api/v1", tags=["conversations"])


@router.get("/tickets", response_model=Page[TicketOut], summary="List conversations")
async def list_tickets(
    actor: ApiRead,
    session: SessionDep,
    view: View = "all",
    status: str | None = None,
    priority: str | None = None,
    channel: str | None = None,
    category: str | None = None,
    assignee_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    tag: str | None = None,
    q: Annotated[str | None, Query(max_length=200, description="Full-text search, or #123")] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> Page[TicketOut]:
    items, next_cursor = await queries.list_tickets(
        session,
        actor.scope,
        view=view,
        user_id=actor.id,
        status=status,
        priority=priority,
        channel=channel,
        category=category,
        assignee_id=assignee_id,
        customer_id=customer_id,
        tag=tag,
        q=q,
        cursor=cursor,
        limit=limit,
    )
    return Page[TicketOut](items=items, next_cursor=next_cursor)


@router.get("/tickets/counts", response_model=ViewCounts, summary="Conversations per inbox view")
async def counts(actor: Agent, session: SessionDep) -> ViewCounts:
    return await queries.view_counts(session, actor.scope, actor.id)


@router.post(
    "/tickets", response_model=TicketDetail, status_code=201, summary="Open a conversation"
)
async def create_ticket(
    body: TicketCreate, actor: ApiWrite, session: SessionDep, container: ContainerDep
) -> TicketDetail:
    if not (body.customer_email or body.customer_external_id):
        raise AppError("Give the customer's email or external id", code="customer_required")
    inbox = await inbox_for_channel(session, actor.org_id, "api")
    customer = await find_or_create(
        session,
        actor.org_id,
        email=body.customer_email,
        name=body.customer_name,
        external_id=body.customer_external_id,
    )
    ticket, _ = await service.open_ticket(
        session,
        inbox,
        customer,
        body.body,
        subject=body.subject,
        priority=body.priority,
        author=actor,
        ai=body.ai,
    )
    if body.tags:
        ticket.tags = sorted({t.strip().lower()[:40] for t in body.tags if t.strip()})
    await commit(container, session)
    return await queries.detail(session, ticket)


@router.get(
    "/tickets/{ticket_id}", response_model=TicketDetail, summary="A conversation with its messages"
)
async def get_ticket(ticket_id: uuid.UUID, actor: ApiRead, session: SessionDep) -> TicketDetail:
    ticket = await service.get_ticket(session, actor.scope, ticket_id)
    return await queries.detail(session, ticket)


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=MessageOut,
    status_code=201,
    summary="Reply to the customer, or add an internal note",
)
async def reply(
    ticket_id: uuid.UUID,
    body: ReplyIn,
    actor: ApiWrite,
    session: SessionDep,
    container: ContainerDep,
) -> Message:
    ticket = await service.get_ticket(session, actor.scope, ticket_id, lock=True)
    text = body.body
    if body.macro_id is not None:
        macro = await session.get(Macro, body.macro_id)
        if macro is None or macro.org_id != actor.org_id:
            raise NotFoundError("Canned reply not found")
        macro.uses += 1
    message = await service.agent_reply(
        session, actor, ticket, text, note=body.note, status=body.status
    )
    await commit(container, session)
    return message


@router.patch(
    "/tickets/{ticket_id}",
    response_model=TicketDetail,
    summary="Change status, priority, assignee...",
)
async def update_ticket(
    ticket_id: uuid.UUID,
    body: TicketPatch,
    actor: ApiWrite,
    session: SessionDep,
    container: ContainerDep,
) -> TicketDetail:
    ticket = await service.get_ticket(session, actor.scope, ticket_id, lock=True)
    fields = body.model_fields_set
    await service.update_ticket(
        session,
        actor,
        ticket,
        status=body.status,
        priority=body.priority,
        category=body.category if "category" in fields else False,
        tags=body.tags,
        subject=body.subject,
        assignee_id=None
        if body.unassign
        else (body.assignee_id if "assignee_id" in fields else False),
        team_id=None if body.clear_team else (body.team_id if "team_id" in fields else False),
    )
    await commit(container, session)
    return await queries.detail(session, ticket)


@router.post(
    "/tickets/bulk", response_model=BulkResult, summary="Update many conversations at once"
)
async def bulk(
    body: BulkPatch, actor: Agent, session: SessionDep, container: ContainerDep
) -> BulkResult:
    rows = (
        await session.scalars(
            select(Ticket)
            .where(Ticket.org_id == actor.org_id, Ticket.id.in_(body.ids))
            .with_for_update()
        )
    ).all()
    for ticket in rows:
        tags = (
            sorted({*ticket.tags, *(t.lower() for t in body.add_tags)}) if body.add_tags else None
        )
        await service.update_ticket(
            session,
            actor,
            ticket,
            status=body.status,
            priority=body.priority,
            tags=tags,
            assignee_id=None
            if body.unassign
            else (body.assignee_id if body.assignee_id else False),
        )
    await commit(container, session)
    return BulkResult(updated=len(rows))


@router.post(
    "/messages/{message_id}/approve",
    response_model=MessageOut,
    summary="Send an AI answer held for approval",
)
async def approve(
    message_id: uuid.UUID,
    body: ApproveIn,
    actor: Agent,
    session: SessionDep,
    container: ContainerDep,
) -> Message:
    message = await session.get(Message, message_id)
    if message is None or message.org_id != actor.org_id:
        raise NotFoundError("Message not found")
    sent = await service.approve(session, actor, message, body.body)
    await commit(container, session)
    return sent


@router.post(
    "/messages/{message_id}/reject",
    response_model=MessageOut,
    summary="Discard an AI answer or draft",
)
async def reject(
    message_id: uuid.UUID, actor: Agent, session: SessionDep, container: ContainerDep
) -> Message:
    message = await session.get(Message, message_id)
    if message is None or message.org_id != actor.org_id:
        raise NotFoundError("Message not found")
    await service.reject(session, actor, message)
    await commit(container, session)
    return message


@router.post("/tickets/{ticket_id}/draft", response_model=DraftOut, summary="Draft a reply with AI")
async def draft(
    ticket_id: uuid.UUID, body: DraftIn, actor: Agent, session: SessionDep, container: ContainerDep
) -> DraftOut:
    ticket = await service.get_ticket(session, actor.scope, ticket_id)
    return DraftOut.model_validate(
        await assist.draft(container, actor.org_id, ticket, body.tone, body.instructions)
    )


@router.get("/attachments/{attachment_id}", summary="Download an attachment")
async def download(
    attachment_id: uuid.UUID, actor: ApiRead, session: SessionDep, container: ContainerDep
) -> Response:
    att = await session.get(Attachment, attachment_id)
    if att is None or att.org_id != actor.org_id:
        raise NotFoundError("Attachment not found")
    data = await container.storage.get(att.storage_key)
    safe = att.filename.replace('"', "")
    return Response(
        data,
        media_type="application/octet-stream",
        headers={
            "content-disposition": f'attachment; filename="{safe}"',
            "cache-control": "private, no-store",
        },
    )


@router.get("/macros", response_model=list[MacroOut], summary="Canned replies")
async def list_macros(actor: Agent, session: SessionDep) -> list[Macro]:
    return list(
        (
            await session.scalars(
                select(Macro).where(Macro.org_id == actor.org_id).order_by(Macro.title)
            )
        ).all()
    )


@router.post("/macros", response_model=MacroOut, status_code=201, summary="Add a canned reply")
async def create_macro(body: MacroIn, actor: Admin, session: SessionDep) -> Macro:
    macro = Macro(org_id=actor.org_id, **body.model_dump())
    session.add(macro)
    await session.commit()
    return macro


@router.put("/macros/{macro_id}", response_model=MacroOut, summary="Edit a canned reply")
async def update_macro(
    macro_id: uuid.UUID, body: MacroIn, actor: Admin, session: SessionDep
) -> Macro:
    macro = await session.get(Macro, macro_id)
    if macro is None or macro.org_id != actor.org_id:
        raise NotFoundError("Canned reply not found")
    for k, v in body.model_dump().items():
        setattr(macro, k, v)
    await session.commit()
    return macro


@router.delete("/macros/{macro_id}", status_code=204, summary="Delete a canned reply")
async def delete_macro(macro_id: uuid.UUID, actor: Admin, session: SessionDep) -> Response:
    macro = await session.get(Macro, macro_id)
    if macro is None or macro.org_id != actor.org_id:
        raise NotFoundError("Canned reply not found")
    await session.delete(macro)
    await session.commit()
    return Response(status_code=204)


@router.get("/sla-policies", response_model=list[SlaPolicyOut], summary="Service level targets")
async def list_sla(actor: Agent, session: SessionDep) -> list[SlaPolicy]:
    order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    rows = list(
        (await session.scalars(select(SlaPolicy).where(SlaPolicy.org_id == actor.org_id))).all()
    )
    return sorted(rows, key=lambda r: order.get(r.priority, 9))


@router.put(
    "/sla-policies", response_model=list[SlaPolicyOut], summary="Replace the service level targets"
)
async def put_sla(body: list[SlaPolicyIn], actor: Admin, session: SessionDep) -> list[SlaPolicy]:
    existing = {
        p.priority: p
        for p in (
            await session.scalars(select(SlaPolicy).where(SlaPolicy.org_id == actor.org_id))
        ).all()
    }
    for item in body:
        row = existing.get(item.priority)
        if row is None:
            row = SlaPolicy(org_id=actor.org_id, **item.model_dump())
            session.add(row)
            existing[item.priority] = row
        else:
            for k, v in item.model_dump().items():
                setattr(row, k, v)
    from supportdesk.audit.service import audit

    audit(session, actor, "sla.updated", "org", actor.org_id)
    await session.commit()
    return await list_sla(actor, session)
