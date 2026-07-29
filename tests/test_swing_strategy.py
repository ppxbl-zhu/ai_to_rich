from decimal import Decimal

from quantagent.swing import (
    MarketRegime,
    SwingCandidate,
    SwingConfig,
    SwingExitReason,
    SwingPositionState,
    SwingTrendStrategy,
)


def candidate(**overrides: object) -> SwingCandidate:
    values: dict[str, object] = {
        "symbol": "000001.SZ",
        "price": Decimal("12.00"),
        "ma20": Decimal("11.50"),
        "ma60": Decimal("10.50"),
        "weekly_ma10": Decimal("10.80"),
        "relative_strength_60d": Decimal("0.12"),
        "sector_relative_strength": Decimal("0.08"),
        "roe": Decimal("0.14"),
        "operating_cashflow_positive": True,
        "debt_ratio": Decimal("0.45"),
        "atr": Decimal("0.40"),
        "market_regime": MarketRegime.RISK_ON,
    }
    values.update(overrides)
    return SwingCandidate(**values)  # type: ignore[arg-type]


def test_swing_entry_requires_trend_strength_quality_and_market_regime() -> None:
    strategy = SwingTrendStrategy(SwingConfig())

    accepted = strategy.evaluate_entry(candidate(), equity=Decimal("100000"))
    rejected = strategy.evaluate_entry(
        candidate(operating_cashflow_positive=False),
        equity=Decimal("100000"),
    )

    assert accepted.eligible is True
    assert accepted.plan is not None
    assert accepted.plan.quantity == 800
    assert accepted.plan.stop_price == Decimal("11.20")
    assert accepted.plan.target_price == Decimal("14.40")
    assert rejected.eligible is False
    assert rejected.plan is None
    assert "operating_cashflow" in rejected.failed_rules


def test_swing_position_size_respects_risk_and_capital_caps_in_board_lots() -> None:
    strategy = SwingTrendStrategy(SwingConfig(max_position_fraction=Decimal("0.15")))

    decision = strategy.evaluate_entry(
        candidate(price=Decimal("30"), ma20=Decimal("28"), atr=Decimal("0.50")),
        equity=Decimal("100000"),
    )

    assert decision.plan is not None
    assert decision.plan.quantity == 500
    assert decision.plan.quantity % 100 == 0


def test_swing_exit_is_deterministic_for_stop_trend_target_and_time() -> None:
    strategy = SwingTrendStrategy(SwingConfig(max_holding_days=20))
    position = SwingPositionState(
        entry_price=Decimal("12"),
        initial_stop=Decimal("11.20"),
        highest_close=Decimal("14"),
        holding_days=8,
    )

    assert (
        strategy.evaluate_exit(position, close=Decimal("11.10"), ma20=Decimal("11.40"))
        is SwingExitReason.STOP
    )
    assert (
        strategy.evaluate_exit(position, close=Decimal("12.50"), ma20=Decimal("12.80"))
        is SwingExitReason.TREND_BREAK
    )
    assert (
        strategy.evaluate_exit(position, close=Decimal("14.50"), ma20=Decimal("13.00"))
        is SwingExitReason.TARGET
    )
    assert (
        strategy.evaluate_exit(
            SwingPositionState(
                entry_price=Decimal("12"),
                initial_stop=Decimal("11.20"),
                highest_close=Decimal("12.30"),
                holding_days=20,
            ),
            close=Decimal("12.10"),
            ma20=Decimal("11.80"),
        )
        is SwingExitReason.TIME
    )
