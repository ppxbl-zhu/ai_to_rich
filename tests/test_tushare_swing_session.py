from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from quantagent.domain import Board, MarketQuote, SecurityStatus
from quantagent.paper_runtime import build_monitor_session
from quantagent.providers.tushare_swing import enrich_monitor_with_swing

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 10, 30, tzinfo=CST)


def market_quote() -> MarketQuote:
    return MarketQuote(
        symbol="300207.SZ",
        name="欣旺达",
        board=Board.CHINEXT,
        market_time=NOW,
        captured_at=NOW,
        price=Decimal("80"),
        previous_close=Decimal("79"),
        limit_up=Decimal("94.80"),
        limit_down=Decimal("63.20"),
        status=SecurityStatus.ACTIVE,
        source="eastmoney-ocr+tushare",
    )


def api_bars(start: str, step: str) -> tuple[dict[str, Any], ...]:
    first = Decimal(start)
    increment = Decimal(step)
    rows = []
    previous = first - increment
    for offset in range(70):
        close = first + increment * offset
        rows.append(
            {
                "trade_date": (date(2026, 4, 1) + timedelta(days=offset)).strftime(
                    "%Y%m%d"
                ),
                "high": float(close + 1),
                "low": float(close - 1),
                "close": float(close),
                "pre_close": float(previous),
            }
        )
        previous = close
    return tuple(reversed(rows))


class FakeTushare:
    def query(
        self, api_name: str, params: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        if api_name == "daily":
            return api_bars("10", "1")
        if api_name == "index_member_all":
            return (
                {
                    "l1_code": "801010.SI",
                    "l1_name": "农林牧渔",
                    "ts_code": "300207.SZ",
                    "in_date": "20240730",
                    "out_date": None,
                    "is_new": "Y",
                },
                {
                    "l1_code": "801730.SI",
                    "l1_name": "电力设备",
                    "ts_code": "300207.SZ",
                    "in_date": "20260701",
                    "out_date": None,
                    "is_new": "Y",
                },
            )
        if api_name == "index_daily" and params["ts_code"] == "801730.SI":
            return api_bars("50", "0.75")
        if api_name == "index_daily":
            return api_bars("100", "0.5")
        if api_name == "fina_indicator_vip":
            return (
                {
                    "ann_date": "20260720",
                    "roe": 14.2,
                    "debt_to_assets": 45.6,
                },
            )
        if api_name == "cashflow_vip":
            return ({"ann_date": "20260718", "n_cashflow_act": 100},)
        raise AssertionError((api_name, params))


def test_enriches_verified_monitor_session_without_inventing_closing_factors() -> None:
    monitor = build_monitor_session(
        quotes=(market_quote(),),
        trading_date=NOW.date(),
        captured_at=NOW,
        is_trading_day=True,
    )

    enriched = enrich_monitor_with_swing(
        client=FakeTushare(),
        monitor=monitor,
        decision_time=NOW,
    )

    assert tuple(enriched.quotes) == ("300207.SZ",)
    assert len(enriched.swing_candidates) == 1
    assert enriched.swing_candidates[0].symbol == "300207.SZ"
    assert enriched.swing_candidates[0].roe == Decimal("0.142")
    assert enriched.closing_candidates == ()
    assert enriched.session_id.startswith("swing-20260729-103000-")
