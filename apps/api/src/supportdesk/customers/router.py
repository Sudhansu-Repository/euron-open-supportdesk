"""Customers: who wrote in, their history, and merging duplicates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import func, or_, select

from supportdesk.auth.dependencies import Agent, ApiRead, ApiWrite
from supportdesk.core.deps import SessionDep
from supportdesk.core.schemas import ApiModel, Email
from supportdesk.customers import service
from supportdesk.customers.models import Customer
from supportdesk.tickets import queries
from supportdesk.tickets.models import Ticket
from supportdesk.tickets.schemas import TicketOut

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


class CustomerOut(ApiModel):
    id: uuid.UUID
    name: str
    email: str | None
    external_id: str | None
    vip: bool
    attributes: dict[str, Any]
    last_seen_at: datetime | None
    created_at: datetime
    ticket_count: int = 0
    open_count: int = 0


class CustomerDetail(CustomerOut):
    tickets: list[TicketOut]
    csat_avg: float | None


class CustomerPatch(ApiModel):
    name: str | None = Field(None, max_length=200)
    email: Email | None = None
    vip: bool | None = None
    attributes: dict[str, Any] | None = None


class MergeIn(ApiModel):
    keep_id: uuid.UUID
    drop_id: uuid.UUID


async def _counts(session: SessionDep, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    rows = await session.execute(
        select(
            Ticket.customer_id,
            func.count(),
            func.count().filter(Ticket.status.in_(("open", "pending"))),
        )
        .where(Ticket.customer_id.in_(ids))
        .group_by(Ticket.customer_id)
    )
    return {cid: (int(total), int(open_)) for cid, total, open_ in rows.tuples()}


@router.get("", response_model=list[CustomerOut], summary="Search customers")
async def list_customers(
    actor: ApiRead,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    vip: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CustomerOut]:
    stmt = select(Customer).where(
        Customer.org_id == actor.org_id, Customer.merged_into_id.is_(None)
    )
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Customer.name).like(like),
                func.lower(Customer.email).like(like),
                Customer.external_id == q.strip(),
            )
        )
    if vip is not None:
        stmt = stmt.where(Customer.vip.is_(vip))
    rows = list(
        (
            await session.scalars(
                stmt.order_by(Customer.last_seen_at.desc().nulls_last()).limit(limit)
            )
        ).all()
    )
    counts = await _counts(session, [c.id for c in rows])
    return [
        CustomerOut.model_validate(
            {
                **CustomerOut.model_validate(c).model_dump(),
                "ticket_count": counts.get(c.id, (0, 0))[0],
                "open_count": counts.get(c.id, (0, 0))[1],
            }
        )
        for c in rows
    ]


@router.get(
    "/{customer_id}", response_model=CustomerDetail, summary="A customer with their conversations"
)
async def get_customer(
    customer_id: uuid.UUID, actor: ApiRead, session: SessionDep
) -> CustomerDetail:
    customer = await service.get_customer(session, actor.scope, customer_id)
    items, _ = await queries.list_tickets(session, actor.scope, customer_id=customer.id, limit=100)
    csat = await session.scalar(
        select(func.avg(Ticket.csat_score)).where(Ticket.customer_id == customer.id)
    )
    total, open_ = (await _counts(session, [customer.id])).get(customer.id, (0, 0))
    return CustomerDetail.model_validate(
        {
            **CustomerOut.model_validate(customer).model_dump(),
            "ticket_count": total,
            "open_count": open_,
            "tickets": items,
            "csat_avg": float(csat) if csat is not None else None,
        }
    )


@router.patch("/{customer_id}", response_model=CustomerOut, summary="Edit a customer")
async def update_customer(
    customer_id: uuid.UUID, body: CustomerPatch, actor: ApiWrite, session: SessionDep
) -> Customer:
    return await service.update_customer(
        session,
        actor,
        customer_id,
        name=body.name,
        email=body.email,
        vip=body.vip,
        attributes=body.attributes,
    )


@router.post(
    "/merge", response_model=CustomerOut, summary="Merge a duplicate into another customer"
)
async def merge(body: MergeIn, actor: Agent, session: SessionDep) -> Customer:
    return await service.merge(session, actor, body.keep_id, body.drop_id)
