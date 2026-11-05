"""Organisation settings: brand, AI providers, policy, budgets, Token Saver, teams, prices."""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select

from supportdesk.ai.models import ModelPrice
from supportdesk.ai.providers.base import ChatMessage, ProviderError
from supportdesk.ai.registry import runtime_for
from supportdesk.audit.service import audit
from supportdesk.auth.dependencies import Admin, Agent
from supportdesk.core.deps import ContainerDep, SessionDep
from supportdesk.core.errors import NotFoundError
from supportdesk.core.schemas import ApiModel
from supportdesk.org import service
from supportdesk.org.schemas import AiTestResult, SettingsOut, SettingsPatch, TeamIn, TeamOut

router = APIRouter(prefix="/api/v1/org", tags=["organisation"])


@router.get("/settings", response_model=SettingsOut, summary="Organisation settings")
async def get_settings(actor: Agent, session: SessionDep) -> SettingsOut:
    return service.to_out(await service.load_settings(session, actor.org_id))


@router.patch("/settings", response_model=SettingsOut, summary="Change organisation settings")
async def update_settings(
    body: SettingsPatch, actor: Admin, session: SessionDep, container: ContainerDep
) -> SettingsOut:
    return service.to_out(await service.update_settings(container, session, actor, body))


@router.post("/ai/test", response_model=AiTestResult, summary="Check the AI provider answers")
async def test_ai(actor: Admin, container: ContainerDep) -> AiTestResult:
    runtime = await runtime_for(container, actor.org_id)
    started = time.perf_counter()
    if runtime.chat is None:
        try:
            await runtime.embedder.embed(["connection test"], kind="query")
        except ProviderError as exc:
            return AiTestResult(
                ok=False,
                provider="extractive",
                model=runtime.embedder.name,
                latency_ms=0,
                message=f"Embeddings failed: {exc}",
            )
        return AiTestResult(
            ok=True,
            provider="extractive",
            model=runtime.embedder.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            message="Zero-API-key mode: answers are quoted from your knowledge. Embeddings work.",
        )
    model = runtime.config.model_for("answer")
    try:
        completion = await runtime.chat.complete(
            [ChatMessage("user", "Reply with the single word: ready")], model=model, max_tokens=5
        )
    except ProviderError as exc:
        return AiTestResult(
            ok=False,
            provider=runtime.provider,
            model=model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            message=str(exc),
        )
    return AiTestResult(
        ok=True,
        provider=runtime.provider,
        model=completion.model or model,
        latency_ms=int((time.perf_counter() - started) * 1000),
        message="The provider answered",
        sample=completion.text.strip()[:80],
    )


@router.get("/teams", response_model=list[TeamOut], summary="Teams")
async def list_teams(actor: Agent, session: SessionDep) -> list[TeamOut]:
    return await service.list_teams(session, actor.scope)


@router.post("/teams", response_model=TeamOut, status_code=201, summary="Create a team")
async def create_team(body: TeamIn, actor: Admin, session: SessionDep) -> TeamOut:
    return await service.save_team(session, actor, body)


@router.put(
    "/teams/{team_id}", response_model=TeamOut, summary="Rename a team or change its members"
)
async def update_team(
    team_id: uuid.UUID, body: TeamIn, actor: Admin, session: SessionDep
) -> TeamOut:
    return await service.save_team(session, actor, body, team_id)


@router.delete("/teams/{team_id}", status_code=204, summary="Delete a team")
async def delete_team(team_id: uuid.UUID, actor: Admin, session: SessionDep) -> Response:
    await service.delete_team(session, actor, team_id)
    return Response(status_code=204)


class PriceIn(ApiModel):
    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=120)
    input_per_mtok: Decimal = Field(ge=0, le=10_000)
    output_per_mtok: Decimal = Field(ge=0, le=10_000)


class PriceOut(PriceIn):
    id: uuid.UUID | None = None
    default: bool = False


@router.get(
    "/prices", response_model=list[PriceOut], summary="Model prices (USD per million tokens)"
)
async def list_prices(actor: Agent, session: SessionDep) -> list[PriceOut]:
    from supportdesk.ai.ledger import DEFAULT_PRICES

    own = list(
        (await session.scalars(select(ModelPrice).where(ModelPrice.org_id == actor.org_id))).all()
    )
    seen = {(p.provider, p.model) for p in own}
    out = [PriceOut.model_validate(p) for p in own]
    out += [
        PriceOut(provider=prov, model=model, input_per_mtok=pin, output_per_mtok=pout, default=True)
        for (prov, model), (pin, pout) in DEFAULT_PRICES.items()
        if (prov, model) not in seen
    ]
    return sorted(out, key=lambda p: (p.provider, p.model))


@router.put("/prices", response_model=PriceOut, summary="Set the price of a model")
async def set_price(body: PriceIn, actor: Admin, session: SessionDep) -> ModelPrice:
    row = await session.scalar(
        select(ModelPrice).where(
            ModelPrice.org_id == actor.org_id,
            ModelPrice.provider == body.provider,
            ModelPrice.model == body.model,
        )
    )
    if row is None:
        row = ModelPrice(org_id=actor.org_id, **body.model_dump())
        session.add(row)
    else:
        row.input_per_mtok, row.output_per_mtok = body.input_per_mtok, body.output_per_mtok
    audit(session, actor, "price.set", "model", f"{body.provider}:{body.model}")
    await session.commit()
    return row


@router.delete("/prices/{price_id}", status_code=204, summary="Remove a custom price")
async def delete_price(price_id: uuid.UUID, actor: Admin, session: SessionDep) -> Response:
    row = await session.get(ModelPrice, price_id)
    if row is None or row.org_id != actor.org_id:
        raise NotFoundError("Price not found")
    await session.delete(row)
    await session.commit()
    return Response(status_code=204)
