from __future__ import annotations

from datetime import datetime, timedelta

from quantagent.costs import ChinaAshareCostModel
from quantagent.domain import (
    Board,
    MarketQuote,
    OrderIntent,
    Portfolio,
    SecurityStatus,
    Side,
    ValidatedOrder,
)


class RiskViolation(ValueError):
    """Raised when an order fails a deterministic risk rule."""


class RiskEngine:
    def __init__(self, *, max_quote_age: timedelta = timedelta(seconds=60)) -> None:
        self.max_quote_age = max_quote_age
        self._kill_switch_reason: str | None = None
        self._validated_keys: set[str] = set()
        self._costs = ChinaAshareCostModel()

    def activate_kill_switch(self, reason: str) -> None:
        self._kill_switch_reason = reason

    def validate(
        self,
        intent: OrderIntent,
        quote: MarketQuote,
        portfolio: Portfolio,
        *,
        now: datetime,
    ) -> ValidatedOrder:
        if self._kill_switch_reason is not None:
            raise RiskViolation(f"kill switch active: {self._kill_switch_reason}")
        if intent.idempotency_key in self._validated_keys:
            raise RiskViolation("duplicate order idempotency key")
        if intent.plan.symbol != quote.symbol:
            raise RiskViolation("order and quote symbol mismatch")
        if not quote.name.strip():
            raise RiskViolation("security name is required")
        if quote.status is not SecurityStatus.ACTIVE:
            raise RiskViolation("security is not tradable")
        if now - quote.captured_at > self.max_quote_age:
            raise RiskViolation("quote is stale")
        if quote.market_time.date() != intent.trading_date:
            raise RiskViolation("quote and order trading date differ")
        if quote.price <= 0 or intent.plan.limit_price <= 0:
            raise RiskViolation("price must be positive")
        if quote.limit_up is None or quote.limit_down is None:
            raise RiskViolation("price limit metadata is required")
        if not quote.limit_down <= intent.plan.limit_price <= quote.limit_up:
            raise RiskViolation("order is outside the daily price limit")

        self._validate_quantity(intent, quote, portfolio)
        if intent.plan.side is Side.BUY:
            costs = self._costs.calculate(
                symbol=intent.plan.symbol,
                side=Side.BUY,
                quantity=intent.plan.quantity,
                price=intent.plan.limit_price,
            )
            required_cash = intent.plan.limit_price * intent.plan.quantity + costs.total
            if required_cash > portfolio.cash:
                raise RiskViolation("insufficient cash")

        validated = ValidatedOrder(intent=intent, validated_at=now)
        self._validated_keys.add(intent.idempotency_key)
        return validated

    @staticmethod
    def _validate_quantity(
        intent: OrderIntent, quote: MarketQuote, portfolio: Portfolio
    ) -> None:
        quantity = intent.plan.quantity
        if quantity <= 0:
            raise RiskViolation("quantity must be positive")

        if intent.plan.side is Side.BUY:
            if quote.board is Board.STAR:
                if quantity < 200:
                    raise RiskViolation("STAR buy quantity must be at least 200")
            elif quantity % 100:
                raise RiskViolation("buy quantity must be a multiple of 100")
            return

        position = portfolio.positions.get(intent.plan.symbol)
        if position is None or quantity > position.available_quantity:
            raise RiskViolation("T+1 available position is insufficient")
        if (
            quantity < position.quantity
            and quote.board is not Board.STAR
            and quantity % 100
        ):
            raise RiskViolation("partial sell quantity must be a multiple of 100")
