# ADR 0002: Environment configuration and versioned storage

- Status: Accepted
- Date: 2026-07-29

## Context

Development and tests must run without secrets or external services, while
later paper operation needs durable relational storage.

## Decision

Configuration comes from environment variables and contains no committed
credentials. SQLite is the offline default. PostgreSQL is the durable
development and operational target. Alembic owns schema migrations. Logs must
redact credential-shaped fields recursively.

## Consequences

Unit tests stay offline. PostgreSQL-specific behavior will require explicit
integration tests in later milestones. Database schema changes must use
migrations rather than implicit table creation.

