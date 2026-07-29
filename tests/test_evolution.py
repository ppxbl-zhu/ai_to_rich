from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from quantagent.evolution import (
    Experiment,
    ExperimentMetrics,
    ExperimentRegistry,
    FitnessError,
    Genome,
    ParameterBound,
    PromotionDecision,
    fitness,
    mutate,
)

NOW = datetime.fromisoformat("2026-07-29T18:00:00+08:00")
BOUNDS = {
    "minimum_strength": ParameterBound(
        minimum=Decimal("0.02"),
        maximum=Decimal("0.15"),
        step=Decimal("0.01"),
    ),
    "stop_fraction": ParameterBound(
        minimum=Decimal("0.02"),
        maximum=Decimal("0.08"),
        step=Decimal("0.01"),
    ),
}


def metrics(**overrides: object) -> ExperimentMetrics:
    values: dict[str, object] = {
        "out_of_sample_return": Decimal("0.12"),
        "max_drawdown": Decimal("0.08"),
        "sharpe": Decimal("1.4"),
        "win_rate": Decimal("0.58"),
        "profit_loss_ratio": Decimal("1.5"),
        "trade_count": 80,
        "turnover": Decimal("2.0"),
        "cost_fraction": Decimal("0.02"),
        "parameter_sensitivity": Decimal("0.10"),
        "cross_period_stability": Decimal("0.75"),
    }
    values.update(overrides)
    return ExperimentMetrics(**values)  # type: ignore[arg-type]


def experiment(experiment_id: str, parent_id: str | None = None) -> Experiment:
    return Experiment(
        experiment_id=experiment_id,
        parent_experiment_id=parent_id,
        created_at=NOW,
        strategy_name="swing",
        strategy_version="swing-v1",
        git_commit="abc123",
        dataset_version="sha256:data",
        universe_version="sha256:universe",
        train_period=("2024-01-01", "2024-12-31"),
        validation_period=("2025-01-01", "2025-06-30"),
        test_period=("2025-07-01", "2025-12-31"),
        random_seed=7,
        genome=Genome(
            values={
                "minimum_strength": Decimal("0.05"),
                "stop_fraction": Decimal("0.03"),
            },
            bounds=BOUNDS,
        ),
        metrics=metrics(),
        llm_hypothesis_id=None,
    )


def test_mutation_is_seeded_bounded_and_snapped_to_declared_steps() -> None:
    genome = experiment("root").genome

    first = mutate(genome, random_seed=9, mutation_probability=Decimal("1"))
    second = mutate(genome, random_seed=9, mutation_probability=Decimal("1"))

    assert first == second
    assert first != genome
    for name, value in first.values.items():
        bound = BOUNDS[name]
        assert bound.minimum <= value <= bound.maximum
        assert (value - bound.minimum) % bound.step == 0


def test_fitness_is_multi_objective_and_rejects_invalid_or_small_samples() -> None:
    strong = fitness(metrics())
    fragile = fitness(
        metrics(max_drawdown=Decimal("0.25"), parameter_sensitivity=Decimal("0.8"))
    )

    assert strong > fragile
    with pytest.raises(FitnessError, match="trade count"):
        fitness(metrics(trade_count=10))
    with pytest.raises(FitnessError, match="finite"):
        fitness(metrics(sharpe=Decimal("NaN")))


def test_registry_preserves_lineage_and_requires_manual_promotion() -> None:
    registry = ExperimentRegistry()
    registry.record(experiment("root"))
    registry.record(experiment("child", "root"))

    assert registry.lineage("child") == ("root", "child")
    assert (
        registry.promotion_decision("child", manually_approved=False)
        is PromotionDecision.REJECTED_MANUAL_APPROVAL
    )
    assert (
        registry.promotion_decision("child", manually_approved=True)
        is PromotionDecision.APPROVED_PAPER
    )

    registry.record(
        replace(
            experiment("fragile", "child"),
            metrics=metrics(max_drawdown=Decimal("0.30")),
        )
    )
    assert (
        registry.promotion_decision("fragile", manually_approved=True)
        is PromotionDecision.REJECTED_EVIDENCE
    )
