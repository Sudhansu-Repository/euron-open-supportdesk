"""API keys and webhooks."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select

from supportdesk.auth.dependencies import Admin
from supportdesk.core.deps import ContainerDep, SessionDep
from supportdesk.core.errors import NotFoundError
from supportdesk.core.schemas import Ack, ApiModel
from supportdesk.integrations import service
from supportdesk.integrations.models import EVENTS, ApiKey, Webhook, WebhookDelivery

router = APIRouter(prefix="/api/v1", tags=["integrations"])


class ApiKeyIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    scope: Literal["read", "write"] = "read"


class ApiKeyOut(ApiModel):
    id: uuid.UUID
    name: str
    prefix: str
    scope: str
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="Shown once. Send it as Authorization: Bearer <key>")


class WebhookIn(ApiModel):
    url: str = Field(min_length=8, max_length=2000)
    events: list[str] = Field(min_length=1, max_length=len(EVENTS))


class WebhookPatch(ApiModel):
    url: str | None = Field(None, min_length=8, max_length=2000)
    events: list[str] | None = None
    active: bool | None = None


class WebhookOut(ApiModel):
    id: uuid.UUID
    url: str
    events: list[str]
    active: bool
    consecutive_failures: int
    disabled_reason: str | None
    last_success_at: datetime | None
    created_at: datetime


class WebhookCreated(WebhookOut):
    secret: str = Field(description="Shown once. Verify X-SupportDesk-Signature with it")


class DeliveryOut(ApiModel):
    id: uuid.UUID
    event: str
    status: str
    attempts: int
    response_status: int | None
    response_ms: int | None
    error: str | None
    created_at: datetime
    delivered_at: datetime | None


@router.get("/api-keys", response_model=list[ApiKeyOut], summary="API keys")
async def list_keys(actor: Admin, session: SessionDep) -> list[ApiKey]:
    rows = await session.scalars(
        select(ApiKey).where(ApiKey.org_id == actor.org_id).order_by(ApiKey.created_at.desc())
    )
    return list(rows.all())


@router.post(
    "/api-keys", response_model=ApiKeyCreated, status_code=201, summary="Create an API key"
)
async def create_key(
    body: ApiKeyIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> ApiKeyCreated:
    key, plaintext = await service.create_api_key(container, session, actor, body.name, body.scope)
    return ApiKeyCreated.model_validate(
        {**ApiKeyOut.model_validate(key).model_dump(), "key": plaintext}
    )


@router.delete("/api-keys/{key_id}", status_code=204, summary="Revoke an API key")
async def revoke_key(key_id: uuid.UUID, actor: Admin, session: SessionDep) -> Response:
    await service.revoke_api_key(session, actor, key_id)
    return Response(status_code=204)


@router.get("/webhooks", response_model=list[WebhookOut], summary="Webhooks")
async def list_webhooks(actor: Admin, session: SessionDep) -> list[Webhook]:
    rows = await session.scalars(
        select(Webhook).where(Webhook.org_id == actor.org_id).order_by(Webhook.created_at)
    )
    return list(rows.all())


@router.get(
    "/webhooks/events", response_model=list[str], summary="Events a webhook can subscribe to"
)
async def webhook_events(actor: Admin) -> list[str]:
    return list(EVENTS)


@router.post("/webhooks", response_model=WebhookCreated, status_code=201, summary="Add a webhook")
async def create_webhook(
    body: WebhookIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> WebhookCreated:
    hook, secret = await service.create_webhook(container, session, actor, body.url, body.events)
    return WebhookCreated.model_validate(
        {**WebhookOut.model_validate(hook).model_dump(), "secret": secret}
    )


@router.patch(
    "/webhooks/{webhook_id}", response_model=WebhookOut, summary="Change or re-enable a webhook"
)
async def update_webhook(
    webhook_id: uuid.UUID,
    body: WebhookPatch,
    actor: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> Webhook:
    return await service.update_webhook(
        container, session, actor, webhook_id, url=body.url, events=body.events, active=body.active
    )


@router.delete("/webhooks/{webhook_id}", status_code=204, summary="Delete a webhook")
async def delete_webhook(webhook_id: uuid.UUID, actor: Admin, session: SessionDep) -> Response:
    await service.delete_webhook(session, actor, webhook_id)
    return Response(status_code=204)


@router.post("/webhooks/{webhook_id}/test", response_model=Ack, summary="Send a ping delivery")
async def test_webhook(
    webhook_id: uuid.UUID, actor: Admin, session: SessionDep, container: ContainerDep
) -> Ack:
    await service.test_webhook(container, session, actor, webhook_id)
    return Ack(message="A ping is on its way; its result appears in the delivery log")


@router.get(
    "/webhooks/{webhook_id}/deliveries",
    response_model=list[DeliveryOut],
    summary="Recent deliveries",
)
async def deliveries(
    webhook_id: uuid.UUID, actor: Admin, session: SessionDep
) -> list[WebhookDelivery]:
    hook = await session.get(Webhook, webhook_id)
    if hook is None or hook.org_id != actor.org_id:
        raise NotFoundError("Webhook not found")
    rows = await session.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(50)
    )
    return list(rows.all())
