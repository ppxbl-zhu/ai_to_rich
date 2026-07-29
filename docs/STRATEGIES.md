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
