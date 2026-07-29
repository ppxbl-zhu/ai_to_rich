# Backtesting contract

The backtester is an event-driven research component, not a live execution
engine.

## Timing and fills

- An order may use only the first bar for its symbol whose opening timestamp is
  strictly later than the signal timestamp.
- A failed first execution attempt is recorded and is not silently retried.
- Suspensions and opening at the applicable price limit remain unfilled.
- Buy and sell slippage move the price against the portfolio.
- A-share transaction costs use the versioned Eastmoney schedule in
  `quantagent.costs`.
- Shares purchased on a trading date cannot be sold until a later trading
  date.

## Evaluation

Walk-forward windows are strictly chronological and non-overlapping within
each split: train, validation, then test. Strategy choices may use train and
validation data only. Test windows are untouched until the selected candidate
is evaluated.

Historical inputs must come from the point-in-time contracts established in
Milestone 2. A run report records the dataset version, configuration version,
and random seed so the result can be reproduced. It also exposes ending
equity, total return, maximum drawdown, turnover, fills, and every rejected or
unfilled order.

This design prevents same-bar look-ahead. Survivorship control remains a data
responsibility: the supplied universe must represent securities known on each
historical date, including subsequently suspended or delisted securities.
