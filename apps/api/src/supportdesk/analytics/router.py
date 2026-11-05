"""Analytics: volume, speed, AI resolution, satisfaction, the team, and model costs."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import Response

from supportdesk.analytics import service
from supportdesk.analytics.schemas import Costs, Overview, TeamMember
from supportdesk.auth.dependencies import Admin, Agent
from supportdesk.core.deps import SessionDep

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])
Days = Annotated[int, Query(ge=1, le=365)]


@router.get(
    "/overview",
    response_model=Overview,
    summary="Volume, response times, AI resolution, CSAT and cost",
)
async def overview(actor: Agent, session: SessionDep, days: Days = 30) -> dict[str, Any]:
    return await service.overview(session, actor.org_id, days)


@router.get("/team", response_model=list[TeamMember], summary="Workload and replies per agent")
async def team(actor: Agent, session: SessionDep, days: Days = 30) -> list[dict[str, Any]]:
    return await service.team(session, actor.org_id, days)


@router.get(
    "/costs",
    response_model=Costs,
    summary="The token ledger by purpose and model, and budget usage",
)
async def costs(actor: Agent, session: SessionDep, days: Days = 30) -> dict[str, Any]:
    return await service.ledger(session, actor.org_id, days)


@router.get("/export.csv", summary="Daily rollups as CSV")
async def export(actor: Admin, session: SessionDep, days: Days = 90) -> Response:
    body = await service.export_csv(session, actor.org_id, days)
    return Response(
        body,
        media_type="text/csv",
        headers={"content-disposition": 'attachment; filename="supportdesk-daily.csv"'},
    )
