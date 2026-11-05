from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from supportdesk.core.schemas import ApiModel, Email

Status = Literal["open", "pending", "resolved", "closed"]
Priority = Literal["low", "normal", "high", "urgent"]
View = Literal["all", "mine", "unassigned", "ai", "approvals", "escalated", "sla", "resolved"]


class CustomerBrief(ApiModel):
    id: uuid.UUID
    name: str
    email: str | None
    vip: bool


class TicketOut(ApiModel):
    id: uuid.UUID
    number: int
    subject: str
    status: str
    priority: str
    category: str | None
    sentiment: str | None
    intent: str | None
    channel: str
    handled_by: str
    ai_resolved: bool
    escalation_reasons: list[str]
    pending_approval: bool
    assignee_id: uuid.UUID | None
    team_id: uuid.UUID | None
    tags: list[str]
    customer: CustomerBrief
    preview: str = ""
    preview_author: str | None = None
    sla_state: str = "none"
    sla_next_due_at: datetime | None
    last_message_at: datetime
    created_at: datetime


class Citation(ApiModel):
    chunk_id: str | None = None
    source_id: str | None = None
    article_id: str | None = None
    title: str
    heading: str | None = None
    url: str | None = None
    relevance: float | None = None


class MessageOut(ApiModel):
    id: uuid.UUID
    author_type: str
    author_id: uuid.UUID | None
    author_name: str | None = None
    kind: str
    status: str
    body: str
    citations: list[Citation]
    feedback: str | None
    delivery: dict[str, Any]
    ai_meta: dict[str, Any]
    created_at: datetime
    sent_at: datetime | None


class EventOut(ApiModel):
    id: int
    type: str
    actor_type: str
    actor_id: uuid.UUID | None
    data: dict[str, Any]
    created_at: datetime


class AttachmentOut(ApiModel):
    id: uuid.UUID
    message_id: uuid.UUID | None
    filename: str
    content_type: str
    size: int


class TicketDetail(TicketOut):
    summary: str | None
    language: str | None
    csat_score: int | None
    csat_comment: str | None
    first_response_at: datetime | None
    human_replied_at: datetime | None
    resolved_at: datetime | None
    escalated_at: datetime | None
    first_response_due_at: datetime | None
    resolution_due_at: datetime | None
    reopened_count: int
    ai_cost_usd: Decimal
    ai_tokens: int
    messages: list[MessageOut]
    events: list[EventOut]
    attachments: list[AttachmentOut]


class TicketCreate(ApiModel):
    """Open a conversation on a customer's behalf (API, or an agent logging a call)."""

    customer_email: Email | None = None
    customer_name: str | None = Field(None, max_length=200)
    customer_external_id: str | None = Field(None, max_length=200)
    subject: str | None = Field(None, max_length=300)
    body: str = Field(min_length=1, max_length=50_000)
    priority: Priority | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    ai: bool = Field(False, description="Let the AI answer first (as if the customer wrote in)")


class ReplyIn(ApiModel):
    body: str = Field(min_length=1, max_length=50_000)
    note: bool = Field(False, description="Internal note: never shown to the customer")
    status: Status | None = Field(None, description="Status after sending (default pending)")
    macro_id: uuid.UUID | None = None


class TicketPatch(ApiModel):
    status: Status | None = None
    priority: Priority | None = None
    category: str | None = Field(None, max_length=64)
    tags: list[str] | None = Field(None, max_length=20)
    assignee_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    subject: str | None = Field(None, max_length=300)
    unassign: bool = False
    clear_team: bool = False


class BulkPatch(ApiModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    status: Status | None = None
    priority: Priority | None = None
    assignee_id: uuid.UUID | None = None
    unassign: bool = False
    add_tags: list[str] = Field(default_factory=list, max_length=10)


class BulkResult(ApiModel):
    updated: int


class ApproveIn(ApiModel):
    body: str | None = Field(None, max_length=50_000, description="Edited text to send instead")


class DraftIn(ApiModel):
    tone: Literal["friendly", "formal", "concise", "empathetic"] = "friendly"
    instructions: str | None = Field(None, max_length=500)


class DraftOut(ApiModel):
    body: str
    citations: list[Citation]
    grounded: bool
    method: str
    tokens: int
    cost_usd: Decimal


class MacroIn(ApiModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=20_000)
    actions: dict[str, Any] = Field(default_factory=dict)


class MacroOut(MacroIn):
    id: uuid.UUID
    uses: int


class SlaPolicyIn(ApiModel):
    priority: Priority
    first_response_minutes: int = Field(ge=1, le=60 * 24 * 30)
    resolution_minutes: int = Field(ge=1, le=60 * 24 * 90)
    enabled: bool = True


class SlaPolicyOut(SlaPolicyIn):
    id: uuid.UUID


class ViewCounts(ApiModel):
    all: int
    mine: int
    unassigned: int
    ai: int
    approvals: int
    escalated: int
    sla: int


# ----- what customers see (widget and portal): an explicit whitelist -----


class PublicCitation(ApiModel):
    title: str
    heading: str | None = None
    url: str | None = None


class PublicMessage(ApiModel):
    """A message as the customer sees it: no AI metadata, delivery status or agent ids."""

    id: uuid.UUID
    author_type: str
    author_name: str | None = None
    body: str
    citations: list[PublicCitation]
    feedback: str | None
    created_at: datetime


class PortalTicket(ApiModel):
    id: uuid.UUID
    number: int
    subject: str
    status: str
    channel: str
    preview: str = ""
    last_message_at: datetime
    created_at: datetime


class PortalTicketDetail(PortalTicket):
    csat_score: int | None
    messages: list[PublicMessage]
