from datetime import datetime, timedelta, timezone
from pathlib import Path

from quantagent.platform import (
    PlatformController,
    PlatformStore,
    qualify_simulation_day,
)
from quantagent.platform_schedule import CycleKind

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 9, 32, tzinfo=CST)


def test_persists_cycle_result_and_never_repeats_same_slot(tmp_path: Path) -> None:
    store = PlatformStore(tmp_path / "platform.json")
    controller = PlatformController(store)
    calls = []

    first = controller.run_due(
        NOW,
        is_trading_day=True,
        handlers={CycleKind.MONITOR: lambda: calls.append("monitor") or {"quotes": 7}},
    )
    second = controller.run_due(
        NOW + timedelta(minutes=1),
        is_trading_day=True,
        handlers={CycleKind.MONITOR: lambda: calls.append("duplicate") or {}},
    )

    assert first is not None
    assert first.status == "completed"
    assert first.details == {"quotes": 7}
    assert second is None
    assert calls == ["monitor"]
    assert store.load().cycle_results == (first,)


def test_records_failed_cycle_without_treating_it_as_success(tmp_path: Path) -> None:
    store = PlatformStore(tmp_path / "platform.json")
    controller = PlatformController(store)

    def fail() -> dict[str, object]:
        raise RuntimeError("quote source unavailable")

    result = controller.run_due(
        NOW,
        is_trading_day=True,
        handlers={CycleKind.MONITOR: fail},
    )

    assert result is not None
    assert result.status == "failed"
    assert result.details == {"reason": "quote source unavailable"}
    assert store.load().health == "degraded"


def test_any_failed_intraday_cycle_disqualifies_simulation_day(
    tmp_path: Path,
) -> None:
    store = PlatformStore(tmp_path / "platform.json")
    controller = PlatformController(store)
    controller.run_due(
        NOW,
        is_trading_day=True,
        handlers={CycleKind.MONITOR: lambda: {"quotes": 7}},
    )

    def fail() -> dict[str, object]:
        raise RuntimeError("OCR unavailable")

    controller.run_due(
        NOW + timedelta(minutes=5),
        is_trading_day=True,
        handlers={CycleKind.MONITOR: fail},
    )

    day = qualify_simulation_day(
        store.load().cycle_results,
        trading_date=NOW.date(),
        reconciled=True,
        open_incidents=0,
    )

    assert day.completed is False
    assert day.reconciled is True
    assert day.critical_incident is True
