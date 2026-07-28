from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from quantagent.domain import OrderIntent, Side, TradePlan, ValidatedOrder
from quantagent.paper import PaperBroker

CN_TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 14, 50, tzinfo=CN_TZ)


def order(
    *,
    side: Side,
    trading_date: date,
    quantity: int = 100,
    price: Decimal = Decimal("10.00"),
    key: str,
) -> ValidatedOrder:
    return ValidatedOrder(
        intent=OrderIntent(
            idempotency_key=key,
            created_at=NOW,
            trading_date=trading_date,
            plan=TradePlan(
                symbol="000001.SZ",
                side=side,
                quantity=quantity,
                limit_price=price,
                stop_price=Decimal("9.50"),
                target_price=Decimal("11.00"),
                invalidation="跌破止损",
            ),
        ),
        validated_at=NOW,
    )


def test_paper_buy_preserves_cash_and_t0_position_accounting() -> None:
    broker = PaperBroker(initial_cash=Decimal("100000.00"))

    fill = broker.execute(
        order(side=Side.BUY, trading_date=date(2026, 7, 29), key="buy-1")
    )

    assert fill.fee == Decimal("5.01")
    assert broker.portfolio.cash == Decimal("98994.99")
    position = broker.portfolio.positions["000001.SZ"]
    assert position.quantity == 100
    assert position.available_quantity == 0
    assert position.average_cost == Decimal("10.0501")


def test_paper_settlement_makes_t0_position_available_next_trade_day() -> None:
    broker = PaperBroker(initial_cash=Decimal("100000.00"))
    broker.execute(order(side=Side.BUY, trading_date=date(2026, 7, 29), key="buy-1"))

    broker.settle(date(2026, 7, 30))

    assert broker.portfolio.positions["000001.SZ"].available_quantity == 100


def test_paper_round_trip_uses_net_proceeds_and_removes_closed_position() -> None:
    broker = PaperBroker(initial_cash=Decimal("100000.00"))
    broker.execute(order(side=Side.BUY, trading_date=date(2026, 7, 29), key="buy-1"))
    broker.settle(date(2026, 7, 30))

    fill = broker.execute(
        order(
            side=Side.SELL,
            trading_date=date(2026, 7, 30),
            price=Decimal("11.00"),
            key="sell-1",
        )
    )

    assert fill.fee == Decimal("5.56")
    assert broker.portfolio.cash == Decimal("100089.43")
    assert "000001.SZ" not in broker.portfolio.positions


def test_paper_execute_is_idempotent_for_same_validated_order() -> None:
    broker = PaperBroker(initial_cash=Decimal("100000.00"))
    validated = order(
        side=Side.BUY, trading_date=date(2026, 7, 29), key="buy-duplicate"
    )

    first_fill = broker.execute(validated)
    cash_after_first = broker.portfolio.cash
    second_fill = broker.execute(validated)

    assert second_fill == first_fill
    assert broker.portfolio.cash == cash_after_first
    assert broker.portfolio.positions["000001.SZ"].quantity == 100
