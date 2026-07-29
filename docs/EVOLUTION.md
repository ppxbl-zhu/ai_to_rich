# Genetic evolution contract

Evolution searches declared strategy parameters; it cannot generate code,
change risk controls, or promote itself.

Each parameter has a decimal minimum, maximum, and step. A genome must contain
exactly the declared parameters, and every value must lie on the configured
grid. Mutation is seeded and reproducible.

Fitness is multi-objective. It rewards untouched out-of-sample return, Sharpe,
win rate, profit/loss ratio, and cross-period stability. It penalizes maximum
drawdown, transaction-cost share, turnover, and parameter sensitivity. NaN,
infinite values, negative risk/cost inputs, or fewer than 30 trades fail the
experiment rather than becoming zero-valued observations.

Every experiment records:

- its parent experiment and optional LLM hypothesis;
- creation time, strategy and code version;
- dataset and historical-universe versions;
- train, validation, and untouched test periods;
- random seed, genome, parameter bounds, metrics, and fitness; and
- failure and promotion records.

Promotion to the formal paper account requires positive out-of-sample return,
maximum drawdown no greater than 20%, Sharpe of at least 1, at least 50 trades,
bounded parameter sensitivity, cross-period stability, and explicit human
approval. These are engineering defaults for evidence gating, not a promise of
future returns. Live promotion is outside this component.
