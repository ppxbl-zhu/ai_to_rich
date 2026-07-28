from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import ClassVar

from quantagent.domain import Side


@dataclass(frozen=True, slots=True)
class TransactionCosts:
    schedule_version: str
    commission: Decimal
    transfer_fee: Decimal
    stamp_duty: Decimal
    total: Decimal


class ChinaAshareCostModel:
    _SCHEDULE_VERSION = "eastmoney-2026-07-29"
    _CENT = Decimal("0.01")
    _MINIMUM_COMMISSION = Decimal("5.00")
    _COMMISSION_RATES: ClassVar[dict[str, Decimal]] = {
        "SH": Decimal("0.0000541"),
        "SZ": Decimal("0.0000641"),
    }
    _TRANSFER_RATE = Decimal("0.00001")
    _STAMP_DUTY_RATE = Decimal("0.0005")

    def calculate(
        self, *, symbol: str, side: Side, quantity: int, price: Decimal
    ) -> TransactionCosts:
        market = symbol.rsplit(".", maxsplit=1)[-1]
        turnover = price * quantity
        commission = max(
            turnover * self._COMMISSION_RATES[market], self._MINIMUM_COMMISSION
        ).quantize(self._CENT, rounding=ROUND_HALF_UP)
        transfer_fee = (turnover * self._TRANSFER_RATE).quantize(
            self._CENT, rounding=ROUND_HALF_UP
        )
        stamp_duty = (
            turnover * self._STAMP_DUTY_RATE if side is Side.SELL else Decimal()
        ).quantize(self._CENT, rounding=ROUND_HALF_UP)
        total = commission + transfer_fee + stamp_duty
        return TransactionCosts(
            schedule_version=self._SCHEDULE_VERSION,
            commission=commission,
            transfer_fee=transfer_fee,
            stamp_duty=stamp_duty,
            total=total,
        )
