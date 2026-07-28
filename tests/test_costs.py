from decimal import Decimal

from quantagent.costs import ChinaAshareCostModel
from quantagent.domain import Side


def test_shanghai_buy_applies_minimum_commission_and_transfer_fee() -> None:
    costs = ChinaAshareCostModel().calculate(
        symbol="600000.SH",
        side=Side.BUY,
        quantity=1000,
        price=Decimal("10.00"),
    )

    assert costs.commission == Decimal("5.00")
    assert costs.transfer_fee == Decimal("0.10")
    assert costs.stamp_duty == Decimal("0.00")
    assert costs.total == Decimal("5.10")
    assert costs.schedule_version == "eastmoney-2026-07-29"


def test_shenzhen_sell_applies_all_confirmed_fees() -> None:
    costs = ChinaAshareCostModel().calculate(
        symbol="000001.SZ",
        side=Side.SELL,
        quantity=1000,
        price=Decimal("10.00"),
    )

    assert costs.commission == Decimal("5.00")
    assert costs.transfer_fee == Decimal("0.10")
    assert costs.stamp_duty == Decimal("5.00")
    assert costs.total == Decimal("10.10")


def test_commission_uses_market_rate_above_minimum() -> None:
    costs = ChinaAshareCostModel().calculate(
        symbol="600000.SH",
        side=Side.BUY,
        quantity=10000,
        price=Decimal("10.00"),
    )

    assert costs.commission == Decimal("5.41")
