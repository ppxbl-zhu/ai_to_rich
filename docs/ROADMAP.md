# QuantAgent roadmap

## Current checkpoint

- Active branch: `main`
- Active milestone: Milestone 3 complete; Milestones 4 and 5 authorized
- Product mode: research, advice, and paper trading only
- Live broker orders: prohibited
- Durable requirements: `docs/PRODUCT_REQUIREMENTS.md`

## Milestone 0 — Engineering baseline

Goal: a clean checkout can create a reproducible environment and pass an
offline quality gate without secrets or network access.

- [x] Remove the abandoned QuantLab implementation.
- [x] Establish the `src/quantagent` package.
- [x] Pin Python and direct dependencies.
- [x] Add Ruff, pytest, pre-commit, and Windows/Linux verification commands.
- [x] Add Windows and Linux CI.
- [x] Add fail-closed paper-mode configuration and secret redaction.
- [x] Add deterministic offline market-data fixtures and a health report.
- [x] Add PostgreSQL development service and Alembic migration structure.
- [x] Add architecture decision records and domain glossary.
- [x] Run the complete quality gate after replacing the legacy environment.
- [x] Commit and push the verified baseline.

Exit gate: bootstrap followed by verification passes compile, lint, formatting,
tests, and offline health checks without credentials or live APIs.

## Milestone 1 — Trading domain and risk core

- [x] Quote, Bar, Signal, TradePlan, OrderIntent, ValidatedOrder, Fill, Position,
  and Portfolio models.
- [x] 100,000 CNY deterministic paper account.
- [x] A-share T+1, board lot, price limit, suspension, ST, delisting, cash,
  position, duplicate-order, and kill-switch controls.
- [x] Versioned transaction-cost engine using the confirmed Eastmoney fee
  schedule.
- [x] Append-only order, fill, and portfolio-snapshot migration baseline.
- [x] Run the complete quality gate and publish the checkpoint.

## Milestone 2 — Data system

- [x] Point-in-time daily, minute, index, sector, financial, announcement, and
  news contracts and fixtures.
- [x] Tushare capability probe and offline provider fake.
- [x] Read-only Eastmoney desktop collector feasibility probe.
- [x] Freshness, provenance, reconciliation, and dataset versioning.
- [x] Dataset, record, and provider-probe migration baseline.
- [x] Run the complete quality gate and publish the checkpoint.

## Milestone 3 — Trustworthy backtesting

- [x] Future-bar execution with costs, slippage, T+1, suspensions, price
  limits, and explicit unfilled-order outcomes.
- [x] Chronological train, validation, and untouched test windows.
- [x] Point-in-time inputs and reports that record dataset version,
  configuration version, and random seed.
- [x] Equity, return, drawdown, turnover, fill, and order-outcome reporting.
- [x] Run the complete quality gate and publish the checkpoint.

## Milestone 4 — Swing-trend strategy

- Trend, relative strength, financial quality, market regime, position sizing,
  and deterministic exits.

## Milestone 5 — Closing-auction short-horizon strategy

- Closing scan, next-day exit state machine, independent risk budget, and
  calibrated T2 extension gate.

## Milestone 6 — LLM research layer

- Structured evidence extraction, hypothesis generation, explanation, and
  review. LLM output remains outside deterministic execution controls.

## Milestone 7 — Genetic evolution

- Bounded genome, multi-objective fitness, experiment lineage, overfitting
  controls, and manual promotion.

## Milestone 8 — Paper operations

- Dashboard, alerts, scheduling, reconciliation, incident handling, and at
  least 20 trading days of simulation.

## Release gate

Live trading requires a separate broker, regulatory, security, reconciliation,
capital-risk, and human-control review explicitly authorized by the user.
