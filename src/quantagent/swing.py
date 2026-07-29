from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from quantagent.domain import Side, TradePlan


class MarketRegime(StrEnum):
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"


class SwingExitReason(StrEnum):
    HOLD = "hold"
    STOP = "stop"
    TRAILING_STOP = "trailing_stop"
    TREND_BREAK = "trend_break"
    TARGET = "target"
    TIME = "time"


@dataclass(frozen=True, slots=True)
class SwingConfig:
    minimum_relative_strength: Decimal = Decimal("0.05")
    minimum_sector_strength: Decimal = Decimal("0.02")
    minimum_roe: Decimal = Decimal("0.08")
    maximum_debt_ratio: Decimal = Decimal("0.70")
    risk_fraction: Decimal = Decimal("0.01")
    max_position_fraction: Decimal = Decimal("0.10")
    stop_atr_multiple: Decimal = Decimal("2")
    reward_risk_multiple: Decimal = Decimal("3")
    trailing_risk_multiple: Decimal = Decimal("2")
    max_holding_days: int = 20


@dataclass(frozen=True, slots=True)
class SwingCandidate:
    symbol: str
    price: Decimal
    ma20: Decimal
    ma60: Decimal
    weekly_ma10: Decimal
    relative_strength_60d: Decimal
    sector_relative_strength: Decimal
    roe: Decimal
    operating_cashflow_positive: bool
    debt_ratio: Decimal
    atr: Decimal
    market_regime: MarketRegime


@dataclass(frozen=True, slots=True)
class SwingEntryDecision:
    eligible: bool
    score: Decimal
    failed_rules: tuple[str, ...]
    plan: TradePlan | None


@dataclass(frozen=True, slots=True)
class SwingPositionState:
    entry_price: Decimal
    initial_stop: Decimal
    highest_close: Decimal
    holding_days: int


class SwingTrendStrategy:
    def __init__(self, config: SwingConfig) -> None:
        self.config = config

    def evaluate_entry(
        self, candidate: SwingCandidate, *, equity: Decimal
    ) -> SwingEntryDecision:
        checks = {
            "daily_trend": candidate.price > candidate.ma20 > candidate.ma60,
            "weekly_trend": candidate.price > candidate.weekly_ma10,
            "relative_strength": (
                candidate.relative_strength_60d >= self.config.minimum_relative_strength
            ),
            "sector_strength": (
                candidate.sector_relative_strength
                >= self.config.minimum_sector_strength
            ),
            "roe": candidate.roe >= self.config.minimum_roe,
            "operating_cashflow": candidate.operating_cashflow_positive,
            "debt_ratio": candidate.debt_ratio <= self.config.maximum_debt_ratio,
            "market_regime": candidate.market_regime is MarketRegime.RISK_ON,
            "valid_price_and_atr": candidate.price > 0 and candidate.atr > 0,
        }
        failed_rules = tuple(name for name, passed in checks.items() if not passed)
        score = Decimal(sum(checks.values())) / Decimal(len(checks))
        if failed_rules:
            return SwingEntryDecision(False, score, failed_rules, None)

        stop_price = candidate.price - candidate.atr * self.config.stop_atr_multiple
        per_share_risk = candidate.price - stop_price
        risk_quantity = equity * self.config.risk_fraction / per_share_risk
        capital_quantity = equity * self.config.max_position_fraction / candidate.price
        quantity = int(
            (min(risk_quantity, capital_quantity) / 100).to_integral_value(
                rounding=ROUND_DOWN
            )
            * 100
        )
        if quantity <= 0:
            return SwingEntryDecision(False, score, ("position_below_board_lot",), None)
        target_price = candidate.price + (
            per_share_risk * self.config.reward_risk_multiple
        )
        return SwingEntryDecision(
            True,
            score,
            (),
            TradePlan(
                symbol=candidate.symbol,
                side=Side.BUY,
                quantity=quantity,
                limit_price=candidate.price,
                stop_price=stop_price,
                target_price=target_price,
                invalidation="trend, quality, market regime, or risk gate fails",
            ),
        )

    def evaluate_exit(
        self,
        position: SwingPositionState,
        *,
        close: Decimal,
        ma20: Decimal,
    ) -> SwingExitReason:
        initial_risk = position.entry_price - position.initial_stop
        target = position.entry_price + initial_risk * self.config.reward_risk_multiple
        trailing_stop = (
            position.highest_close - initial_risk * self.config.trailing_risk_multiple
        )
        if close <= position.initial_stop:
            return SwingExitReason.STOP
        if close <= trailing_stop:
            return SwingExitReason.TRAILING_STOP
        if close < ma20:
            return SwingExitReason.TREND_BREAK
        if close >= target:
            return SwingExitReason.TARGET
        if position.holding_days >= self.config.max_holding_days:
            return SwingExitReason.TIME
        return SwingExitReason.HOLD
