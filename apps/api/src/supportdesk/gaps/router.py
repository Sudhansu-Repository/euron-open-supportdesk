"""Knowledge gaps: what customers asked that the knowledge base could not answer."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import select

from supportdesk.auth.dependencies import Admin, Agent
from supportdesk.core.deps import ContainerDep, SessionDep
from supportdesk.core.schemas import ApiModel
from supportdesk.gaps import service
from supportdesk.gaps.models import KnowledgeGap

router = APIRouter(prefix="/api/v1/gaps", tags=["knowledge gaps"])


class GapOut(ApiModel):
    id: uuid.UUID
    title: str
    status: str
    question_count: int
    last_seen_at: datetime
    article_id: uuid.UUID | None
    created_at: datetime


class GapQuestionOut(ApiModel):
    id: uuid.UUID
    question: str
    reason: str
    ticket_id: uuid.UUID | None
    created_at: datetime


class GapDetail(GapOut):
    questions: list[GapQuestionOut]
    replies: list[str]


class ArticleDraft(ApiModel):
    title: str
    body: str
    source: Literal["model", "agent_replies", "none"] = Field(
        description="Where the text came from; none means no agent has answered these questions yet"
    )


class GapStatusIn(ApiModel):
    status: Literal["open", "dismissed"]


@router.get("", response_model=list[GapOut], summary="Knowledge gaps, most asked first")
async def list_gaps(actor: Agent, session: SessionDep, status: str = "open") -> list[KnowledgeGap]:
    stmt = select(KnowledgeGap).where(KnowledgeGap.org_id == actor.org_id)
    if status == "open":
        stmt = stmt.where(KnowledgeGap.status.in_(("open", "drafted")))
    elif status != "all":
        stmt = stmt.where(KnowledgeGap.status == status)
    rows = await session.scalars(
        stmt.order_by(KnowledgeGap.question_count.desc(), KnowledgeGap.last_seen_at.desc()).limit(
            200
        )
    )
    return list(rows.all())


@router.get("/{gap_id}", response_model=GapDetail, summary="A gap with example questions")
async def get_gap(gap_id: uuid.UUID, actor: Agent, session: SessionDep) -> GapDetail:
    gap = await service.get_gap(session, actor.scope, gap_id)
    questions = await service.examples(session, gap.id, 20)
    replies = await service.resolving_replies(session, gap.id)
    return GapDetail.model_validate(
        {
            **GapOut.model_validate(gap).model_dump(),
            "questions": [GapQuestionOut.model_validate(q) for q in questions],
            "replies": replies,
        }
    )


@router.post(
    "/{gap_id}/draft", response_model=ArticleDraft, summary="Draft an article that closes this gap"
)
async def draft(
    gap_id: uuid.UUID, actor: Admin, session: SessionDep, container: ContainerDep
) -> ArticleDraft:
    return ArticleDraft.model_validate(
        await service.draft_article(container, session, actor, gap_id)
    )


@router.post("/{gap_id}/status", response_model=GapOut, summary="Dismiss or reopen a gap")
async def set_status(
    gap_id: uuid.UUID, body: GapStatusIn, actor: Admin, session: SessionDep
) -> KnowledgeGap:
    return await service.set_status(session, actor, gap_id, body.status)
