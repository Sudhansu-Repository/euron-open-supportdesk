"""Knowledge gaps: questions the AI could not answer, clustered into topics to write."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from supportdesk.core.db import Base, OrgScoped, TimestampMixin, new_id

GAP_STATUSES = ("open", "drafted", "resolved", "dismissed")
REASONS = ("no_answer", "unhelpful", "low_confidence")


class KnowledgeGap(OrgScoped, TimestampMixin, Base):
    __tablename__ = "knowledge_gaps"
    __table_args__ = (Index("ix_gaps_org_status", "org_id", "status", "question_count"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    centroid: Mapped[Any] = mapped_column(Vector(), nullable=True)
    dims: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_articles.id", ondelete="SET NULL")
    )


class GapQuestion(OrgScoped, Base):
    __tablename__ = "gap_questions"
    __table_args__ = (Index("ix_gap_questions_unclustered", "org_id", "gap_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    gap_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_gaps.id", ondelete="SET NULL"), index=True
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="SET NULL")
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), unique=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(24), nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(), nullable=True)
    dims: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
