"""Task and job registration, and the command line wiring."""

from __future__ import annotations

import pytest

from supportdesk import cli, worker
from supportdesk.core import jobs, tasks


def test_every_handler_and_task_registers() -> None:
    worker.import_handlers()
    assert {"ai.reply", "kb.ingest", "kb.article", "mail.reply", "webhooks.deliver"} <= set(
        jobs.job_types()
    )
    assert jobs.job_types()["ai.reply"].on_dead is not None  # a dead AI turn still hands over
    assert {
        "sla.scan",
        "tickets.auto_resolve",
        "analytics.rollup",
        "gaps.cluster",
        "jobs.prune",
    } <= set(tasks.tasks())


def test_periodic_tasks_have_distinct_lock_ids() -> None:
    worker.import_handlers()
    ids = [t.lock_id for t in tasks.tasks().values()]
    assert len(ids) == len(set(ids))


def test_cli_parses_every_command(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    for name in ("_serve", "_worker", "_migrate", "_seed", "_openapi", "_owner"):
        monkeypatch.setattr(cli, name, lambda args, n=name: seen.append(n))
    for argv in (
        ["serve", "--port", "9"],
        ["worker"],
        ["migrate"],
        ["seed-demo"],
        ["openapi"],
        ["create-owner", "--email", "a@b.c"],
    ):
        cli.main(argv)
    assert seen == ["_serve", "_worker", "_migrate", "_seed", "_openapi", "_owner"]


def test_backoff_grows_and_caps() -> None:
    assert list(jobs.BACKOFF_S) == sorted(jobs.BACKOFF_S)
