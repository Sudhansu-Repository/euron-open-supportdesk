"""Customers (the people asking for help) and their portal sign-in links."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from supportdesk.core.db import Base, OrgScoped, TimestampMixin, new_id


class Customer(OrgScoped, TimestampMixin, Base):
    __tablename__ = "customers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    email: Mapped[str | None] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # The company's own id for this person (identity-verified widget users, API callers).
    external_id: Mapped[str | None] = mapped_column(String(200))
    vip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when this customer was merged into another; reads follow it.
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL")
    )


Index(
    "uq_customers_org_email",
    Customer.org_id,
    func.lower(Customer.email),
    unique=True,
    postgresql_where=text("email IS NOT NULL AND merged_into_id IS NULL"),
)
Index(
    "uq_customers_org_external",
    Customer.org_id,
    Customer.external_id,
    unique=True,
    postgresql_where=text("external_id IS NOT NULL AND merged_into_id IS NULL"),
)


class PortalToken(OrgScoped, Base):
    """A one-time magic sign-in link for the customer portal (15 minutes)."""

    __tablename__ = "portal_tokens"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    # Set for a known customer; a first-time address gets its customer record only when
    # the link is redeemed, so asking for links cannot fill the customer table.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
