from datetime import datetime, timedelta, timezone

from quantagent.platform_schedule import CycleKind, due_cycle

CST = timezone(timedelta(hours=8))


def at(hour: int, minute: int) -> datetime:
    return datetime(2026, 7, 30, hour, minute, tzinfo=CST)


def test_assigns_unique_five_minute_and_closing_scan_slots() -> None:
    morning = due_cycle(at(9, 32), is_trading_day=True)
    closing = due_cycle(at(14, 47), is_trading_day=True)

    assert morning is not None
    assert morning.kind is CycleKind.MONITOR
    assert morning.slot_id == "20260730-monitor-0930"
    assert closing is not None
    assert closing.kind is CycleKind.CLOSING
    assert closing.slot_id == "20260730-closing-1447"


def test_assigns_preopen_and_postclose_once_and_skips_breaks() -> None:
    assert due_cycle(at(9, 20), is_trading_day=True).kind is CycleKind.PREOPEN
    assert due_cycle(at(15, 12), is_trading_day=True).kind is CycleKind.POSTCLOSE
    assert due_cycle(at(12, 0), is_trading_day=True) is None
    assert due_cycle(at(9, 32), is_trading_day=False) is None
