from datetime import date
from decimal import Decimal

import pytest

from quantagent.swing import MarketRegime
from quantagent.swing_factors import (
    DailyFactorBar,
    FinancialFactors,
    derive_swing_candidate,
)


def bars(
    *,
    start: str,
    step: str,
    count: int = 70,
) -> tuple[DailyFactorBar, ...]:
    first = Decimal(start)
    increment = Decimal(step)
    result = []
    previous = first - increment
    for offset in range(count):
        close = first + increment * offset
        result.append(
            DailyFactorBar(
                trading_date=date(2026, 4, 1).fromordinal(
                    date(2026, 4, 1).toordinal() + offset
                ),
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                previous_close=previous,
            )
        )
        previous = close
    return tuple(result)


def test_derives_point_in_time_swing_factors_with_explicit_unit_conversion() -> None:
    candidate = derive_swing_candidate(
        symbol="300207.SZ",
        price=Decimal("80"),
        stock_bars=bars(start="10", step="1"),
        benchmark_bars=bars(start="100", step="0.5"),
        sector_bars=bars(start="50", step="0.75"),
        financials=FinancialFactors(
            roe_percent=Decimal("14.2"),
            debt_to_assets_percent=Decimal("45.6"),
            operating_cashflow=Decimal("100"),
        ),
    )

    assert candidate.ma20 == Decimal("69.5")
    assert candidate.ma60 == Decimal("49.5")
    assert candidate.weekly_ma10 == Decimal("52")
    assert candidate.relative_strength_60d == pytest.approx(Decimal("2.87081340"))
    assert candidate.sector_relative_strength == pytest.approx(Decimal("0.50587020"))
    assert candidate.roe == Decimal("0.142")
    assert candidate.debt_ratio == Decimal("0.456")
    assert candidate.operating_cashflow_positive is True
    assert candidate.atr == Decimal("2")
    assert candidate.market_regime is MarketRegime.RISK_ON


def test_rejects_incomplete_history_instead_of_shortening_factor_windows() -> None:
    with pytest.raises(ValueError, match="at least 60"):
        derive_swing_candidate(
            symbol="300207.SZ",
            price=Decimal("20"),
            stock_bars=bars(start="10", step="1", count=59),
            benchmark_bars=bars(start="100", step="0.5"),
            sector_bars=bars(start="50", step="0.75"),
            financials=FinancialFactors(
                roe_percent=Decimal("10"),
                debt_to_assets_percent=Decimal("50"),
                operating_cashflow=Decimal("1"),
            ),
        )
