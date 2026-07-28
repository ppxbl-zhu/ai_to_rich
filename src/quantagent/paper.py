from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date
from decimal import Decimal

from quantagent.costs import ChinaAshareCostModel
from quantagent.domain import Fill, Portfolio, Position, Side, ValidatedOrder


class PaperBroker:
    def __init__(self, *, initial_cash: Decimal) -> None:
        self.portfolio = Portfolio(cash=initial_cash)
        self._costs = ChinaAshareCostModel()
        self._fills: dict[str, Fill] = {}

    def execute(self, order: ValidatedOrder) -> Fill:
        key = order.intent.idempotency_key
        if key in self._fills:
            return self._fills[key]

        plan = order.intent.plan
        costs = self._costs.calculate(
            symbol=plan.symbol,
            side=plan.side,
            quantity=plan.quantity,
            price=plan.limit_price,
        )
        turnover = plan.limit_price * plan.quantity
        positions = dict(self.portfolio.positions)

        if plan.side is Side.BUY:
            cash = self.portfolio.cash - turnover - costs.total
            existing = positions.get(plan.symbol)
            previous_quantity = existing.quantity if existing else 0
            previous_cost = (
                existing.average_cost * existing.quantity if existing else Decimal()
            )
            total_quantity = previous_quantity + plan.quantity
            average_cost = (previous_cost + turnover + costs.total) / total_quantity
            positions[plan.symbol] = Position(
                symbol=plan.symbol,
                quantity=total_quantity,
                available_quantity=existing.available_quantity if existing else 0,
                average_cost=average_cost,
                acquired_on=order.intent.trading_date,
            )
        else:
            existing = positions[plan.symbol]
            cash = self.portfolio.cash + turnover - costs.total
            remaining = existing.quantity - plan.quantity
            if remaining:
                positions[plan.symbol] = replace(
                    existing,
                    quantity=remaining,
                    available_quantity=existing.available_quantity - plan.quantity,
                )
            else:
                del positions[plan.symbol]

        fill = Fill(
            fill_id=hashlib.sha256(key.encode()).hexdigest()[:24],
            idempotency_key=key,
            symbol=plan.symbol,
            side=plan.side,
            quantity=plan.quantity,
            price=plan.limit_price,
            fee=costs.total,
            filled_at=order.validated_at,
            trading_date=order.intent.trading_date,
        )
        self.portfolio = Portfolio(cash=cash, positions=positions)
        self._fills[key] = fill
        return fill

    def settle(self, trading_date: date) -> None:
        positions = {
            symbol: (
                replace(position, available_quantity=position.quantity)
                if position.acquired_on < trading_date
                else position
            )
            for symbol, position in self.portfolio.positions.items()
        }
        self.portfolio = Portfolio(cash=self.portfolio.cash, positions=positions)
