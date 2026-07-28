# QuantAgent optimization roadmap

## Current state

QuantAgent is an A-share research and paper-trading prototype combining four
agents, four strategy families, a backtester, genetic optimization, monitoring,
notifications and a FastAPI dashboard.

Known baseline issues:

- `skills/intraday.py` has an `IndentationError`.
- The test suite has no behavior tests.
- GA runs have produced `NaN` or zero fitness.
- Paper trading accepted invalid/stale data and repeated buys.
- Review formatting fails when metrics are `None`.
- The dashboard can collide on port 5001.
- Core strategies depend on `/mnt/d/AI/auction-stock-picker`.
- Runtime records contain inconsistent text encodings.

## Milestone 0 — Reproducible baseline

Goal: one command creates a clean environment and produces an evidence-backed
health report.

- Fix syntax/import errors without changing trading behavior.
- Pin or lock dependencies and document Python/WSL support.
- Add Ruff, pytest and pre-commit configuration.
- Add CI for compile, lint and unit tests.
- Replace hard-coded external paths with validated configuration.
- Add deterministic offline fixtures so tests never require live market APIs.

Exit gate: a clean checkout passes compile, lint and tests without secrets or
network access.

## Milestone 1 — Data and paper-trading safety

Goal: impossible market data cannot become an order.

- Introduce typed market-data validation with freshness and source metadata.
- Reject missing names, non-positive/implausible prices and stale quotes.
- Filter suspended, ST, delisting and non-tradable securities before selection.
- Enforce A-share lot size, T+1, price limits and position/cash constraints.
- Add idempotency keys for daily signals and simulated orders.
- Make order and position updates atomic in SQLite.
- Add a global kill switch and explicit `paper` execution mode.

Exit gate: adversarial fixtures cannot create invalid or duplicate paper orders.

## Milestone 2 — Trustworthy backtesting

Goal: strategy claims are reproducible and free from common leakage.

- Define a point-in-time data contract and trading calendar.
- Model commissions, stamp duty, slippage, limit-up/down and unfilled orders.
- Prevent look-ahead bias, survivorship bias and same-bar execution leakage.
- Add walk-forward and out-of-sample evaluation.
- Produce versioned reports with sample count, CAGR, Sharpe, drawdown, turnover
  and confidence intervals.
- Remove the unverified `86.6%` claim until reproduced.

Exit gate: a fixed dataset and configuration produce a deterministic report.

## Milestone 3 — Repair GA and LLM boundaries

Goal: optimization cannot silently promote invalid results.

- Sanitize every metric with explicit finite-value checks.
- Fail experiments on `NaN` instead of completing them.
- Separate train, validation and untouched test periods.
- Add minimum-trade and overfitting penalties.
- Version genomes, datasets, code revision and random seeds.
- Require schema validation for LLM JSON and deterministic fallback behavior.
- Keep promotion manual and paper-only.

Exit gate: seeded GA tests improve a synthetic objective and reject invalid runs.

## Milestone 4 — Architecture and observability

Goal: modules are independently testable and failures are diagnosable.

- Define provider interfaces for market data, LLM, notification and execution.
- Remove imports from the sibling `auction-stock-picker` repository.
- Replace broad exception swallowing with typed failures and retry policies.
- Add structured logs, correlation IDs, task metrics and health probes.
- Add schema migrations and a retention policy for logs/caches.
- Separate scheduler jobs from business logic.

Exit gate: each external provider can be replaced by an offline fake.

## Milestone 5 — Operations and dashboard

Goal: safe, low-maintenance paper operation.

- Harden Docker and service startup; detect occupied ports.
- Add scheduler locking and missed-job policies.
- Add dashboard authentication before non-local deployment.
- Show data freshness, failed jobs, risk state and strategy provenance.
- Add backup/restore checks and incident runbooks.

Exit gate: a paper-trading soak test completes at least 20 trading days without
duplicate orders, silent job failures or unreconciled positions.

## Release gate

Live trading is out of scope until a separate security, regulatory, broker,
reconciliation and capital-risk review is explicitly authorized.

## Standard verification

During a milestone, run focused tests first. Before committing:

```bash
python -m compileall -q .
ruff check .
pytest -q
```

Record meaningful architecture decisions in `docs/adr/` and update this roadmap
after each completed milestone. This is the durable project checkpoint used to
avoid rediscovery and reduce future context/token usage.
