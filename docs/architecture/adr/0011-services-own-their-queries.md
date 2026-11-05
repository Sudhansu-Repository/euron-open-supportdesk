# ADR-0011: Domain services own their queries (no separate repository modules)

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

The program's layering is routers, then services, then repositories, with tenant scoping
structural rather than per-route discipline. In SupportDesk most queries are written once
and are specific to one use case (the claim query for jobs, the hybrid retrieval query,
the inbox list with its keyset cursor, the budget reservation). A repository module per
domain would mostly forward one call to one query.

## Decision

Each domain package keeps its SQL in its `service.py` (or a focused module such as
`tickets/queries.py`, `knowledge/retrieval.py`, `ai/budget.py`), and routers never query
the database. Tenant scoping stays structural: every tenant-owned table carries `org_id`
through `core.db.OrgScoped`; services take an `Actor` or `OrgScope` and filter by it;
lookups by id go through helpers that refuse rows of another organisation
(`get_ticket`, `get_customer`, `get_source`, `core.db.get_scoped`). The integration suite
signs up a fresh organisation per test and asserts cross-tenant reads and writes return
404.

## Consequences

**Good**
- Queries sit next to the rules that need them; no pass-through layer to keep in sync.
- Hot queries stay hand-tuned (DISTINCT ON previews, partial indexes, SKIP LOCKED).

**Bad / caveats**
- A service can, in principle, write a query that forgets `org_id`; reviews and the
  cross-tenant integration tests are the guard, not the type system.
