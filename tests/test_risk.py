from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quantagent.domain import (
    Board,
    MarketQuote,
    OrderIntent,
    Portfolio,
    Position,
    SecurityStatus,
    Side,
    TradePlan,
)
from quantagent.risk import RiskEngine, RiskViolation

CN_TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 14, 50, tzinfo=CN_TZ)


def quote(
    *,
    symbol: str = "000001.SZ",
    board: Board = Board.MAIN,
    status: SecurityStatus = SecurityStatus.ACTIVE,
    captured_at: datetime = NOW,
    name: str = "测试股份",
    market_time: datetime = NOW,
) -> MarketQuote:
    return MarketQuote(
        symbol=symbol,
        name=name,
        board=board,
        market_time=market_time,
        captured_at=captured_at,
        price=Decimal("10.00"),
        previous_close=Decimal("9.80"),
        limit_up=Decimal("10.78"),
        limit_down=Decimal("8.82"),
        status=status,
        source="offline-test",
    )


def intent(
    *,
    symbol: str = "000001.SZ",
    quantity: int = 100,
    side: Side = Side.BUY,
    price: Decimal = Decimal("10.00"),
    key: str = "strategy:000001.SZ:20260729",
) -> OrderIntent:
    return OrderIntent(
        idempotency_key=key,
        created_at=NOW,
        trading_date=date(2026, 7, 29),
        plan=TradePlan(
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=price,
            stop_price=Decimal("9.50"),
            target_price=Decimal("10.80"),
            invalidation="跌破止损",
        ),
    )


def test_risk_accepts_valid_main_board_buy() -> None:
    validated = RiskEngine().validate(
        intent(),
        quote(),
        Portfolio(cash=Decimal("100000.00")),
        now=NOW,
    )

    assert validated.intent.plan.quantity == 100


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (SecurityStatus.SUSPENDED, "not tradable"),
        (SecurityStatus.ST, "not tradable"),
        (SecurityStatus.DELISTING, "not tradable"),
    ],
)
def test_risk_rejects_non_tradable_security(
    status: SecurityStatus, reason: str
) -> None:
    with pytest.raises(RiskViolation, match=reason):
        RiskEngine().validate(
            intent(), quote(status=status), Portfolio(cash=Decimal("100000")), now=NOW
        )


def test_risk_rejects_stale_quote() -> None:
    with pytest.raises(RiskViolation, match="stale"):
        RiskEngine(max_quote_age=timedelta(seconds=30)).validate(
            intent(),
            quote(captured_at=NOW - timedelta(seconds=31)),
            Portfolio(cash=Decimal("100000")),
            now=NOW,
        )


def test_risk_rejects_quote_without_security_name() -> None:
    with pytest.raises(RiskViolation, match="name"):
        RiskEngine().validate(
            intent(),
            quote(name=""),
            Portfolio(cash=Decimal("100000")),
            now=NOW,
        )


def test_risk_rejects_market_data_from_different_trading_date() -> None:
    with pytest.raises(RiskViolation, match="trading date"):
        RiskEngine().validate(
            intent(),
            quote(market_time=NOW - timedelta(days=1)),
            Portfolio(cash=Decimal("100000")),
            now=NOW,
        )


def test_risk_enforces_board_lot_rules() -> None:
    engine = RiskEngine()

    with pytest.raises(RiskViolation, match="100"):
        engine.validate(
            intent(quantity=150),
            quote(),
            Portfolio(cash=Decimal("100000")),
            now=NOW,
        )

    validated = engine.validate(
        intent(symbol="688001.SH", quantity=201),
        quote(symbol="688001.SH", board=Board.STAR),
        Portfolio(cash=Decimal("100000")),
        now=NOW,
    )
    assert validated.intent.plan.quantity == 201


def test_risk_rejects_price_outside_daily_limit() -> None:
    with pytest.raises(RiskViolation, match="price limit"):
        RiskEngine().validate(
            intent(price=Decimal("10.79")),
            quote(),
            Portfolio(cash=Decimal("100000")),
            now=NOW,
        )


def test_risk_rejects_duplicate_order_key() -> None:
    engine = RiskEngine()
    portfolio = Portfolio(cash=Decimal("100000"))
    engine.validate(intent(), quote(), portfolio, now=NOW)

    with pytest.raises(RiskViolation, match="duplicate"):
        engine.validate(intent(), quote(), portfolio, now=NOW)


def test_risk_rejects_sell_of_t0_position() -> None:
    portfolio = Portfolio(
        cash=Decimal("90000"),
        positions={
            "000001.SZ": Position(
                symbol="000001.SZ",
                quantity=100,
                available_quantity=0,
                average_cost=Decimal("10.00"),
                acquired_on=date(2026, 7, 29),
            )
        },
    )

    with pytest.raises(RiskViolation, match="T\\+1"):
        RiskEngine().validate(
            intent(side=Side.SELL),
            quote(),
            portfolio,
            now=NOW,
        )


def test_risk_kill_switch_rejects_all_new_orders() -> None:
    engine = RiskEngine()
    engine.activate_kill_switch("manual stop")

    with pytest.raises(RiskViolation, match="kill switch"):
        engine.validate(intent(), quote(), Portfolio(cash=Decimal("100000")), now=NOW)
