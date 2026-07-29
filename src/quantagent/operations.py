from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ReconciliationStatus(StrEnum):
    MATCHED = "matched"
    MISMATCHED = "mismatched"


@dataclass(frozen=True, slots=True)
class Alert:
    code: str
    severity: Severity
    message: str


@dataclass(frozen=True, slots=True)
class OperationsSnapshot:
    captured_at: datetime
    equity: Decimal
    cash: Decimal
    drawdown: Decimal
    strategy_exposure: Mapping[str, Decimal]
    data_status: str
    scheduler_status: str
    reconciliation_status: ReconciliationStatus
    open_incidents: int
    active_strategy_version: str
    source_experiment_id: str


def build_dashboard(snapshot: OperationsSnapshot) -> dict[str, Any]:
    return {
        "captured_at": snapshot.captured_at.isoformat(),
        "portfolio": {
            "equity": str(snapshot.equity),
            "cash": str(snapshot.cash),
            "drawdown": str(snapshot.drawdown),
        },
        "strategies": {
            name: str(exposure)
            for name, exposure in sorted(snapshot.strategy_exposure.items())
        },
        "health": {
            "data": snapshot.data_status,
            "scheduler": snapshot.scheduler_status,
            "reconciliation": snapshot.reconciliation_status.value,
            "open_incidents": snapshot.open_incidents,
        },
        "lineage": {
            "strategy_version": snapshot.active_strategy_version,
            "experiment_id": snapshot.source_experiment_id,
        },
    }


def evaluate_alerts(snapshot: OperationsSnapshot) -> tuple[Alert, ...]:
    alerts: list[Alert] = []
    if snapshot.data_status != "fresh":
        alerts.append(
            Alert(
                "DATA_UNAVAILABLE",
                Severity.CRITICAL,
                "Market data is unavailable or stale; new advice is disabled.",
            )
        )
    if snapshot.reconciliation_status is ReconciliationStatus.MISMATCHED:
        alerts.append(
            Alert(
                "RECONCILIATION_FAILED",
                Severity.CRITICAL,
                "Paper ledger reconciliation failed; execution is disabled.",
            )
        )
    if snapshot.drawdown >= Decimal("0.10"):
        alerts.append(
            Alert(
                "DRAWDOWN_LIMIT",
                Severity.CRITICAL,
                "Account drawdown reached the configured circuit breaker.",
            )
        )
    if snapshot.scheduler_status != "healthy":
        alerts.append(
            Alert(
                "SCHEDULER_DEGRADED",
                Severity.WARNING,
                "One or more scheduled jobs are late or failed.",
            )
        )
    return tuple(alerts)


@dataclass(frozen=True, slots=True)
class JobSchedule:
    name: str
    run_at: time
    trading_days_only: bool


class Scheduler:
    def __init__(self, schedules: tuple[JobSchedule, ...]) -> None:
        names = [schedule.name for schedule in schedules]
        if len(names) != len(set(names)):
            raise ValueError("scheduled job names must be unique")
        self._schedules = schedules
        self._last_success: dict[str, datetime] = {}

    def due_jobs(self, now: datetime, *, is_trading_day: bool) -> tuple[str, ...]:
        due = []
        for schedule in self._schedules:
            if schedule.trading_days_only and not is_trading_day:
                continue
            if now.timetz().replace(tzinfo=None) < schedule.run_at:
                continue
            last_success = self._last_success.get(schedule.name)
            if last_success is not None and last_success.date() == now.date():
                continue
            due.append(schedule.name)
        return tuple(due)

    def mark_succeeded(self, job_name: str, completed_at: datetime) -> None:
        if job_name not in {schedule.name for schedule in self._schedules}:
            raise KeyError(job_name)
        self._last_success[job_name] = completed_at


@dataclass(frozen=True, slots=True)
class LedgerState:
    cash: Decimal
    positions: Mapping[str, int]
    order_ids: tuple[str, ...]
    fill_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    status: ReconciliationStatus
    severity: Severity
    differences: tuple[str, ...]


def reconcile(expected: LedgerState, actual: LedgerState) -> ReconciliationReport:
    differences: list[str] = []
    if expected.cash != actual.cash:
        differences.append(f"cash expected {expected.cash} actual {actual.cash}")
    symbols = sorted(set(expected.positions) | set(actual.positions))
    for symbol in symbols:
        expected_quantity = expected.positions.get(symbol, 0)
        actual_quantity = actual.positions.get(symbol, 0)
        if expected_quantity != actual_quantity:
            differences.append(
                f"{symbol} quantity expected {expected_quantity} "
                f"actual {actual_quantity}"
            )
    if expected.order_ids != actual.order_ids:
        differences.append("order ids differ")
    if expected.fill_ids != actual.fill_ids:
        differences.append("fill ids differ")
    if differences:
        return ReconciliationReport(
            ReconciliationStatus.MISMATCHED,
            Severity.CRITICAL,
            tuple(differences),
        )
    return ReconciliationReport(ReconciliationStatus.MATCHED, Severity.INFO, ())


@dataclass(frozen=True, slots=True)
class Incident:
    incident_id: str
    severity: Severity
    category: str
    message: str
    opened_at: datetime
    resolved_at: datetime | None = None


class IncidentManager:
    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}
        self.kill_switch = False

    def open(
        self,
        *,
        incident_id: str,
        severity: Severity,
        category: str,
        message: str,
        opened_at: datetime,
    ) -> Incident:
        if incident_id in self._incidents:
            raise ValueError("incident id already exists")
        incident = Incident(
            incident_id=incident_id,
            severity=severity,
            category=category,
            message=message,
            opened_at=opened_at,
        )
        self._incidents[incident_id] = incident
        if severity is Severity.CRITICAL:
            self.kill_switch = True
        return incident

    def resolve(self, incident_id: str, resolved_at: datetime) -> None:
        incident = self._incidents[incident_id]
        if incident.resolved_at is not None:
            raise ValueError("incident is already resolved")
        self._incidents[incident_id] = replace(incident, resolved_at=resolved_at)

    def clear_kill_switch(self) -> None:
        if any(
            incident.severity is Severity.CRITICAL and incident.resolved_at is None
            for incident in self._incidents.values()
        ):
            raise RuntimeError("critical incident remains open")
        self.kill_switch = False


@dataclass(frozen=True, slots=True)
class SimulationDay:
    trading_date: date
    completed: bool
    reconciled: bool
    critical_incident: bool


@dataclass(frozen=True, slots=True)
class SimulationStatus:
    recorded_days: int
    qualifying_streak: int
    required_days: int
    eligible_for_review: bool


class SimulationTracker:
    def __init__(self, *, required_days: int = 20) -> None:
        if required_days <= 0:
            raise ValueError("required days must be positive")
        self.required_days = required_days
        self._days: list[SimulationDay] = []

    def record(self, day: SimulationDay) -> None:
        if self._days and day.trading_date <= self._days[-1].trading_date:
            raise ValueError("simulation days must be unique and chronological")
        self._days.append(day)

    def status(self) -> SimulationStatus:
        streak = 0
        for day in self._days:
            if day.completed and day.reconciled and not day.critical_incident:
                streak += 1
            else:
                streak = 0
        return SimulationStatus(
            recorded_days=len(self._days),
            qualifying_streak=streak,
            required_days=self.required_days,
            eligible_for_review=streak >= self.required_days,
        )
