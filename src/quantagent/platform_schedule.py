from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum


class CycleKind(StrEnum):
    PREOPEN = "preopen"
    MONITOR = "monitor"
    CLOSING = "closing"
    POSTCLOSE = "postclose"


@dataclass(frozen=True, slots=True)
class ScheduledCycle:
    slot_id: str
    kind: CycleKind


def due_cycle(now: datetime, *, is_trading_day: bool) -> ScheduledCycle | None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("platform time requires a timezone")
    if not is_trading_day:
        return None
    value = now.timetz().replace(tzinfo=None)
    date_prefix = now.strftime("%Y%m%d")
    if time(9, 15) <= value < time(9, 30):
        return ScheduledCycle(f"{date_prefix}-preopen", CycleKind.PREOPEN)
    if time(9, 30) <= value <= time(11, 30) or time(13) <= value < time(14, 45):
        slot_minute = now.minute - now.minute % 5
        return ScheduledCycle(
            f"{date_prefix}-monitor-{now.hour:02d}{slot_minute:02d}",
            CycleKind.MONITOR,
        )
    if time(14, 45) <= value <= time(14, 55):
        return ScheduledCycle(
            f"{date_prefix}-closing-{now:%H%M}",
            CycleKind.CLOSING,
        )
    if time(14, 56) <= value <= time(15):
        return ScheduledCycle(
            f"{date_prefix}-monitor-{now:%H%M}",
            CycleKind.MONITOR,
        )
    if value >= time(15, 10):
        return ScheduledCycle(f"{date_prefix}-postclose", CycleKind.POSTCLOSE)
    return None
