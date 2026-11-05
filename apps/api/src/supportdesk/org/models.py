"""Organisations, their settings and teams.

Settings that are edited as a unit (AI configuration, policy, budgets, Token Saver) are
JSONB documents validated by the Pydantic models in ``org.schemas`` on every write, so the
database never holds a shape the code cannot read.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from supportdesk.core.db import Base, OrgScoped, TimestampMixin, new_id


class Org(TimestampMixin, Base):
    __tablename__ = "orgs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # The customer-facing address of the help center and portal: /help/<slug>.
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Ticket numbers are per organisation (#1, #2...): taken with UPDATE ... RETURNING.
    ticket_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Bumped on every knowledge change; answer caches keyed on it go stale at once.
    kb_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class OrgSettings(TimestampMixin, Base):
    __tablename__ = "org_settings"
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True
    )
    brand: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ai: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Sealed with the key sealer (local AES-GCM or KMS); never returned by the API.
    ai_api_key_sealed: Mapped[bytes | None] = mapped_column(LargeBinary)
    policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    budgets: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    token_saver: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class Team(OrgScoped, TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_teams_org_name"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Round-robin cursor: the last member a conversation was assigned to.
    last_assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class TeamMember(Base):
    __tablename__ = "team_members"
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
