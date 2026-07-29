from datetime import time
from decimal import Decimal

from quantagent.closing import (
    ClosingCandidate,
    ClosingConfig,
    ClosingStrategy,
    HoldingAction,
    T1Observation,
    T2ExtensionEvidence,
)


def candidate(**overrides: object) -> ClosingCandidate:
    values: dict[str, object] = {
        "symbol": "300001.SZ",
        "observed_at": time(14, 50),
        "price": Decimal("20"),
        "vwap": Decimal("19.60"),
        "close_location": Decimal("0.90"),
        "volume_ratio": Decimal("1.80"),
        "turnover": Decimal("120000000"),
        "stock_relative_strength": Decimal("0.08"),
        "sector_relative_strength": Decimal("0.06"),
        "sector_breadth": Decimal("0.70"),
        "at_limit_up": False,
        "fresh": True,
    }
    values.update(overrides)
    return ClosingCandidate(**values)  # type: ignore[arg-type]


def extension(**overrides: object) -> T2ExtensionEvidence:
    values: dict[str, object] = {
        "predicted_probability": Decimal("0.84"),
        "calibration_sample_size": 300,
        "calibration_error": Decimal("0.04"),
        "logic_evidence_confirmed": True,
        "sector_linkage_confirmed": True,
        "stock_structure_confirmed": True,
        "market_regime_allowed": True,
        "expected_net_return": Decimal("0.009"),
        "hard_invalidation": False,
    }
    values.update(overrides)
    return T2ExtensionEvidence(**values)  # type: ignore[arg-type]


def test_closing_scan_requires_confirmed_strength_and_sizes_separate_budget() -> None:
    strategy = ClosingStrategy(ClosingConfig())

    accepted = strategy.evaluate_candidate(candidate(), equity=Decimal("100000"))
    rejected = strategy.evaluate_candidate(
        candidate(sector_breadth=Decimal("0.40")), equity=Decimal("100000")
    )

    assert accepted.eligible is True
    assert accepted.plan is not None
    assert accepted.plan.quantity == 200
    assert accepted.plan.stop_price == Decimal("19.40")
    assert rejected.eligible is False
    assert "sector_breadth" in rejected.failed_rules


def test_t1_stop_overrides_extension_and_normal_position_exits_by_deadline() -> None:
    strategy = ClosingStrategy(ClosingConfig())

    assert (
        strategy.decide_t1(
            T1Observation(
                observed_at=time(10, 0),
                return_since_entry=Decimal("-0.04"),
                below_invalidation=True,
            ),
            extension(),
        )
        is HoldingAction.EXIT_STOP
    )
    assert (
        strategy.decide_t1(
            T1Observation(
                observed_at=time(14, 50),
                return_since_entry=Decimal("0.02"),
                below_invalidation=False,
            ),
            None,
        )
        is HoldingAction.EXIT_T1_DEADLINE
    )


def test_t2_extension_requires_calibration_logic_sector_and_positive_net_edge() -> None:
    strategy = ClosingStrategy(ClosingConfig())
    observation = T1Observation(
        observed_at=time(14, 50),
        return_since_entry=Decimal("0.015"),
        below_invalidation=False,
    )

    assert strategy.decide_t1(observation, extension()) is HoldingAction.EXTEND_TO_T2
    assert (
        strategy.decide_t1(observation, extension(calibration_sample_size=30))
        is HoldingAction.EXIT_T1_DEADLINE
    )
    assert (
        strategy.decide_t1(observation, extension(sector_linkage_confirmed=False))
        is HoldingAction.EXIT_T1_DEADLINE
    )


def test_t2_position_always_exits_no_later_than_configured_deadline() -> None:
    strategy = ClosingStrategy(ClosingConfig())

    assert (
        strategy.decide_t2(
            observed_at=time(14, 50),
            return_since_entry=Decimal("0.08"),
            below_invalidation=False,
        )
        is HoldingAction.EXIT_T2_DEADLINE
    )
