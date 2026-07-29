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

Eastmoney `mainfree` is discoverable, but this client exposes only custom
`Pane` controls through UI Automation and no structured quote grid. Before OCR
or any navigation, the user must place the client on a visible market-only
page and confirm it contains no account, asset, position, order, or credential
information. Only then may the approved quote fields be mapped.

For daily automation, Windows Task Scheduler should call `run-once` with a
freshly generated session file. A successful command exit does not itself
qualify a simulation day; post-close reconciliation and incident status must
also pass.
