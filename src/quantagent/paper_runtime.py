from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from quantagent.closing import ClosingCandidate, ClosingConfig, ClosingStrategy
from quantagent.domain import (
    MarketQuote,
    OrderIntent,
    Portfolio,
    Position,
    TradePlan,
)
from quantagent.paper import PaperBroker
from quantagent.risk import RiskEngine, RiskViolation
from quantagent.swing import SwingCandidate, SwingConfig, SwingTrendStrategy


class RuntimeStatus(StrEnum):
    COMPLETED = "completed"
    STOPPED = "stopped"
    BLOCKED = "blocked"
    ALREADY_PROCESSED = "already_processed"


class RuntimeBusy(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PaperSession:
    session_id: str
    trading_date: date
    captured_at: datetime
    dataset_version: str
    is_trading_day: bool
    quotes: Mapping[str, MarketQuote]
    swing_candidates: tuple[SwingCandidate, ...]
    closing_candidates: tuple[ClosingCandidate, ...]


@dataclass(frozen=True, slots=True)
class RuntimeState:
    enabled: bool
    cash: Decimal
    positions: Mapping[str, int]
    available_positions: Mapping[str, int]
    average_costs: Mapping[str, Decimal]
    acquired_on: Mapping[str, date]
    processed_session_ids: tuple[str, ...]
    blocked_session_ids: tuple[str, ...]
    fill_ids: tuple[str, ...]
    open_incidents: int
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    stop_reason: str | None


@dataclass(frozen=True, slots=True)
class RuntimeReport:
    status: RuntimeStatus
    session_id: str
    dataset_version: str
    generated_plans: int = 0
    fills: int = 0
    rejected_plans: int = 0
    reason: str | None = None


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_suffix(f"{path.suffix}.lock")

    def load(self) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState(
                enabled=False,
                cash=Decimal("100000.00"),
                positions={},
                available_positions={},
                average_costs={},
                acquired_on={},
                processed_session_ids=(),
                blocked_session_ids=(),
                fill_ids=(),
                open_incidents=0,
                last_started_at=None,
                last_stopped_at=None,
                stop_reason="not started",
            )
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeState(
            enabled=bool(payload["enabled"]),
            cash=Decimal(payload["cash"]),
            positions={key: int(value) for key, value in payload["positions"].items()},
            available_positions={
                key: int(value) for key, value in payload["available_positions"].items()
            },
            average_costs={
                key: Decimal(value) for key, value in payload["average_costs"].items()
            },
            acquired_on={
                key: date.fromisoformat(value)
                for key, value in payload["acquired_on"].items()
            },
            processed_session_ids=tuple(payload["processed_session_ids"]),
            blocked_session_ids=tuple(payload.get("blocked_session_ids", [])),
            fill_ids=tuple(payload["fill_ids"]),
            open_incidents=int(payload["open_incidents"]),
            last_started_at=_optional_datetime(payload["last_started_at"]),
            last_stopped_at=_optional_datetime(payload["last_stopped_at"]),
            stop_reason=payload["stop_reason"],
        )

    def save(self, state: RuntimeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "enabled": state.enabled,
            "cash": str(state.cash),
            "positions": dict(state.positions),
            "available_positions": dict(state.available_positions),
            "average_costs": {
                key: str(value) for key, value in state.average_costs.items()
            },
            "acquired_on": {
                key: value.isoformat() for key, value in state.acquired_on.items()
            },
            "processed_session_ids": list(state.processed_session_ids),
            "blocked_session_ids": list(state.blocked_session_ids),
            "fill_ids": list(state.fill_ids),
            "open_incidents": state.open_incidents,
            "last_started_at": _optional_isoformat(state.last_started_at),
            "last_stopped_at": _optional_isoformat(state.last_stopped_at),
            "stop_reason": state.stop_reason,
        }
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    @contextmanager
    def locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise RuntimeBusy("another paper runtime process holds the lock") from error
        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.close(descriptor)
            yield
        finally:
            if self.lock_path.exists():
                self.lock_path.unlink()


class PaperRuntime:
    def __init__(
        self,
        store: JsonStateStore,
        *,
        maximum_session_age: timedelta = timedelta(seconds=60),
    ) -> None:
        self.store = store
        self.maximum_session_age = maximum_session_age

    def start(self, started_at: datetime) -> RuntimeState:
        with self.store.locked():
            state = replace(
                self.store.load(),
                enabled=True,
                last_started_at=started_at,
                stop_reason=None,
            )
            self.store.save(state)
            return state

    def stop(self, stopped_at: datetime, *, reason: str) -> RuntimeState:
        if not reason.strip():
            raise ValueError("stop reason is required")
        with self.store.locked():
            state = replace(
                self.store.load(),
                enabled=False,
                last_stopped_at=stopped_at,
                stop_reason=reason,
            )
            self.store.save(state)
            return state

    def status(self) -> RuntimeState:
        return self.store.load()

    def run_once(self, session: PaperSession, *, now: datetime) -> RuntimeReport:
        with self.store.locked():
            state = self.store.load()
            base_report = {
                "session_id": session.session_id,
                "dataset_version": session.dataset_version,
            }
            if not state.enabled:
                return RuntimeReport(RuntimeStatus.STOPPED, **base_report)
            if session.session_id in state.processed_session_ids:
                return RuntimeReport(RuntimeStatus.ALREADY_PROCESSED, **base_report)
            blocked_reason = self._blocked_reason(session, now)
            if blocked_reason is not None:
                if session.session_id not in state.blocked_session_ids:
                    state = replace(
                        state,
                        open_incidents=state.open_incidents + 1,
                        blocked_session_ids=(
                            *state.blocked_session_ids,
                            session.session_id,
                        ),
                    )
                    self.store.save(state)
                return RuntimeReport(
                    RuntimeStatus.BLOCKED,
                    reason=blocked_reason,
                    **base_report,
                )

            portfolio = self._portfolio(state, session.trading_date)
            equity = portfolio.cash + sum(
                position.quantity * session.quotes[symbol].price
                for symbol, position in portfolio.positions.items()
            )
            plans = self._plans(session, equity)
            broker = PaperBroker(initial_cash=portfolio.cash)
            broker.portfolio = portfolio
            risk = RiskEngine(max_quote_age=self.maximum_session_age)
            rejected = 0
            fills = []
            for strategy_name, plan in plans:
                intent = OrderIntent(
                    idempotency_key=(
                        f"{strategy_name}:{plan.symbol}:{session.trading_date.isoformat()}"
                    ),
                    created_at=now,
                    trading_date=session.trading_date,
                    plan=plan,
                )
                try:
                    validated = risk.validate(
                        intent,
                        session.quotes[plan.symbol],
                        broker.portfolio,
                        now=now,
                    )
                except RiskViolation:
                    rejected += 1
                    continue
                fills.append(broker.execute(validated))

            new_state = self._state_after(
                state,
                broker.portfolio,
                session.session_id,
                tuple(fill.fill_id for fill in fills),
            )
            self.store.save(new_state)
            return RuntimeReport(
                RuntimeStatus.COMPLETED,
                generated_plans=len(plans),
                fills=len(fills),
                rejected_plans=rejected,
                **base_report,
            )

    def _blocked_reason(self, session: PaperSession, now: datetime) -> str | None:
        if not session.is_trading_day:
            return "session date is not a trading day"
        if session.trading_date != now.date():
            return "session and runtime trading dates differ"
        age = now - session.captured_at
        if age < timedelta() or age > self.maximum_session_age:
            return "session data is stale"
        symbols = {candidate.symbol for candidate in session.swing_candidates} | {
            candidate.symbol for candidate in session.closing_candidates
        }
        if not symbols.issubset(session.quotes):
            return "candidate quote is missing"
        return None

    @staticmethod
    def _plans(
        session: PaperSession, equity: Decimal
    ) -> tuple[tuple[str, TradePlan], ...]:
        plans: list[tuple[str, TradePlan]] = []
        swing = SwingTrendStrategy(SwingConfig())
        for candidate in session.swing_candidates:
            decision = swing.evaluate_entry(candidate, equity=equity)
            if decision.plan is not None:
                plans.append(("swing", decision.plan))
        closing = ClosingStrategy(ClosingConfig())
        for candidate in session.closing_candidates:
            decision = closing.evaluate_candidate(candidate, equity=equity)
            if decision.plan is not None:
                plans.append(("closing", decision.plan))
        return tuple(plans)

    @staticmethod
    def _portfolio(state: RuntimeState, trading_date: date) -> Portfolio:
        positions = {
            symbol: Position(
                symbol=symbol,
                quantity=quantity,
                available_quantity=(
                    quantity
                    if state.acquired_on[symbol] < trading_date
                    else state.available_positions[symbol]
                ),
                average_cost=state.average_costs[symbol],
                acquired_on=state.acquired_on[symbol],
            )
            for symbol, quantity in state.positions.items()
        }
        return Portfolio(cash=state.cash, positions=positions)

    @staticmethod
    def _state_after(
        previous: RuntimeState,
        portfolio: Portfolio,
        session_id: str,
        fill_ids: tuple[str, ...],
    ) -> RuntimeState:
        return replace(
            previous,
            cash=portfolio.cash,
            positions={
                symbol: position.quantity
                for symbol, position in portfolio.positions.items()
            },
            available_positions={
                symbol: position.available_quantity
                for symbol, position in portfolio.positions.items()
            },
            average_costs={
                symbol: position.average_cost
                for symbol, position in portfolio.positions.items()
            },
            acquired_on={
                symbol: position.acquired_on
                for symbol, position in portfolio.positions.items()
            },
            processed_session_ids=(
                *previous.processed_session_ids,
                session_id,
            ),
            fill_ids=(*previous.fill_ids, *fill_ids),
        )


def _optional_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _optional_isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
