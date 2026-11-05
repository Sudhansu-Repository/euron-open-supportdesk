"""The migrations and the models describe the same schema, and the migrations run both
ways. A model change without a migration fails here, not in production."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from supportdesk.core.db import Base, import_all_models
from supportdesk.migrations.runner import alembic_config, upgrade

pytestmark = pytest.mark.asyncio


def _diff(conn: Connection) -> list[Any]:
    from supportdesk.migrations.env_filters import include_object

    context = MigrationContext.configure(
        conn, opts={"compare_type": True, "include_object": include_object}
    )
    return list(compare_metadata(context, Base.metadata))


async def test_the_migrations_match_the_models(database: str) -> None:
    import_all_models()
    engine = create_async_engine(database)
    async with engine.connect() as conn:
        diff = await conn.run_sync(_diff)
    await engine.dispose()
    assert diff == [], f"models and migrations differ; generate a migration: {diff}"


async def test_the_migrations_downgrade_and_upgrade_again(database: str) -> None:
    cfg = alembic_config(database)
    await asyncio.to_thread(command.downgrade, cfg, "base")
    await asyncio.to_thread(upgrade, database)
    await test_the_migrations_match_the_models(database)
