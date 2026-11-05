"""Organisations: creation with safe defaults, settings, teams.

Settings documents are validated by their Pydantic models on every read and write, so a
document written by an older version gains new fields with their defaults instead of
failing. The AI provider key is sealed before it is stored and is never returned.
"""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.audit.service import Actor, audit
from supportdesk.core.container import Container
from supportdesk.core.db import OrgScope
from supportdesk.core.errors import AppError, NotFoundError
from supportdesk.core.net import host_of, is_private_host
from supportdesk.org.models import Org, OrgSettings, Team, TeamMember
from supportdesk.org.schemas import (
    DEFAULT_CATEGORIES,
    AiConfig,
    Brand,
    Budgets,
    OrgOut,
    Policy,
    SettingsOut,
    SettingsPatch,
    TeamIn,
    TeamOut,
    TokenSaver,
)
from supportdesk.users.models import User

KEY_CONTEXT = "org:{org_id}:ai_api_key"
DEFAULT_SLA = {  # priority: (first response, resolution) in minutes
    "urgent": (30, 4 * 60),
    "high": (2 * 60, 24 * 60),
    "normal": (8 * 60, 3 * 24 * 60),
    "low": (24 * 60, 7 * 24 * 60),
}


@dataclass(frozen=True)
class SettingsBundle:
    org: Org
    row: OrgSettings
    brand: Brand
    ai: AiConfig
    policy: Policy
    budgets: Budgets
    token_saver: TokenSaver
    categories: list[str]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return slug or "support"


async def unique_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name)
    slug = base
    while await session.scalar(select(Org.id).where(Org.slug == slug)) is not None:
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


async def create_org(session: AsyncSession, name: str) -> Org:
    """An organisation with default settings, SLA policies and the four inboxes (website
    widget, email, portal and API) so a new team can start without configuring anything."""
    from supportdesk.channels.service import create_default_inboxes
    from supportdesk.tickets.models import SlaPolicy

    org = Org(name=name, slug=await unique_slug(session, name))
    session.add(org)
    await session.flush()
    session.add(
        OrgSettings(
            org_id=org.id,
            brand=Brand(company_name=name).model_dump(mode="json"),
            ai=AiConfig().model_dump(mode="json"),
            policy=Policy().model_dump(mode="json"),
            budgets=Budgets().model_dump(mode="json"),
            token_saver=TokenSaver().model_dump(mode="json"),
            categories=list(DEFAULT_CATEGORIES),
        )
    )
    for priority, (first, resolution) in DEFAULT_SLA.items():
        session.add(
            SlaPolicy(
                org_id=org.id,
                priority=priority,
                first_response_minutes=first,
                resolution_minutes=resolution,
            )
        )
    await session.flush()
    await create_default_inboxes(session, org.id)
    return org


async def load_settings(session: AsyncSession, org_id: uuid.UUID) -> SettingsBundle:
    org = await session.get(Org, org_id)
    row = await session.get(OrgSettings, org_id)
    if org is None or row is None:
        raise NotFoundError("Organisation not found", code="org_not_found")
    return SettingsBundle(
        org=org,
        row=row,
        brand=Brand.model_validate(row.brand or {}),
        ai=AiConfig.model_validate(row.ai or {}),
        policy=Policy.model_validate(row.policy or {}),
        budgets=Budgets.model_validate(row.budgets or {}),
        token_saver=TokenSaver.model_validate(row.token_saver or {}),
        categories=list(row.categories or DEFAULT_CATEGORIES),
    )


async def unseal_api_key(container: Container, bundle: SettingsBundle) -> str | None:
    sealed = bundle.row.ai_api_key_sealed
    if not sealed:
        return None
    return await container.sealer.open(sealed, KEY_CONTEXT.format(org_id=bundle.org.id))


def to_out(bundle: SettingsBundle) -> SettingsOut:
    return SettingsOut(
        org=OrgOut.model_validate(bundle.org),
        brand=bundle.brand,
        ai=bundle.ai,
        ai_key_set=bundle.row.ai_api_key_sealed is not None,
        policy=bundle.policy,
        budgets=bundle.budgets,
        token_saver=bundle.token_saver,
        categories=bundle.categories,
    )


def check_endpoint(container: Container, url: str | None) -> None:
    """Refuse a private AI endpoint unless private endpoints are allowed (local models)."""
    if url and not container.settings.ai_allow_private_endpoints and is_private_host(host_of(url)):
        raise AppError(
            "The AI endpoint is a private address, which this deployment does not allow. "
            "Use a public provider URL, or set AI_ALLOW_PRIVATE_ENDPOINTS=true",
            code="ai_endpoint_private",
        )


async def update_settings(
    container: Container, session: AsyncSession, actor: Actor, patch: SettingsPatch
) -> SettingsBundle:
    bundle = await load_settings(session, actor.org_id)
    row, changed = bundle.row, []
    if patch.name is not None and patch.name != bundle.org.name:
        bundle.org.name = patch.name
        changed.append("name")
    if patch.ai is not None:
        check_endpoint(container, patch.ai.base_url)
        check_endpoint(container, patch.ai.embed_base_url)
        embedder_changed = (patch.ai.embedder, patch.ai.embed_model, patch.ai.embed_dims) != (
            bundle.ai.embedder,
            bundle.ai.embed_model,
            bundle.ai.embed_dims,
        )
        row.ai = patch.ai.model_dump(mode="json")
        changed.append("ai")
        if embedder_changed:
            # New vectors are incompatible with the old ones: re-embed every chunk.
            from supportdesk.knowledge.service import schedule_reindex_all

            await schedule_reindex_all(session, actor.org_id)
            changed.append("embedder")
    if patch.ai_api_key is not None:
        row.ai_api_key_sealed = (
            await container.sealer.seal(patch.ai_api_key, KEY_CONTEXT.format(org_id=actor.org_id))
            if patch.ai_api_key
            else None
        )
        changed.append("ai_api_key")
    for name in ("brand", "policy", "budgets", "token_saver"):
        value = getattr(patch, name)
        if value is not None:
            setattr(row, name, value.model_dump(mode="json"))
            changed.append(name)
    if patch.categories is not None:
        row.categories = patch.categories
        changed.append("categories")
    if {"ai", "policy"} & set(changed):
        # Cached answers were made under the old model or policy: retire them.
        await bump_kb_version(session, actor.org_id)
    if changed:
        audit(session, actor, "settings.updated", "org", actor.org_id, fields=changed)
        await session.commit()
    return await load_settings(session, actor.org_id)


async def bump_kb_version(session: AsyncSession, org_id: uuid.UUID) -> int:
    """Every knowledge change bumps the version: answer caches keyed on it go stale."""
    version = await session.scalar(
        update(Org)
        .where(Org.id == org_id)
        .values(kb_version=Org.kb_version + 1)
        .returning(Org.kb_version)
    )
    return int(version or 0)


async def list_teams(session: AsyncSession, scope: OrgScope) -> list[TeamOut]:
    teams = list(
        (
            await session.scalars(
                select(Team).where(Team.org_id == scope.org_id).order_by(Team.name)
            )
        ).all()
    )
    members = await session.execute(
        select(TeamMember.team_id, TeamMember.user_id).where(
            TeamMember.team_id.in_([t.id for t in teams])
        )
    )
    by_team: dict[uuid.UUID, list[uuid.UUID]] = {}
    for team_id, user_id in members.tuples():
        by_team.setdefault(team_id, []).append(user_id)
    return [TeamOut(id=t.id, name=t.name, member_ids=by_team.get(t.id, [])) for t in teams]


async def _check_members(session: AsyncSession, scope: OrgScope, ids: list[uuid.UUID]) -> None:
    if not ids:
        return
    found = await session.scalars(
        select(User.id).where(User.org_id == scope.org_id, User.id.in_(ids))
    )
    if len(set(found.all())) != len(set(ids)):
        raise AppError(
            "Every team member must be an agent of this organisation", code="unknown_member"
        )


async def save_team(
    session: AsyncSession, actor: Actor, data: TeamIn, team_id: uuid.UUID | None = None
) -> TeamOut:
    await _check_members(session, actor.scope, data.member_ids)
    if team_id is None:
        team = Team(org_id=actor.org_id, name=data.name)
        session.add(team)
        await session.flush()
    else:
        found = await session.get(Team, team_id)
        if found is None or found.org_id != actor.org_id:
            raise NotFoundError("Team not found")
        team = found
        team.name = data.name
        await session.execute(delete(TeamMember).where(TeamMember.team_id == team.id))
    for user_id in dict.fromkeys(data.member_ids):
        session.add(TeamMember(team_id=team.id, user_id=user_id))
    audit(session, actor, "team.saved", "team", team.id, members=len(data.member_ids))
    await session.commit()
    return TeamOut(id=team.id, name=team.name, member_ids=list(dict.fromkeys(data.member_ids)))


async def delete_team(session: AsyncSession, actor: Actor, team_id: uuid.UUID) -> None:
    team = await session.get(Team, team_id)
    if team is None or team.org_id != actor.org_id:
        raise NotFoundError("Team not found")
    await session.delete(team)
    audit(session, actor, "team.deleted", "team", team_id)
    await session.commit()
