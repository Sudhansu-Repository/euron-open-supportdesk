from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from supportdesk.core.schemas import ApiModel, Email

Role = Literal["agent", "admin", "owner"]


class InviteIn(ApiModel):
    email: Email
    role: Literal["agent", "admin"] = "agent"


class InvitationOut(ApiModel):
    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class InvitationCreated(InvitationOut):
    invite_url: str = Field(description="Shown once: share it if email is not set up")


class UserPatch(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    role: Role | None = None
    disabled: bool | None = None
    capacity: int | None = Field(None, ge=0, le=500)


class MePatch(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    availability: Literal["online", "away", "offline"] | None = None
