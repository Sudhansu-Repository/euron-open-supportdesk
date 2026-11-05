"""Routing choice and SLA state."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from supportdesk.tickets import sla
from supportdesk.tickets.models import Ticket
from supportdesk.tickets.routing import choose

A, B, C = (uuid.UUID(int=i) for i in (1, 2, 3))


def test_least_loaded_wins_and_full_agents_are_skipped() -> None:
    assert choose([(A, 3, 10), (B, 1, 10), (C, 0, 0)], None) == B


def test_ties_go_round_robin_after_the_last_assignee() -> None:
    candidates = [(A, 1, 10), (B, 1, 10), (C, 1, 10)]
    assert choose(candidates, None) == A
    assert choose(candidates, A) == B
    assert choose(candidates, C) == A


def test_nobody_available() -> None:
    assert choose([(A, 5, 5)], None) is None and choose([], None) is None


def _ticket(**kw: object) -> Ticket:
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "status": "open",
        "created_at": now - timedelta(hours=1),
        "escalated_at": None,
        "sla_breached": False,
        "human_replied_at": None,
        "resolved_at": None,
        "first_response_due_at": None,
        "resolution_due_at": None,
    }
    values.update(kw)
    return Ticket(**values)


def test_sla_states() -> None:
    now = datetime.now(UTC)
    t = _ticket(first_response_due_at=now + timedelta(hours=3))
    sla.refresh(t)
    assert sla.state(t, now) == "ok"
    t = _ticket(first_response_due_at=now + timedelta(minutes=5))
    sla.refresh(t)
    assert sla.state(t, now) == "at_risk"
    t = _ticket(first_response_due_at=now - timedelta(minutes=1))
    sla.refresh(t)
    assert sla.state(t, now) == "breached"
    assert sla.state(_ticket(), now) == "none"


def test_meeting_the_first_response_target_moves_to_resolution() -> None:
    now = datetime.now(UTC)
    t = _ticket(
        first_response_due_at=now + timedelta(hours=1),
        resolution_due_at=now + timedelta(hours=8),
        human_replied_at=now,
    )
    sla.refresh(t)
    assert t.sla_next_due_at == t.resolution_due_at
    t.status = "resolved"
    sla.refresh(t)
    assert t.sla_next_due_at is None
