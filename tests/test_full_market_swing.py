from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from quantagent.closing_snapshot import RealtimeStock
from quantagent.providers.full_market_swing import (
    FullMarketSwingScanner,
    build_full_market_swing_session,
)

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 10, 30, tzinfo=CST)


def daily_rows() -> dict[str, tuple[dict[str, Any], ...]]:
    result: dict[str, list[dict[str, Any]]] = {
        "000001.SZ": [],
        "300207.SZ": [],
    }
    previous = {"000001.SZ": Decimal("10"), "300207.SZ": Decimal("20")}
    for offset in range(70):
        trading_date = date(2026, 4, 1) + timedelta(days=offset)
        for symbol, step in (
            ("000001.SZ", Decimal("0.02")),
            ("300207.SZ", Decimal("0.40")),
        ):
            close = previous[symbol] + step
            result[symbol].append(
                {
                    "ts_code": symbol,
                    "trade_date": trading_date.strftime("%Y%m%d"),
                    "high": close + Decimal("0.30"),
                    "low": close - Decimal("0.30"),
                    "close": close,
                    "pre_close": previous[symbol],
                }
            )
            previous[symbol] = close
    return {symbol: tuple(rows) for symbol, rows in result.items()}


class FakeTushare:
    def __init__(self) -> None:
        self.rows = daily_rows()

    def query(
        self, api_name: str, params: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        if api_name == "trade_cal":
            dates = sorted(
                {row["trade_date"] for rows in self.rows.values() for row in rows},
                reverse=True,
            )
            return tuple({"cal_date": value, "is_open": 1} for value in dates)
        if api_name == "daily":
            return tuple(
                row
                for rows in self.rows.values()
                for row in rows
                if row["trade_date"] == params["trade_date"]
            )
        if api_name == "stock_basic":
            return tuple(
                {"ts_code": symbol, "name": symbol, "list_status": "L"}
                for symbol in self.rows
            )
        if api_name == "index_member_all":
            if params.get("offset", 0):
                return ()
            return tuple(
                {
                    "ts_code": symbol,
                    "l1_code": "801730.SI",
                    "in_date": "20200101",
                    "out_date": None,
                }
                for symbol in self.rows
            )
        if api_name == "index_daily":
            rows = []
            previous = Decimal("100")
            for offset in range(70):
                close = previous + Decimal("0.10")
                rows.append(
                    {
                        "trade_date": (
                            date(2026, 4, 1) + timedelta(days=offset)
                        ).strftime("%Y%m%d"),
                        "high": close + 1,
                        "low": close - 1,
                        "close": close,
                        "pre_close": previous,
                    }
                )
                previous = close
            if params["ts_code"] == "801730.SI":
                for row in rows:
                    row["close"] += Decimal("0.30")
            return tuple(reversed(rows))
        if api_name == "fina_indicator_vip":
            return tuple(
                {
                    "ts_code": symbol,
                    "ann_date": "20260720",
                    "roe": Decimal("15"),
                    "debt_to_assets": Decimal("40"),
                }
                for symbol in self.rows
            )
        if api_name == "cashflow_vip":
            return tuple(
                {
                    "ts_code": symbol,
                    "ann_date": "20260720",
                    "n_cashflow_act": 100,
                }
                for symbol in self.rows
            )
        if api_name == "stk_limit":
            return tuple(
                {
                    "ts_code": symbol,
                    "up_limit": Decimal("100"),
                    "down_limit": Decimal("1"),
                }
                for symbol in self.rows
            )
        if api_name == "suspend_d":
            return ()
        raise AssertionError((api_name, params))


class FakeRealtime:
    def fetch(self, captured_at: datetime) -> tuple[RealtimeStock, ...]:
        return tuple(
            RealtimeStock(
                symbol=symbol,
                name=symbol,
                price=price,
                pct_change_percent=Decimal("2"),
                volume_hands=Decimal("1000"),
                amount=Decimal("1000000"),
                high=price + 1,
                low=price - 1,
                open=price - Decimal("0.5"),
                previous_close=price - Decimal("0.2"),
                volume_ratio=Decimal("1.5"),
                captured_at=captured_at,
            )
            for symbol, price in (
                ("000001.SZ", Decimal("11.4")),
                ("300207.SZ", Decimal("48.5")),
            )
        )


def test_full_market_scan_selects_symbol_without_watchlist_input() -> None:
    scanner = FullMarketSwingScanner(client=FakeTushare(), shortlist_size=10)

    snapshot = scanner.scan(as_of=NOW)
    session = build_full_market_swing_session(
        snapshot=snapshot,
        client=scanner.client,
        realtime=FakeRealtime(),
        now=NOW,
    )

    assert "300207.SZ" in session.quotes
    assert "300207.SZ" in {candidate.symbol for candidate in session.swing_candidates}


def test_full_market_scan_fails_closed_on_insufficient_history() -> None:
    client = FakeTushare()
    client.rows = {symbol: rows[:20] for symbol, rows in client.rows.items()}

    with pytest.raises(ValueError, match="60 completed trading days"):
        FullMarketSwingScanner(client=client).scan(as_of=NOW)
