# ADR 0001: Greenfield, paper-only architecture

- Status: Accepted
- Date: 2026-07-29

## Context

The imported QuantLab prototype had syntax failures, no behavior tests,
untrusted order paths, hard-coded external dependencies, and inconsistent
runtime records. The user authorized removing it and rebuilding from the product
requirements.

## Decision

Build a new Python 3.13 package under `src/quantagent`. The system defaults to
paper mode and rejects any other execution mode. Live broker integration is
excluded until a separately approved release gate.

## Consequences

Legacy code and experimental records are not carried forward. Features are
introduced milestone by milestone behind deterministic tests and fail-closed
safety boundaries.
