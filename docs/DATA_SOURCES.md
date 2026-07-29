# Data-source capability baseline

## Probe metadata

- Probe date: 2026-07-29
- Tushare account points reported by user: 6238
- Secrets stored in repository: none
- Probe output persisted: endpoint status and row count only

## Tushare

The following endpoints were called with small, read-only requests using the
locally supplied environment token:

| Endpoint | Result | Intended use |
|---|---|---|
| `trade_cal` | Available | Trading calendar |
| `stock_basic` | Available | Security master |
| `daily` | Available | Daily bars |
| `daily_basic` | Available | Turnover, valuation, and daily indicators |
| `stk_limit` | Available | Point-in-time daily price limits |
| `suspend_d` | Available | Suspension status |
| `moneyflow` | Available | Daily money-flow research |
| `index_daily` | Available | Index daily bars |
| `income_vip` | Available | Income statement |
| `balancesheet_vip` | Available | Balance sheet |
| `cashflow_vip` | Available | Cash-flow statement |
| `fina_indicator_vip` | Available | Financial indicators |
| `disclosure_date` | Available | Disclosure schedule |
| `share_float` | Available | Share unlock events |

A zero-row response was treated as a successful permission probe, not as
evidence that data exists for the chosen symbol and date.

The following remain disabled because the user has no separately purchased
permission:

| Endpoint/data | State | Reason |
|---|---|---|
| `rt_min` | Disabled | Realtime minute permission is separate from points |
| Historical minute data | Disabled | Historical minute permission is separate |
| `news` / `major_news` | Disabled | News permission is separate from points |

Official references:

- [Tushare permission model](https://tushare.pro/document/1?doc_id=290)
- [A-share realtime minute API](https://tushare.pro/document/2?doc_id=374)
- [Historical minute permission](https://tushare.pro/document/1?doc_id=234)
- [Daily basic API](https://tushare.pro/document/2?doc_id=32)
- [Financial indicator API](https://tushare.pro/document/2?doc_id=79)
- [News API](https://tushare.pro/document/2?doc_id=143)

## Eastmoney desktop

The read-only Windows UI Automation probe found:

- Process: `mainfree`
- Safe top-level window: `东方财富终端`
- Exposed UIA structure: 13 `Pane` controls and 1 `Window` control
- Exposed structured quote grids: none
- User-confirmed page scope: public market data only
- OCR language: installed Windows `zh-Hans-CN`
- Approved OCR region: visible watchlist quote table only

The probe read only the safe window title, process ID, and UIA control types. It
did not read control text, take screenshots, click, type, or connect to windows
whose titles contained trading, order, account, asset, position, transfer, buy,
or sell markers.

After the user approved the market-only page, the Milestone 9 collector read
the watchlist region in memory and extracted code, name, latest price, and
percentage change. It does not persist the frame or interact with account,
asset, position, order, credential, buy, or sell surfaces. OCR rows are
fail-closed on malformed fields, implausible values, window/layout changes, or
Tushare previous-close disagreement. Current price limits and suspension
metadata are joined from Tushare before conversion to the common quote model.

## Runtime policy

- Offline fixtures are the default in tests.
- Tushare common endpoints are the primary source for daily and financial data.
- No minute or news endpoint is treated as available without a successful
  separately authorized live probe.
- Eastmoney remains an auxiliary intraday source. Its OCR output is never
  accepted without Tushare cross-validation and complete risk metadata.
- The full-market closing scan uses a reviewed, minimal client for Eastmoney's
  public Shanghai and Shenzhen quote pages. Requests are concurrent, limited
  to approved quote fields, and bounded by a ten-second timeout. Tushare joins
  sector membership, price limits, suspensions, and the trading calendar.
  Schema drift, an implausibly small universe, or incomplete risk metadata
  disables the affected closing cycle.
- The 2026-07-29 rehearsal proved that a visible scheduler console can obscure
  the approved desktop OCR region. The task now runs under a hidden parent.
  A post-fix read recovered seven Tushare-verified quotes; the failed earlier
  cycles remain recorded and disqualify that rehearsal day.
- Every record carries event time, availability time, capture time, source,
  quality state, and dataset version.
- Conflicting providers cannot silently overwrite one another.
