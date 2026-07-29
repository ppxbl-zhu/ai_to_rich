# Deterministic strategy contracts

Strategy output is research advice for the paper account. Every generated plan
must still pass the common risk gate before it can become a simulated order.
LLM output cannot override any rule in this document.

## Swing trend

An entry requires all of the following:

- price above the 20-day average, which is above the 60-day average;
- price above the 10-week average;
- 60-day stock relative strength and sector relative strength above their
  configured thresholds;
- ROE above the floor, positive operating cash flow, and debt ratio below the
  ceiling;
- a risk-on market regime; and
- positive price and ATR inputs.

The default position risks at most 1% of current equity and consumes at most
10% of equity. Quantity is rounded down to a 100-share board lot. The initial
stop is two ATR below entry and the target is three times initial risk above
entry.

Exit evaluation is deterministic and ordered: initial stop, trailing stop,
20-day trend break, profit target, then maximum holding time. Earlier safety
conditions therefore take precedence when several rules trigger together.

All thresholds are explicit `SwingConfig` fields. A later experiment may
propose different bounded values, but it cannot mutate an active configuration
or skip out-of-sample validation.

## Closing-window short horizon

The scan runs only during the configured closing window. A candidate must have
fresh data, trade above intraday VWAP, close in the upper part of its daily
range, show adequate volume and turnover, outperform the market, and belong to
a strong sector with broad participation. A stock already at its upper price
limit is rejected because the planned entry is not realistically executable.

This strategy has its own default 15% account budget and a 5% per-position cap.
Each plan is rounded down to a 100-share lot. These caps are separate from the
swing allocation and remain subject to the common account risk gate.

On T1, an invalidation or 3% loss exits immediately, a 4% gain realizes the
target, and the position otherwise exits at the deadline. Extension to T2 is
the sole exception and requires every configured evidence gate:

- predicted continuation probability of at least 80%;
- at least 200 calibration observations and calibration error no greater than
  5%;
- confirmed evidence-backed company or event logic;
- confirmed sector linkage and intact stock structure;
- an allowed market regime;
- expected return after full costs of at least 0.5%; and
- no hard invalidation.

The probability is therefore not an LLM opinion and cannot authorize extension
by itself. Missing evidence fails closed. An extended position still obeys its
stop and target and must exit no later than the T2 deadline.
