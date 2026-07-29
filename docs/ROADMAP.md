# QuantAgent roadmap

## Current checkpoint

- Active branch: `main`
- Active milestone: Milestones 0-8 engineering complete; accumulating the
  Milestone 8 twenty-trading-day operational evidence gate
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

- [x] Daily and weekly trend, stock and sector relative strength, financial
  quality, and risk-on market-regime entry gates.
- [x] Volatility-risk and capital-cap position sizing in A-share board lots.
- [x] Initial stop, trailing stop, trend break, target, and maximum-holding
  deterministic exits.
- [x] Run the complete quality gate and publish the checkpoint.

## Milestone 5 — Closing-auction short-horizon strategy

- [x] Closing-window strength, liquidity, price-location, freshness, and sector
  confirmation scan.
- [x] Independent strategy and per-position capital budgets.
- [x] T1 stop, target, deadline, and explicit extension state machine.
- [x] T2 extension requires calibrated probability, minimum sample size,
  evidence-backed logic, sector linkage, stock structure, market regime,
  positive net edge, and no hard invalidation.
- [x] T2 stop, target, and mandatory final deadline.
- [x] Run the complete quality gate and publish the checkpoint.

## Milestone 6 — LLM research layer

- [x] Point-in-time evidence identities, source metadata, timestamps, and
  content hashes.
- [x] Structured summaries, cited hypotheses, contradiction tracking,
  falsification conditions, risks, and bounded confidence.
- [x] Fail-closed schema, citation, confidence, and execution-field validation.
- [x] Provider, model, prompt version, raw output, token, cost, validation, and
  failure audit migration.
- [x] LLM research remains structurally outside order and risk controls.
- [x] Run the complete quality gate and publish the checkpoint.

## Milestone 7 — Genetic evolution

- [x] Explicit decimal parameter bounds, steps, validation, and seeded mutation.
- [x] Multi-objective fitness using out-of-sample return, drawdown, Sharpe,
  win rate, payoff, cost, turnover, sensitivity, and cross-period stability.
- [x] Invalid metrics and insufficient samples fail the experiment.
- [x] Immutable parent-child lineage with code, data, universe, split, seed,
  genome, hypothesis, metrics, and failure metadata.
- [x] Evidence thresholds and recorded manual approval before paper promotion.
- [x] Run the complete quality gate and publish the checkpoint.

## Milestone 8 — Paper operations

- [x] Portfolio, strategy allocation, data, scheduler, reconciliation,
  incident, active-version, and experiment-lineage dashboard contract.
- [x] Deterministic critical/warning alerts for stale data, reconciliation,
  drawdown, and scheduler health.
- [x] Trading-day-aware idempotent daily scheduling state.
- [x] Non-destructive cash, position, order, and fill reconciliation.
- [x] Incident lifecycle with a latched critical kill switch.
- [x] Append-only operations, job, reconciliation, incident, and simulation
  persistence migration.
- [x] Twenty-day consecutive qualification tracker and fail-closed review gate.
- [ ] Accumulate 20 real, consecutive, completed and reconciled A-share
  simulation trading days without a critical incident.
- [x] Run the complete engineering quality gate and publish the checkpoint.

## Release gate

Live trading requires a separate broker, regulatory, security, reconciliation,
capital-risk, and human-control review explicitly authorized by the user.
