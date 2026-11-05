# ADR-0006: Live events are invalidations over Redis pub/sub or Postgres LISTEN/NOTIFY

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

The worker writes AI replies; agents and customers hold WebSockets on any API replica.
Updates must reach them quickly, but the system must stay correct if an event is lost,
and must run without Redis.

## Decision

Events are small invalidations (`{"type": "message.created", "ticket_id": ...}`), never
data. They are published only after the transaction commits, to an organisation topic and
a ticket topic. The transport is Redis pub/sub when `REDIS_URL` is set, otherwise Postgres
`LISTEN/NOTIFY`; each process holds one subscription and fans out to local bounded queues.
Clients refetch over REST when they hear an event, and on reconnect.

## Consequences

**Good**
- A lost event delays an update; it never loses or corrupts data. A lossy transport is
  enough.
- Authorization stays in the REST endpoints; events carry no customer content.
- A thousand open widgets cost one Redis or Postgres connection per process.
- `test_live_events_reach_a_socket_on_another_api_replica` covers cross-replica fan-out.

**Bad / caveats**
- One extra request per update.
- A stalled client's queue drops its oldest events (256 kept); it re-syncs on the next one.

## Alternatives considered

- **Pushing full messages over the socket**: duplicate authorization logic and payloads
  in the event path, and lost events would lose data in the UI.
- **Redis Streams per conversation**: durable but needless, since REST is the source of
  truth.
- **Server-sent events**: workable for agents, but the widget also sends typing events.
