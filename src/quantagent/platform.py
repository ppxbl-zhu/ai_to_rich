from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from quantagent.operations import SimulationDay
from quantagent.platform_schedule import CycleKind, due_cycle

CycleHandler = Callable[[], dict[str, object]]


@dataclass(frozen=True, slots=True)
class CycleResult:
    slot_id: str
    kind: CycleKind
    started_at: datetime
    status: str
    details: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PlatformState:
    health: str
    last_heartbeat: datetime | None
    cycle_results: tuple[CycleResult, ...]


class PlatformStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> PlatformState:
        if not self.path.exists():
            return PlatformState("not_started", None, ())
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return PlatformState(
            health=str(payload["health"]),
            last_heartbeat=(
                datetime.fromisoformat(payload["last_heartbeat"])
                if payload.get("last_heartbeat")
                else None
            ),
            cycle_results=tuple(
                CycleResult(
                    slot_id=str(item["slot_id"]),
                    kind=CycleKind(item["kind"]),
                    started_at=datetime.fromisoformat(item["started_at"]),
                    status=str(item["status"]),
                    details=dict(item["details"]),
                )
                for item in payload["cycle_results"]
            ),
        )

    def save(self, state: PlatformState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "health": state.health,
            "last_heartbeat": (
                state.last_heartbeat.isoformat() if state.last_heartbeat else None
            ),
            "cycle_results": [
                {
                    **asdict(item),
                    "kind": item.kind.value,
                    "started_at": item.started_at.isoformat(),
                }
                for item in state.cycle_results[-200:]
            ],
        }
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


class PlatformController:
    def __init__(self, store: PlatformStore) -> None:
        self.store = store

    def run_due(
        self,
        now: datetime,
        *,
        is_trading_day: bool,
        handlers: Mapping[CycleKind, CycleHandler],
    ) -> CycleResult | None:
        scheduled = due_cycle(now, is_trading_day=is_trading_day)
        state = self.store.load()
        if scheduled is None:
            self.store.save(PlatformState(state.health, now, state.cycle_results))
            return None
        if scheduled.slot_id in {item.slot_id for item in state.cycle_results}:
            self.store.save(PlatformState(state.health, now, state.cycle_results))
            return None
        try:
            details = handlers[scheduled.kind]()
            status = "completed"
            health = "healthy"
        except Exception as error:
            details = {"reason": str(error)}
            status = "failed"
            health = "degraded"
        result = CycleResult(
            slot_id=scheduled.slot_id,
            kind=scheduled.kind,
            started_at=now,
            status=status,
            details=details,
        )
        self.store.save(PlatformState(health, now, (*state.cycle_results, result)))
        return result


def qualify_simulation_day(
    cycle_results: tuple[CycleResult, ...],
    *,
    trading_date: date,
    reconciled: bool,
    open_incidents: int,
) -> SimulationDay:
    daily_results = tuple(
        item for item in cycle_results if item.started_at.date() == trading_date
    )
    failed = any(item.status != "completed" for item in daily_results)
    return SimulationDay(
        trading_date=trading_date,
        completed=bool(daily_results) and not failed,
        reconciled=reconciled,
        critical_incident=failed or open_incidents > 0,
    )
