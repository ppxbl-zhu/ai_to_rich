from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from quantagent.swing import MarketRegime, SwingCandidate


@dataclass(frozen=True, slots=True)
class DailyFactorBar:
    trading_date: date
    high: Decimal
    low: Decimal
    close: Decimal
    previous_close: Decimal


@dataclass(frozen=True, slots=True)
class FinancialFactors:
    roe_percent: Decimal
    debt_to_assets_percent: Decimal
    operating_cashflow: Decimal


def derive_swing_candidate(
    *,
    symbol: str,
    price: Decimal,
    stock_bars: tuple[DailyFactorBar, ...],
    benchmark_bars: tuple[DailyFactorBar, ...],
    sector_bars: tuple[DailyFactorBar, ...],
    financials: FinancialFactors,
) -> SwingCandidate:
    for series in (stock_bars, benchmark_bars, sector_bars):
        if len(series) < 60:
            raise ValueError("factor history requires at least 60 trading bars")
        if tuple(sorted(series, key=lambda item: item.trading_date)) != series:
            raise ValueError("factor history must be chronological")

    weekly_closes: dict[tuple[int, int], Decimal] = {}
    for bar in stock_bars:
        iso_year, iso_week, _ = bar.trading_date.isocalendar()
        weekly_closes[(iso_year, iso_week)] = bar.close
    if len(weekly_closes) < 10:
        raise ValueError("weekly trend requires at least 10 calendar weeks")

    benchmark_ma20 = _mean(item.close for item in benchmark_bars[-20:])
    benchmark_ma60 = _mean(item.close for item in benchmark_bars[-60:])
    market_regime = (
        MarketRegime.RISK_ON
        if benchmark_bars[-1].close > benchmark_ma20 > benchmark_ma60
        else MarketRegime.RISK_OFF
    )
    benchmark_return = _period_return(benchmark_bars)

    return SwingCandidate(
        symbol=symbol,
        price=price,
        ma20=_mean(item.close for item in stock_bars[-20:]),
        ma60=_mean(item.close for item in stock_bars[-60:]),
        weekly_ma10=_mean(tuple(weekly_closes.values())[-10:]),
        relative_strength_60d=_period_return(stock_bars) - benchmark_return,
        sector_relative_strength=_period_return(sector_bars) - benchmark_return,
        roe=financials.roe_percent / Decimal(100),
        operating_cashflow_positive=financials.operating_cashflow > 0,
        debt_ratio=financials.debt_to_assets_percent / Decimal(100),
        atr=_atr(stock_bars[-14:]),
        market_regime=market_regime,
    )


def _period_return(bars: tuple[DailyFactorBar, ...]) -> Decimal:
    window = bars[-60:]
    base = window[0].previous_close
    if base <= 0:
        raise ValueError("period return requires a positive base")
    return window[-1].close / base - Decimal(1)


def _atr(bars: tuple[DailyFactorBar, ...]) -> Decimal:
    ranges = (
        max(
            item.high - item.low,
            abs(item.high - item.previous_close),
            abs(item.low - item.previous_close),
        )
        for item in bars
    )
    result = _mean(ranges)
    if result <= 0:
        raise ValueError("ATR requires a positive range")
    return result


def _mean(values: Iterable[Decimal]) -> Decimal:
    items = tuple(values)
    if not items:
        raise ValueError("mean requires values")
    return sum(items, Decimal()) / Decimal(len(items))
