from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from quantagent.closing_snapshot import RealtimeStock
from quantagent.providers.closing_session import build_closing_session

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 14, 50, tzinfo=CST)


class FakeRealtime:
    def fetch(self, captured_at: datetime) -> tuple[RealtimeStock, ...]:
        return tuple(
            RealtimeStock(
                symbol=symbol,
                name=f"测试{symbol}",
                price=Decimal("10"),
                pct_change_percent=Decimal(str(pct)),
                volume_hands=Decimal("120000"),
                amount=Decimal("120000000"),
                high=Decimal("10"),
                low=Decimal("8"),
                open=Decimal("8.5"),
                previous_close=Decimal("9"),
                volume_ratio=Decimal("1.8"),
                captured_at=captured_at,
            )
            for symbol, pct in (
                ("300001.SZ", 8),
                ("300002.SZ", 6),
                ("300003.SZ", -1),
                ("600001.SH", 0),
                ("600002.SH", 0),
            )
        )


class FakeTushare:
    def query(
        self, api_name: str, params: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        symbols = (
            "300001.SZ",
            "300002.SZ",
            "300003.SZ",
            "600001.SH",
            "600002.SH",
        )
        if api_name == "trade_cal":
            return ({"cal_date": "20260730", "is_open": 1},)
        if api_name == "index_member_all":
            if params.get("offset"):
                return ()
            return tuple(
                {
                    "ts_code": symbol,
                    "l1_code": ("801730.SI" if symbol.startswith("3") else "801780.SI"),
                    "in_date": "20200101",
                    "out_date": None,
                    "is_new": "Y",
                }
                for symbol in symbols
            )
        if api_name == "stk_limit":
            return tuple(
                {
                    "ts_code": symbol,
                    "up_limit": 12,
                    "down_limit": 8,
                }
                for symbol in symbols
            )
        if api_name == "suspend_d":
            return ()
        raise AssertionError((api_name, params))


def test_builds_full_market_closing_paper_session_with_risk_quotes() -> None:
    session = build_closing_session(
        client=FakeTushare(),
        realtime=FakeRealtime(),
        now=NOW,
    )

    assert session.is_trading_day is True
    assert len(session.quotes) == 5
    assert len(session.closing_candidates) == 5
    assert session.swing_candidates == ()
    assert session.quotes["300001.SZ"].limit_up == Decimal("12")
    assert session.session_id.startswith("closing-20260730-145000-")
