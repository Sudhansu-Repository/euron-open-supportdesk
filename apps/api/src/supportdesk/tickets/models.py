"""Conversations (one conversation is one ticket), their messages and history."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from supportdesk.core.db import Base, OrgScoped, TimestampMixin, new_id

STATUSES = ("open", "pending", "resolved", "closed")
PRIORITIES = ("low", "normal", "high", "urgent")
SENTIMENTS = ("negative", "neutral", "positive")
# Who holds the conversation: the AI agent, or people.
HANDLERS = ("ai", "human")


class Ticket(OrgScoped, TimestampMixin, Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("org_id", "number", name="uq_tickets_org_number"),
        # The inbox list: newest activity first within a status, per organisation.
        Index("ix_tickets_inbox", "org_id", "status", "last_message_at"),
        Index("ix_tickets_assignee", "org_id", "assignee_id", "status"),
        Index("ix_tickets_customer", "customer_id", "created_at"),
        Index("ix_tickets_sla", "org_id", "status", "sla_next_due_at"),
        Index("ix_tickets_tags", "tags", postgresql_using="gin"),
        Index("ix_tickets_search", "search", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    inbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inboxes.id", ondelete="RESTRICT"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    category: Mapped[str | None] = mapped_column(String(64))
    sentiment: Mapped[str | None] = mapped_column(String(16))
    intent: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str | None] = mapped_column(String(16))
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL")
    )
    handled_by: Mapped[str] = mapped_column(String(8), nullable=False, default="ai")
    # Resolved by the AI with no human reply (counted in the AI resolution rate).
    ai_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Why the AI handed the conversation over: reason codes from the escalation engine.
    escalation_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The AI's handoff summary for the agent who picks the conversation up.
    summary: Mapped[str | None] = mapped_column(Text)
    pending_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The earliest unmet SLA target, for sorting by urgency.
    sla_next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The first reply by a person after a person took the conversation (the SLA's target).
    human_replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the AI answered and the customer has not replied: auto-resolved after a while.
    ai_answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_customer_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    csat_score: Mapped[int | None] = mapped_column(SmallInteger)
    csat_comment: Mapped[str | None] = mapped_column(Text)
    # Email threading: replies go to <local>+<reply_token>@<domain>.
    reply_token: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    ai_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    ai_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    search: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', coalesce(subject, ''))", persisted=True)
    )


class Message(OrgScoped, Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_ticket", "ticket_id", "created_at"),
        # One AI turn per customer message, whatever the number of job attempts.
        Index(
            "uq_messages_ai_reply",
            "reply_to_id",
            unique=True,
            postgresql_where=text("author_type = 'ai' AND reply_to_id IS NOT NULL"),
        ),
        # A provider retrying an inbound email cannot store it twice.
        Index(
            "ix_messages_email_id",
            "org_id",
            "email_message_id",
            unique=True,
            postgresql_where=text("email_message_id IS NOT NULL"),
        ),
        Index(
            "ix_messages_pending", "org_id", "status", postgresql_where=text("status = 'pending'")
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    # customer, agent, ai, system
    author_type: Mapped[str] = mapped_column(String(16), nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # reply (the customer sees it), note (internal), draft (AI suggestion for an agent)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="reply")
    # sent, draft, pending (waiting for approval), discarded, rejected
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="sent")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    # For an AI turn: the customer message it answers.
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL")
    )
    # helpful / unhelpful, from the customer, on AI answers.
    feedback: Mapped[str | None] = mapped_column(String(16))
    email_message_id: Mapped[str | None] = mapped_column(String(300))
    # How the reply left: {"email": "sent"|"failed", ...}
    delivery: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # The AI decision behind an AI turn (reason codes, scores, cache, cost) for the panel.
    ai_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', coalesce(body, ''))", persisted=True)
    )


Index("ix_messages_search", Message.search, postgresql_using="gin")


class Attachment(OrgScoped, Base):
    __tablename__ = "attachments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketEvent(OrgScoped, Base):
    """The conversation's history: status, assignment, priority, escalation, AI decisions."""

    __tablename__ = "ticket_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(48), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Macro(OrgScoped, TimestampMixin, Base):
    """A canned reply, optionally with actions (status, priority, tags)."""

    __tablename__ = "macros"
    __table_args__ = (UniqueConstraint("org_id", "title", name="uq_macros_org_title"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    actions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SlaPolicy(OrgScoped, TimestampMixin, Base):
    __tablename__ = "sla_policies"
    __table_args__ = (UniqueConstraint("org_id", "priority", name="uq_sla_org_priority"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    first_response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
