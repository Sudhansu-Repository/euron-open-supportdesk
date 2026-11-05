"""Hard token and cost budgets, enforced before a model call is made.

A call reserves its worst case (estimated input plus the maximum output) in the daily and
the monthly row with one conditional UPDATE each. Postgres locks the row, re-checks the
condition against the latest committed values, and applies it only if the limit still
holds, so fifty concurrent calls can never jointly overspend. After the call the
reservation is settled to what the provider reported. Usage is tracked even without
limits, for the cost views.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.core.tasks import periodic
from supportdesk.org.schemas import Budgets

if TYPE_CHECKING:
    from supportdesk.core.container import Container


def periods(now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now(UTC)
    return f"d:{now:%Y-%m-%d}", f"m:{now:%Y-%m}"


@dataclass(frozen=True)
class Reservation:
    org_id: uuid.UUID
    periods: tuple[str, ...]
    tokens: int
    cost: Decimal


_RESERVE = text(
    """
    UPDATE budget_usage
       SET reserved_tokens = reserved_tokens + :t,
           reserved_cost_usd = reserved_cost_usd + :c,
           reserved_at = now()
     WHERE org_id = :org AND period = :period
       AND (:lt = 0 OR tokens + reserved_tokens + :t <= :lt)
       AND (:lc = 0 OR cost_usd + reserved_cost_usd + :c <= :lc)
    RETURNING id
    """
)
_ENSURE = text(
    "INSERT INTO budget_usage (org_id, period, tokens, cost_usd, reserved_tokens, reserved_cost_usd, blocked) "
    "VALUES (:org, :period, 0, 0, 0, 0, 0) ON CONFLICT (org_id, period) DO NOTHING"
)


async def reserve(
    session: AsyncSession,
    org_id: uuid.UUID,
    budgets: Budgets,
    tokens: int,
    cost: Decimal,
    now: datetime | None = None,
) -> Reservation | None:
    """Reserve in both periods, or neither. None means a budget would be exceeded.

    Commits its own short transaction: a reservation must be visible to other callers at
    once, and must not be held open across the model call.
    """
    day, month = periods(now)
    limits = {
        day: (budgets.daily_tokens, budgets.daily_cost_usd),
        month: (budgets.monthly_tokens, budgets.monthly_cost_usd),
    }
    for period in limits:
        await session.execute(_ENSURE, {"org": org_id, "period": period})
    await session.commit()
    for period, (lt, lc) in limits.items():
        row = await session.execute(
            _RESERVE, {"t": tokens, "c": cost, "org": org_id, "period": period, "lt": lt, "lc": lc}
        )
        if row.scalar_one_or_none() is None:
            await session.rollback()
            await session.execute(
                text(
                    "UPDATE budget_usage SET blocked = blocked + 1 WHERE org_id = :org AND period = :p"
                ),
                {"org": org_id, "p": day},
            )
            await session.commit()
            return None
    await session.commit()
    return Reservation(org_id, tuple(limits), tokens, cost)


async def settle(
    session: AsyncSession, reservation: Reservation, tokens: int, cost: Decimal
) -> None:
    """Release the reservation and record what the call really used."""
    for period in reservation.periods:
        await session.execute(
            text(
                """
                UPDATE budget_usage
                   SET reserved_tokens = GREATEST(reserved_tokens - :rt, 0),
                       reserved_cost_usd = GREATEST(reserved_cost_usd - :rc, 0),
                       tokens = tokens + :t,
                       cost_usd = cost_usd + :c
                 WHERE org_id = :org AND period = :period
                """
            ),
            {
                "rt": reservation.tokens,
                "rc": reservation.cost,
                "t": tokens,
                "c": cost,
                "org": reservation.org_id,
                "period": period,
            },
        )
    await session.commit()


async def exhausted(session: AsyncSession, org_id: uuid.UUID, budgets: Budgets) -> bool:
    """Whether a budget is already spent (a cheap pre-check; reserve() is authoritative)."""
    if not (
        budgets.daily_tokens
        or budgets.monthly_tokens
        or budgets.daily_cost_usd
        or budgets.monthly_cost_usd
    ):
        return False
    day, month = periods()
    rows = await session.execute(
        text(
            "SELECT period, tokens + reserved_tokens AS t, cost_usd + reserved_cost_usd AS c "
            "FROM budget_usage WHERE org_id = :org AND period IN (:d, :m)"
        ),
        {"org": org_id, "d": day, "m": month},
    )
    for period, used_tokens, used_cost in rows.tuples():
        lt, lc = (
            (budgets.daily_tokens, budgets.daily_cost_usd)
            if period == day
            else (budgets.monthly_tokens, budgets.monthly_cost_usd)
        )
        if (lt and used_tokens >= lt) or (lc and used_cost >= lc):
            return True
    return False


@periodic("budget.release_stale", every_s=300)
async def release_stale(container: Container) -> int:
    """Release reservations a crashed call never settled.

    A reservation lives for one model call (bounded by AI_TIMEOUT_S). When the newest
    reservation on a row is far older than any call could run, nothing in flight still
    holds part of it, so the whole reserved amount is released.
    """
    stale_after = int(container.settings.ai_timeout_s * 3) + 60
    async with container.db.sessionmaker() as session:
        result = await session.execute(
            text(
                "UPDATE budget_usage SET reserved_tokens = 0, reserved_cost_usd = 0 "
                "WHERE (reserved_tokens > 0 OR reserved_cost_usd > 0) "
                "AND reserved_at < now() - make_interval(secs => :s)"
            ),
            {"s": stale_after},
        )
        await session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
