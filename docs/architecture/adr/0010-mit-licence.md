# ADR-0010: MIT licence

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

Comparable open-source helpdesks are AGPL (Zammad, FreeScout, Frappe Helpdesk) or MIT
with enterprise editions (Chatwoot). Every project in the Euron open-source programme is
MIT licensed, so companies and individuals can adopt and adapt it with the fewest
conditions.

## Decision

MIT. `LICENSE` reads `Copyright (c) 2026 ENGAGESPHERE TECHNOLOGY PRIVATE LIMITED and the
Euron Open SupportDesk contributors`. There is no enterprise edition; every feature in
the repository is MIT.

## Consequences

**Good**
- Companies can run, modify and embed it, including in commercial products.

**Bad / caveats**
- Modifications made by hosted operators need not be shared back.

## Alternatives considered

- **AGPLv3**: forces network operators to share changes, but deters many companies from
  adopting a tool that sits next to their customer data.
- **Apache 2.0**: similar permissions with an explicit patent grant; MIT keeps the
  programme consistent.
