"""Inboxes: where conversations come from (website widget, email, portal, API)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from supportdesk.core.db import Base, OrgScoped, TimestampMixin, new_id

CHANNELS = ("widget", "email", "portal", "api")


class Inbox(OrgScoped, TimestampMixin, Base):
    __tablename__ = "inboxes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    # Widget: the public key in the script tag. Not a secret: origins and rate limits
    # protect it; identity verification protects who a visitor claims to be.
    public_key: Mapped[str | None] = mapped_column(String(40), unique=True)
    allowed_origins: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    appearance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # HMAC secret the company backend signs customer ids with (sealed).
    identity_secret_sealed: Mapped[bytes | None] = mapped_column(LargeBinary)
    identity_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Email: the support address customers write to, and the inbound webhook secret hash.
    email_address: Mapped[str | None] = mapped_column(String(320))
    inbound_secret_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL")
    )
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
