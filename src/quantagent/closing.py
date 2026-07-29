from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from quantagent.domain import Side, TradePlan


class HoldingAction(StrEnum):
    HOLD_T1 = "hold_t1"
    EXIT_STOP = "exit_stop"
    EXIT_TARGET = "exit_target"
    EXIT_T1_DEADLINE = "exit_t1_deadline"
    EXTEND_TO_T2 = "extend_to_t2"
    HOLD_T2 = "hold_t2"
    EXIT_T2_DEADLINE = "exit_t2_deadline"


@dataclass(frozen=True, slots=True)
class ClosingConfig:
    scan_start: time = time(14, 45)
    scan_end: time = time(14, 55)
    minimum_close_location: Decimal = Decimal("0.80")
    minimum_volume_ratio: Decimal = Decimal("1.50")
    minimum_turnover: Decimal = Decimal("50000000")
    minimum_stock_strength: Decimal = Decimal("0.05")
    minimum_sector_strength: Decimal = Decimal("0.03")
    minimum_sector_breadth: Decimal = Decimal("0.60")
    strategy_budget_fraction: Decimal = Decimal("0.15")
    max_position_fraction: Decimal = Decimal("0.05")
    stop_fraction: Decimal = Decimal("0.03")
    target_fraction: Decimal = Decimal("0.04")
    t1_exit_deadline: time = time(14, 45)
    t2_exit_deadline: time = time(14, 45)
    extension_probability: Decimal = Decimal("0.80")
    minimum_calibration_sample: int = 200
    maximum_calibration_error: Decimal = Decimal("0.05")
    minimum_expected_net_return: Decimal = Decimal("0.005")


@dataclass(frozen=True, slots=True)
class ClosingCandidate:
    symbol: str
    observed_at: time
    price: Decimal
    vwap: Decimal
    close_location: Decimal
    volume_ratio: Decimal
    turnover: Decimal
    stock_relative_strength: Decimal
    sector_relative_strength: Decimal
    sector_breadth: Decimal
    at_limit_up: bool
    fresh: bool


@dataclass(frozen=True, slots=True)
class ClosingDecision:
    eligible: bool
    score: Decimal
    failed_rules: tuple[str, ...]
    plan: TradePlan | None


@dataclass(frozen=True, slots=True)
class T1Observation:
    observed_at: time
    return_since_entry: Decimal
    below_invalidation: bool


@dataclass(frozen=True, slots=True)
class T2ExtensionEvidence:
    predicted_probability: Decimal
    calibration_sample_size: int
    calibration_error: Decimal
    logic_evidence_confirmed: bool
    sector_linkage_confirmed: bool
    stock_structure_confirmed: bool
    market_regime_allowed: bool
    expected_net_return: Decimal
    hard_invalidation: bool


class ClosingStrategy:
    def __init__(self, config: ClosingConfig) -> None:
        self.config = config

    def evaluate_candidate(
        self,
        candidate: ClosingCandidate,
        *,
        equity: Decimal,
        existing_strategy_exposure: Decimal = Decimal(),
    ) -> ClosingDecision:
        remaining_budget = max(
            Decimal(),
            equity * self.config.strategy_budget_fraction - existing_strategy_exposure,
        )
        checks = {
            "scan_window": (
                self.config.scan_start <= candidate.observed_at <= self.config.scan_end
            ),
            "fresh": candidate.fresh,
            "price_above_vwap": candidate.price > candidate.vwap,
            "close_location": (
                candidate.close_location >= self.config.minimum_close_location
            ),
            "volume_ratio": (
                candidate.volume_ratio >= self.config.minimum_volume_ratio
            ),
            "turnover": candidate.turnover >= self.config.minimum_turnover,
            "stock_strength": (
                candidate.stock_relative_strength >= self.config.minimum_stock_strength
            ),
            "sector_strength": (
                candidate.sector_relative_strength
                >= self.config.minimum_sector_strength
            ),
            "sector_breadth": (
                candidate.sector_breadth >= self.config.minimum_sector_breadth
            ),
            "not_limit_up": not candidate.at_limit_up,
            "strategy_budget": remaining_budget >= candidate.price * 100,
        }
        failed_rules = tuple(name for name, passed in checks.items() if not passed)
        score = Decimal(sum(checks.values())) / Decimal(len(checks))
        if failed_rules:
            return ClosingDecision(False, score, failed_rules, None)

        capital = min(
            equity * self.config.max_position_fraction,
            remaining_budget,
        )
        quantity = int(
            (capital / candidate.price / 100).to_integral_value(rounding=ROUND_DOWN)
            * 100
        )
        if quantity <= 0:
            return ClosingDecision(False, score, ("position_below_board_lot",), None)
        return ClosingDecision(
            True,
            score,
            (),
            TradePlan(
                symbol=candidate.symbol,
                side=Side.BUY,
                quantity=quantity,
                limit_price=candidate.price,
                stop_price=candidate.price * (Decimal(1) - self.config.stop_fraction),
                target_price=candidate.price
                * (Decimal(1) + self.config.target_fraction),
                invalidation="strength, sector linkage, freshness, or risk gate fails",
            ),
        )

    def decide_t1(
        self,
        observation: T1Observation,
        evidence: T2ExtensionEvidence | None,
    ) -> HoldingAction:
        if (
            observation.below_invalidation
            or observation.return_since_entry <= -self.config.stop_fraction
        ):
            return HoldingAction.EXIT_STOP
        if observation.return_since_entry >= self.config.target_fraction:
            return HoldingAction.EXIT_TARGET
        if observation.observed_at < self.config.t1_exit_deadline:
            return HoldingAction.HOLD_T1
        if evidence is not None and self._extension_allowed(evidence):
            return HoldingAction.EXTEND_TO_T2
        return HoldingAction.EXIT_T1_DEADLINE

    def decide_t2(
        self,
        *,
        observed_at: time,
        return_since_entry: Decimal,
        below_invalidation: bool,
    ) -> HoldingAction:
        if below_invalidation or return_since_entry <= -self.config.stop_fraction:
            return HoldingAction.EXIT_STOP
        if observed_at >= self.config.t2_exit_deadline:
            return HoldingAction.EXIT_T2_DEADLINE
        if return_since_entry >= self.config.target_fraction:
            return HoldingAction.EXIT_TARGET
        return HoldingAction.HOLD_T2

    def _extension_allowed(self, evidence: T2ExtensionEvidence) -> bool:
        return all(
            (
                evidence.predicted_probability >= self.config.extension_probability,
                evidence.calibration_sample_size
                >= self.config.minimum_calibration_sample,
                evidence.calibration_error <= self.config.maximum_calibration_error,
                evidence.logic_evidence_confirmed,
                evidence.sector_linkage_confirmed,
                evidence.stock_structure_confirmed,
                evidence.market_regime_allowed,
                evidence.expected_net_return >= self.config.minimum_expected_net_return,
                not evidence.hard_invalidation,
            )
        )
