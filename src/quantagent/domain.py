from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class Board(StrEnum):
    MAIN = "main"
    CHINEXT = "chinext"
    STAR = "star"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class SecurityStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ST = "st"
    DELISTING = "delisting"


@dataclass(frozen=True, slots=True)
class MarketQuote:
    symbol: str
    name: str
    board: Board
    market_time: datetime
    captured_at: datetime
    price: Decimal
    previous_close: Decimal
    limit_up: Decimal | None
    limit_down: Decimal | None
    status: SecurityStatus
    source: str


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: str
    started_at: datetime
    ended_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    amount: Decimal
    source: str


@dataclass(frozen=True, slots=True)
class Signal:
    signal_id: str
    symbol: str
    strategy: str
    generated_at: datetime
    score: Decimal
    rationale: str
    data_version: str


@dataclass(frozen=True, slots=True)
class TradePlan:
    symbol: str
    side: Side
    quantity: int
    limit_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    invalidation: str


@dataclass(frozen=True, slots=True)
class OrderIntent:
    idempotency_key: str
    created_at: datetime
    trading_date: date
    plan: TradePlan


@dataclass(frozen=True, slots=True)
class ValidatedOrder:
    intent: OrderIntent
    validated_at: datetime


@dataclass(frozen=True, slots=True)
class Fill:
    fill_id: str
    idempotency_key: str
    symbol: str
    side: Side
    quantity: int
    price: Decimal
    fee: Decimal
    filled_at: datetime
    trading_date: date


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    quantity: int
    available_quantity: int
    average_cost: Decimal
    acquired_on: date


@dataclass(frozen=True, slots=True)
class Portfolio:
    cash: Decimal
    positions: dict[str, Position] = field(default_factory=dict)
