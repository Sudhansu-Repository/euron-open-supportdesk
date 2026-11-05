# ADR-0007: One conversation is one ticket

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

Live chat products model conversations; helpdesks model tickets. SupportDesk does both:
a widget chat that the AI answers may become a case a person works for days, by email.

## Decision

A single `tickets` row represents the conversation from the first customer message to
resolution, whatever the channel. It carries the status (open, pending, resolved,
closed), who handles it (`handled_by`: ai or human), the assignee, SLA fields, AI cost
and the escalation reasons. Messages, notes, drafts and pending approvals all hang off
it. A customer reply to a resolved conversation reopens the same ticket.

## Consequences

**Good**
- One object to assign, resolve, rate and measure; analytics need no joins between chat
  and ticket models.
- The AI's handoff is a field change, not a copy into another system.

**Bad / caveats**
- A customer who raises a new topic in an old thread reopens it instead of starting a new
  ticket (agents can start a new conversation; merging and splitting tickets is not in
  0.1.0).

## Alternatives considered

- **Separate conversations and tickets** (chat converted into a ticket on escalation):
  two lifecycles, duplicated history, and metrics that must be stitched together.
