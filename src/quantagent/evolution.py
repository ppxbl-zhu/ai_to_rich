from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from random import Random
from types import MappingProxyType


class FitnessError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParameterBound:
    minimum: Decimal
    maximum: Decimal
    step: Decimal

    def __post_init__(self) -> None:
        if self.step <= 0 or self.minimum > self.maximum:
            raise ValueError("parameter bound must have a positive ordered range")
        if (self.maximum - self.minimum) % self.step:
            raise ValueError("parameter range must be divisible by its step")


@dataclass(frozen=True, slots=True)
class Genome:
    values: Mapping[str, Decimal]
    bounds: Mapping[str, ParameterBound]

    def __post_init__(self) -> None:
        if set(self.values) != set(self.bounds) or not self.values:
            raise ValueError("genome values must exactly match declared bounds")
        for name, value in self.values.items():
            bound = self.bounds[name]
            if not bound.minimum <= value <= bound.maximum:
                raise ValueError(f"{name} is outside its declared bound")
            if (value - bound.minimum) % bound.step:
                raise ValueError(f"{name} is not aligned to its declared step")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        object.__setattr__(self, "bounds", MappingProxyType(dict(self.bounds)))


@dataclass(frozen=True, slots=True)
class ExperimentMetrics:
    out_of_sample_return: Decimal
    max_drawdown: Decimal
    sharpe: Decimal
    win_rate: Decimal
    profit_loss_ratio: Decimal
    trade_count: int
    turnover: Decimal
    cost_fraction: Decimal
    parameter_sensitivity: Decimal
    cross_period_stability: Decimal


@dataclass(frozen=True, slots=True)
class Experiment:
    experiment_id: str
    parent_experiment_id: str | None
    created_at: datetime
    strategy_name: str
    strategy_version: str
    git_commit: str
    dataset_version: str
    universe_version: str
    train_period: tuple[str, str]
    validation_period: tuple[str, str]
    test_period: tuple[str, str]
    random_seed: int
    genome: Genome
    metrics: ExperimentMetrics
    llm_hypothesis_id: str | None


class PromotionDecision(StrEnum):
    APPROVED_PAPER = "approved_paper"
    REJECTED_EVIDENCE = "rejected_evidence"
    REJECTED_MANUAL_APPROVAL = "rejected_manual_approval"


def mutate(
    genome: Genome,
    *,
    random_seed: int,
    mutation_probability: Decimal = Decimal("0.20"),
) -> Genome:
    if not Decimal() <= mutation_probability <= Decimal(1):
        raise ValueError("mutation probability must be between zero and one")
    random = Random(random_seed)
    values = dict(genome.values)
    for name in sorted(values):
        if Decimal(str(random.random())) > mutation_probability:
            continue
        bound = genome.bounds[name]
        step_count = int((bound.maximum - bound.minimum) / bound.step)
        values[name] = bound.minimum + bound.step * random.randint(0, step_count)
    return Genome(values=values, bounds=genome.bounds)


def fitness(metrics: ExperimentMetrics) -> Decimal:
    decimal_values = (
        metrics.out_of_sample_return,
        metrics.max_drawdown,
        metrics.sharpe,
        metrics.win_rate,
        metrics.profit_loss_ratio,
        metrics.turnover,
        metrics.cost_fraction,
        metrics.parameter_sensitivity,
        metrics.cross_period_stability,
    )
    if any(not value.is_finite() for value in decimal_values):
        raise FitnessError("all fitness metrics must be finite")
    if metrics.trade_count < 30:
        raise FitnessError("trade count is below the minimum sample")
    if metrics.max_drawdown < 0 or metrics.cost_fraction < 0:
        raise FitnessError("risk and cost metrics cannot be negative")
    return (
        metrics.out_of_sample_return * Decimal("3")
        + metrics.sharpe * Decimal("0.20")
        + metrics.win_rate * Decimal("0.20")
        + metrics.profit_loss_ratio * Decimal("0.10")
        + metrics.cross_period_stability * Decimal("0.30")
        - metrics.max_drawdown * Decimal("2")
        - metrics.cost_fraction * Decimal("1.5")
        - metrics.turnover * Decimal("0.01")
        - metrics.parameter_sensitivity * Decimal("0.50")
    )


class ExperimentRegistry:
    def __init__(self) -> None:
        self._experiments: dict[str, Experiment] = {}

    def record(self, experiment: Experiment) -> None:
        if experiment.experiment_id in self._experiments:
            raise ValueError("experiment id already exists")
        parent_id = experiment.parent_experiment_id
        if parent_id is not None and parent_id not in self._experiments:
            raise ValueError("parent experiment does not exist")
        fitness(experiment.metrics)
        self._experiments[experiment.experiment_id] = experiment

    def lineage(self, experiment_id: str) -> tuple[str, ...]:
        lineage: list[str] = []
        current = self._experiments[experiment_id]
        while True:
            lineage.append(current.experiment_id)
            if current.parent_experiment_id is None:
                break
            current = self._experiments[current.parent_experiment_id]
        return tuple(reversed(lineage))

    def promotion_decision(
        self, experiment_id: str, *, manually_approved: bool
    ) -> PromotionDecision:
        metrics = self._experiments[experiment_id].metrics
        evidence_passes = all(
            (
                metrics.out_of_sample_return > 0,
                metrics.max_drawdown <= Decimal("0.20"),
                metrics.sharpe >= Decimal("1"),
                metrics.trade_count >= 50,
                metrics.parameter_sensitivity <= Decimal("0.30"),
                metrics.cross_period_stability >= Decimal("0.60"),
            )
        )
        if not evidence_passes:
            return PromotionDecision.REJECTED_EVIDENCE
        if not manually_approved:
            return PromotionDecision.REJECTED_MANUAL_APPROVAL
        return PromotionDecision.APPROVED_PAPER
