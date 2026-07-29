# Paper operations runbook

Milestone 8 supplies the deterministic operations contracts and persistence
needed to run the paper account. It does not enable live orders.

## Daily schedule

A production scheduler should persist every planned and completed run and call
the following idempotent jobs on exchange trading days:

1. pre-open data/provider health and previous-day reconciliation;
2. pre-open market-regime and existing-position risk review;
3. intraday freshness, limit, suspension, position, and incident monitoring;
4. 14:45 closing-strategy scan and paper plan generation;
5. post-close fills, portfolio snapshot, performance, and reconciliation;
6. backup, experiment linkage, and simulation-day qualification.

Non-trading-day maintenance jobs, such as backup verification, are scheduled
separately. A job that already succeeded on a date is not silently rerun.

## Dashboard and alerts

The dashboard contract exposes equity, cash, drawdown, per-strategy exposure,
data and scheduler health, reconciliation state, open incidents, active
strategy version, and its source experiment. Stale data, reconciliation
mismatch, or 10% account drawdown raises a critical alert. Scheduler
degradation raises a warning.

Critical incidents latch the kill switch. Resolving the incident does not
automatically clear that latch; an operator must first resolve every critical
incident and then explicitly clear it.

## Reconciliation

Expected and observed paper ledgers are compared across cash, positions, order
identities, and fill identities. A difference is reported and never repaired
by overwriting either ledger. Reconciliation mismatch disables new simulated
execution until investigated.

## Twenty-day evidence gate

Each exchange trading date is append-only and qualifies only when:

- the daily workflow completed;
- the paper ledger reconciled; and
- no critical incident occurred.

The release-review counter is a consecutive streak. Any incomplete,
unreconciled, or critical-incident day resets it to zero. Twenty qualifying
days only make the system eligible for a human review; they do not authorize
live trading.

As of 2026-07-29, the engineering gate is implemented, but real-time evidence
has not yet accumulated for 20 future trading days. Synthetic fixtures and
unit tests are intentionally not counted as operational evidence.
