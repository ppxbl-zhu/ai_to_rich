# ADR 0003: External providers are replaceable and fail closed

- Status: Accepted
- Date: 2026-07-29

## Context

Tushare permissions, public intraday sources, LLM vendors, notifications, and
the Eastmoney desktop collector can fail or change independently.

## Decision

Each external capability will be introduced behind a typed provider interface
with an offline fake. Provider data carries source, market time, capture time,
and quality state. Missing, stale, malformed, or conflicting data cannot produce
new advice or order intents.

## Consequences

Milestone 0 ships only a deterministic fixture and health contract. Concrete
providers are deferred to their planned milestones.
