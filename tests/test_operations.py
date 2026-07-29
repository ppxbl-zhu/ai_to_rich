from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from quantagent.operations import (
    IncidentManager,
    JobSchedule,
    LedgerState,
    OperationsSnapshot,
    ReconciliationStatus,
    Scheduler,
    Severity,
    SimulationDay,
    SimulationTracker,
    build_dashboard,
    evaluate_alerts,
    reconcile,
)

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 15, 30, tzinfo=CST)


def ledger(*, cash: str = "80000") -> LedgerState:
    return LedgerState(
        cash=Decimal(cash),
        positions={"000001.SZ": 1000},
        order_ids=("order-1",),
        fill_ids=("fill-1",),
    )


def test_dashboard_exposes_portfolio_strategy_data_job_and_incident_health() -> None:
    snapshot = OperationsSnapshot(
        captured_at=NOW,
        equity=Decimal("101000"),
        cash=Decimal("80000"),
        drawdown=Decimal("0.03"),
        strategy_exposure={"swing": Decimal("15000"), "closing": Decimal("6000")},
        data_status="fresh",
        scheduler_status="healthy",
        reconciliation_status=ReconciliationStatus.MATCHED,
        open_incidents=0,
        active_strategy_version="swing-v1",
        source_experiment_id="experiment-12",
    )

    dashboard = build_dashboard(snapshot)

    assert dashboard["portfolio"]["equity"] == "101000"
    assert dashboard["strategies"]["closing"] == "6000"
    assert dashboard["health"] == {
        "data": "fresh",
        "scheduler": "healthy",
        "reconciliation": "matched",
        "open_incidents": 0,
    }
    assert dashboard["lineage"]["experiment_id"] == "experiment-12"


def test_alerts_escalate_stale_data_drawdown_and_reconciliation_failure() -> None:
    snapshot = OperationsSnapshot(
        captured_at=NOW,
        equity=Decimal("90000"),
        cash=Decimal("90000"),
        drawdown=Decimal("0.11"),
        strategy_exposure={},
        data_status="stale",
        scheduler_status="degraded",
        reconciliation_status=ReconciliationStatus.MISMATCHED,
        open_incidents=1,
        active_strategy_version="swing-v1",
        source_experiment_id="experiment-12",
    )

    alerts = evaluate_alerts(snapshot)

    assert tuple(alert.code for alert in alerts) == (
        "DATA_UNAVAILABLE",
        "RECONCILIATION_FAILED",
        "DRAWDOWN_LIMIT",
        "SCHEDULER_DEGRADED",
    )
    assert all(alert.severity is Severity.CRITICAL for alert in alerts[:3])


def test_scheduler_runs_due_jobs_once_and_only_on_trading_days() -> None:
    scheduler = Scheduler(
        (
            JobSchedule("pre_open", time(8, 30), trading_days_only=True),
            JobSchedule("daily_backup", time(2, 0), trading_days_only=False),
        )
    )

    assert scheduler.due_jobs(NOW, is_trading_day=True) == (
        "pre_open",
        "daily_backup",
    )
    scheduler.mark_succeeded("pre_open", NOW)
    assert scheduler.due_jobs(NOW, is_trading_day=True) == ("daily_backup",)
    assert scheduler.due_jobs(NOW, is_trading_day=False) == ("daily_backup",)


def test_reconciliation_reports_differences_instead_of_overwriting_ledgers() -> None:
    report = reconcile(ledger(), ledger(cash="79999"))

    assert report.status is ReconciliationStatus.MISMATCHED
    assert report.severity is Severity.CRITICAL
    assert report.differences == ("cash expected 80000 actual 79999",)
    assert ledger().cash == Decimal("80000")


def test_critical_incident_latches_kill_switch_until_resolved_and_cleared() -> None:
    manager = IncidentManager()
    incident = manager.open(
        incident_id="incident-1",
        severity=Severity.CRITICAL,
        category="reconciliation",
        message="paper ledger mismatch",
        opened_at=NOW,
    )

    assert manager.kill_switch is True
    with pytest.raises(RuntimeError, match="critical incident"):
        manager.clear_kill_switch()

    manager.resolve(incident.incident_id, NOW)
    manager.clear_kill_switch()
    assert manager.kill_switch is False


def test_paper_promotion_requires_twenty_consecutive_qualified_trading_days() -> None:
    tracker = SimulationTracker(required_days=20)
    start = date(2026, 7, 1)
    for offset in range(19):
        tracker.record(
            SimulationDay(
                trading_date=start + timedelta(days=offset),
                completed=True,
                reconciled=True,
                critical_incident=False,
            )
        )
    assert tracker.status().eligible_for_review is False
    assert tracker.status().qualifying_streak == 19

    tracker.record(
        SimulationDay(
            trading_date=start + timedelta(days=19),
            completed=True,
            reconciled=True,
            critical_incident=False,
        )
    )
    assert tracker.status().eligible_for_review is True

    tracker.record(
        SimulationDay(
            trading_date=start + timedelta(days=20),
            completed=True,
            reconciled=False,
            critical_incident=False,
        )
    )
    assert tracker.status().qualifying_streak == 0
    assert tracker.status().eligible_for_review is False
