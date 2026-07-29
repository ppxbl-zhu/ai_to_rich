# Paper runtime

The Milestone 9 runtime connects session data, both deterministic strategies,
the common risk engine, the fee-aware paper broker, and durable local state.
It remains incapable of submitting live broker orders.

## Safety model

- The runtime starts disabled and requires an explicit operator `start`.
- `stop` persists across processes and requires a reason.
- Only one process can hold the state lock.
- A session ID is processed at most once.
- A repeated blocked session does not create duplicate incidents.
- Non-trading days, date mismatches, stale sessions, and missing quotes fail
  before portfolio mutation.
- Runtime state is stored below `data/paper/`, which Git ignores.

## Offline rehearsal

After bootstrapping the environment:

```powershell
quantagent-paper start --at "2026-07-29T14:50:10+08:00"
quantagent-paper run-once `
  --session tests/fixtures/paper_session.json `
  --at "2026-07-29T14:50:10+08:00"
quantagent-paper status
quantagent-paper stop `
  --at "2026-07-29T15:10:00+08:00" `
  --reason "offline rehearsal complete"
```

The fixture is synthetic and proves wiring only. It never counts toward the
20-real-trading-day gate.

## Real-data readiness

The local Tushare token has passed read-only probes for the exchange calendar,
daily bars, daily indicators, price limits, and suspensions. Tushare does not
provide the separately permissioned realtime minute feed for this account.

Eastmoney `mainfree` exposes only custom `Pane` controls through UI Automation,
so the approved watchlist region is read with Windows Chinese OCR. The user
confirmed that the visible client page is market-only. The collector validates
the window title and layout, captures only the watchlist region in memory, and
does not click, type, or navigate.

Install the locked desktop dependencies and capture a monitor-only session:

```powershell
uv sync --locked --extra dev --extra desktop
quantagent-eastmoney-monitor `
  --process-id 9904 `
  --output data/paper/live-monitor.json
```

OCR quotes are admitted only after schema/range checks and an independent
percentage-change calculation from the Tushare previous close. A single
verified frame has confidence `0.90`; matching consecutive frames have
confidence `0.95`. Price limits and suspension state also come from Tushare.
The resulting session deliberately contains no strategy candidates: observing
live quotes is not permission to invent a buy or sell signal.

For daily automation, Windows Task Scheduler should call `run-once` with a
freshly generated session file. A successful command exit does not itself
qualify a simulation day; post-close reconciliation and incident status must
also pass.
