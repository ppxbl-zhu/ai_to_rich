from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from quantagent.backtest import (
    BacktestBar,
    BacktestEngine,
    BacktestOrder,
    BacktestStatus,
)
from quantagent.domain import Side

CN_TZ = timezone(timedelta(hours=8))


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=CN_TZ)


def bar(
    day: int,
    *,
    open_price: str,
    close: str,
    suspended: bool = False,
    limit_up: str = "99.00",
    limit_down: str = "0.01",
) -> BacktestBar:
    return BacktestBar(
        symbol="000001.SZ",
        trading_date=date(2026, 7, day),
        opened_at=at(day, 9, 30),
        closed_at=at(day, 15),
        open=Decimal(open_price),
        high=max(Decimal(open_price), Decimal(close)),
        low=min(Decimal(open_price), Decimal(close)),
        close=Decimal(close),
        volume=1000000,
        suspended=suspended,
        limit_up=Decimal(limit_up),
        limit_down=Decimal(limit_down),
    )


def order(day: int, side: Side, *, key: str) -> BacktestOrder:
    return BacktestOrder(
        idempotency_key=key,
        symbol="000001.SZ",
        side=side,
        quantity=100,
        generated_at=at(day, 15),
    )


def test_close_signal_executes_on_next_bar_with_slippage_and_costs() -> None:
    result = BacktestEngine(slippage_bps=Decimal("10")).run(
        bars=[
            bar(1, open_price="10.00", close="10.00"),
            bar(2, open_price="10.20", close="10.30"),
        ],
        orders=[order(1, Side.BUY, key="buy-1")],
        dataset_version="sha256:data",
        config_version="baseline-v1",
        random_seed=7,
    )

    assert len(result.fills) == 1
    assert result.fills[0].trading_date == date(2026, 7, 2)
    assert result.fills[0].price == Decimal("10.2102")
    assert result.fills[0].fee == Decimal("5.01")
    assert result.report.trade_count == 1
    assert result.report.dataset_version == "sha256:data"
    assert result.report.random_seed == 7


def test_backtest_enforces_t1_and_round_trip_net_cash() -> None:
    result = BacktestEngine().run(
        bars=[
            bar(1, open_price="10.00", close="10.00"),
            bar(2, open_price="10.00", close="10.50"),
            bar(3, open_price="11.00", close="11.00"),
        ],
        orders=[
            order(1, Side.BUY, key="buy-1"),
            order(2, Side.SELL, key="sell-1"),
        ],
        dataset_version="sha256:data",
        config_version="baseline-v1",
        random_seed=7,
    )

    assert [fill.trading_date for fill in result.fills] == [
        date(2026, 7, 2),
        date(2026, 7, 3),
    ]
    assert result.report.final_equity == Decimal("100089.43")


def test_backtest_records_unfilled_suspended_and_limit_up_orders() -> None:
    result = BacktestEngine().run(
        bars=[
            bar(1, open_price="10.00", close="10.00"),
            bar(2, open_price="10.78", close="10.78", limit_up="10.78"),
            bar(3, open_price="10.70", close="10.70", suspended=True),
        ],
        orders=[
            order(1, Side.BUY, key="limit-up"),
            order(2, Side.BUY, key="suspended"),
        ],
        dataset_version="sha256:data",
        config_version="baseline-v1",
        random_seed=7,
    )

    assert result.fills == ()
    assert [(item.key, item.status) for item in result.orders] == [
        ("limit-up", BacktestStatus.UNFILLED_LIMIT),
        ("suspended", BacktestStatus.UNFILLED_SUSPENDED),
    ]


def test_backtest_does_not_execute_signal_without_a_future_bar() -> None:
    result = BacktestEngine().run(
        bars=[bar(1, open_price="10.00", close="10.00")],
        orders=[order(1, Side.BUY, key="no-future")],
        dataset_version="sha256:data",
        config_version="baseline-v1",
        random_seed=7,
    )

    assert result.fills == ()
    assert result.orders[0].status is BacktestStatus.NO_FUTURE_BAR
