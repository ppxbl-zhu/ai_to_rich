from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from hashlib import sha256

from quantagent.costs import ChinaAshareCostModel
from quantagent.domain import Fill, Side


@dataclass(frozen=True, slots=True)
class BacktestBar:
    symbol: str
    trading_date: date
    opened_at: datetime
    closed_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    suspended: bool
    limit_up: Decimal
    limit_down: Decimal


@dataclass(frozen=True, slots=True)
class BacktestOrder:
    idempotency_key: str
    symbol: str
    side: Side
    quantity: int
    generated_at: datetime


class BacktestStatus(StrEnum):
    FILLED = "filled"
    UNFILLED_LIMIT = "unfilled_limit"
    UNFILLED_SUSPENDED = "unfilled_suspended"
    NO_FUTURE_BAR = "no_future_bar"
    REJECTED_T1 = "rejected_t1"
    REJECTED_CASH = "rejected_cash"


@dataclass(frozen=True, slots=True)
class BacktestOrderResult:
    key: str
    status: BacktestStatus


@dataclass(frozen=True, slots=True)
class BacktestReport:
    initial_equity: Decimal
    final_equity: Decimal
    total_return: Decimal
    max_drawdown: Decimal
    turnover: Decimal
    trade_count: int
    dataset_version: str
    config_version: str
    random_seed: int


@dataclass(frozen=True, slots=True)
class BacktestResult:
    fills: tuple[Fill, ...]
    orders: tuple[BacktestOrderResult, ...]
    report: BacktestReport


class BacktestEngine:
    def __init__(
        self,
        *,
        initial_cash: Decimal = Decimal("100000.00"),
        slippage_bps: Decimal = Decimal(),
    ) -> None:
        self.initial_cash = initial_cash
        self.slippage_bps = slippage_bps

    def run(
        self,
        *,
        bars: list[BacktestBar],
        orders: list[BacktestOrder],
        dataset_version: str,
        config_version: str,
        random_seed: int,
    ) -> BacktestResult:
        ordered_bars = sorted(bars, key=lambda bar: bar.opened_at)
        indexed_orders = list(enumerate(orders))
        attempts: dict[int, list[tuple[int, BacktestOrder]]] = {}
        results: dict[int, BacktestOrderResult] = {}

        for order_index, order in indexed_orders:
            future_index = next(
                (
                    index
                    for index, bar in enumerate(ordered_bars)
                    if bar.symbol == order.symbol and bar.opened_at > order.generated_at
                ),
                None,
            )
            if future_index is None:
                results[order_index] = BacktestOrderResult(
                    key=order.idempotency_key,
                    status=BacktestStatus.NO_FUTURE_BAR,
                )
            else:
                attempts.setdefault(future_index, []).append((order_index, order))

        cash = self.initial_cash
        positions: dict[str, PositionState] = {}
        fills: list[Fill] = []
        equity_curve = [self.initial_cash]
        latest_closes: dict[str, Decimal] = {}
        cost_model = ChinaAshareCostModel()

        for bar_index, bar in enumerate(ordered_bars):
            position = positions.get(bar.symbol)
            if position is not None and position.acquired_on < bar.trading_date:
                position.available_quantity = position.quantity

            for order_index, order in attempts.get(bar_index, []):
                status = self._unfilled_status(bar, order.side)
                if status is not None:
                    results[order_index] = BacktestOrderResult(
                        key=order.idempotency_key, status=status
                    )
                    continue

                price = self._fill_price(bar.open, order.side)
                costs = cost_model.calculate(
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    price=price,
                )
                turnover = price * order.quantity
                position = positions.get(order.symbol)
                if order.side is Side.BUY:
                    debit = turnover + costs.total
                    if debit > cash:
                        status = BacktestStatus.REJECTED_CASH
                    else:
                        cash -= debit
                        self._add_position(positions, order, price, bar.trading_date)
                        status = BacktestStatus.FILLED
                elif position is None or position.available_quantity < order.quantity:
                    status = BacktestStatus.REJECTED_T1
                else:
                    cash += turnover - costs.total
                    self._reduce_position(positions, order)
                    status = BacktestStatus.FILLED

                results[order_index] = BacktestOrderResult(
                    key=order.idempotency_key, status=status
                )
                if status is BacktestStatus.FILLED:
                    fills.append(
                        Fill(
                            fill_id=sha256(
                                order.idempotency_key.encode("utf-8")
                            ).hexdigest()[:24],
                            idempotency_key=order.idempotency_key,
                            symbol=order.symbol,
                            side=order.side,
                            quantity=order.quantity,
                            price=price,
                            fee=costs.total,
                            filled_at=bar.opened_at,
                            trading_date=bar.trading_date,
                        )
                    )

            latest_closes[bar.symbol] = bar.close
            equity_curve.append(
                cash
                + sum(
                    position.quantity * latest_closes.get(symbol, position.average_cost)
                    for symbol, position in positions.items()
                )
            )

        final_equity = equity_curve[-1]
        peak = equity_curve[0]
        max_drawdown = Decimal()
        for equity in equity_curve:
            peak = max(peak, equity)
            if peak:
                max_drawdown = max(max_drawdown, (peak - equity) / peak)
        turnover = sum((fill.price * fill.quantity for fill in fills), start=Decimal())
        return BacktestResult(
            fills=tuple(fills),
            orders=tuple(results[index] for index in range(len(orders))),
            report=BacktestReport(
                initial_equity=self.initial_cash,
                final_equity=final_equity,
                total_return=(final_equity - self.initial_cash) / self.initial_cash,
                max_drawdown=max_drawdown,
                turnover=turnover,
                trade_count=len(fills),
                dataset_version=dataset_version,
                config_version=config_version,
                random_seed=random_seed,
            ),
        )

    def _fill_price(self, price: Decimal, side: Side) -> Decimal:
        direction = Decimal(1) if side is Side.BUY else Decimal(-1)
        multiplier = Decimal(1) + direction * self.slippage_bps / Decimal(10000)
        return (price * multiplier).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _unfilled_status(bar: BacktestBar, side: Side) -> BacktestStatus | None:
        if bar.suspended:
            return BacktestStatus.UNFILLED_SUSPENDED
        if (side is Side.BUY and bar.open >= bar.limit_up) or (
            side is Side.SELL and bar.open <= bar.limit_down
        ):
            return BacktestStatus.UNFILLED_LIMIT
        return None

    @staticmethod
    def _add_position(
        positions: dict[str, PositionState],
        order: BacktestOrder,
        price: Decimal,
        trading_date: date,
    ) -> None:
        existing = positions.get(order.symbol)
        if existing is None:
            positions[order.symbol] = PositionState(
                quantity=order.quantity,
                available_quantity=0,
                average_cost=price,
                acquired_on=trading_date,
            )
            return
        total_quantity = existing.quantity + order.quantity
        existing.average_cost = (
            existing.average_cost * existing.quantity + price * order.quantity
        ) / total_quantity
        existing.quantity = total_quantity
        existing.acquired_on = trading_date

    @staticmethod
    def _reduce_position(
        positions: dict[str, PositionState], order: BacktestOrder
    ) -> None:
        position = positions[order.symbol]
        position.quantity -= order.quantity
        position.available_quantity -= order.quantity
        if position.quantity == 0:
            del positions[order.symbol]


@dataclass(slots=True)
class PositionState:
    quantity: int
    available_quantity: int
    average_cost: Decimal
    acquired_on: date
