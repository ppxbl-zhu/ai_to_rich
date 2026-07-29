# Local paper platform

The platform is a local, paper-only service. It never connects to a broker or
submits a live order.

## Trading-day workflow

- 09:15-09:29: scan all active Shanghai and Shenzhen A shares from completed
  daily bars, then apply trend, relative-strength, sector, financial-quality,
  and market-regime gates to create the day's swing candidate pool.
- 09:30-11:30 and 13:00-14:44: refresh the full-market realtime snapshot every
  five minutes and monitor the scanned swing candidates and paper positions.
- 14:45-14:55: scan the full Shanghai and Shenzhen A-share snapshot every
  minute for the closing strategy.
- 14:56-15:00: continue position monitoring every minute.
- 15:10: reconcile position-plan metadata and stop simulated execution.
- 15:30: stop the local service.

Every time slot has a persistent identifier. A slot is recorded once even when
the scheduler polls repeatedly. Paper order intent keys are also persisted as
`strategy + symbol + trading date`, so a later monitoring session cannot repeat
the same daily order.

## Data sources

Both strategy universes start from the full Shanghai and Shenzhen A-share
market. A user's Eastmoney watchlist never defines, restricts, or ranks the
selection universe. Desktop OCR is outside the automatic selection path and
may only be used as an explicitly optional, read-only diagnostic.

Intraday and closing scans use a minimal, field-whitelisted client for Eastmoney's
public market pages. It retrieves Shanghai and Shenzhen pages concurrently
with a ten-second request timeout and rejects implausible universe sizes.
Tushare supplies the trading calendar, Shenwan membership, price limits, and
suspensions. The resulting fields include:

- cumulative VWAP from amount and volume;
- current price location within the daily range;
- stock return relative to the full-market median;
- sector median return relative to the market;
- sector breadth;
- volume ratio, turnover, and upper-limit status.

This web source is auxiliary and may change without notice. A timeout, schema
change, incomplete universe, missing sector, missing price limit, or stale
capture fails the affected cycle closed.

## Account and position management

The account begins with CNY 100,000. Paper fills include the configured
commission minimum, stamp tax, and transfer fee. T+1, board lots, price limits,
suspensions, cash, and stale quotes are checked by the common risk engine.

Each filled entry persists its strategy, stop, and target. On a later trading
day, a fresh quote at or beyond either boundary creates a simulated exit for
the available position. Restarting the platform does not lose these controls.

## Operations

The Windows task `QuantAgentPaper` starts a hidden PowerShell parent at 09:15
Monday through Friday, sets `D:\codex\ai_to_rich` as the working directory,
and runs `quantagent-platform`. The exchange calendar prevents trading cycles
on holidays. The hidden parent keeps the scheduled service unobtrusive.

Run or inspect manually:

```powershell
quantagent-platform cycle --process-id 9904
quantagent-platform status --process-id 9904
```

While the service is running, open:

- Dashboard: <http://127.0.0.1:8765/>
- JSON health: <http://127.0.0.1:8765/api/status>

Runtime state, sessions, and logs are stored below `data/paper/` and excluded
from Git. No broker or Eastmoney account/order page is used.
