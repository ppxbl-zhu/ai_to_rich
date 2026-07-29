from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from quantagent.paper_runtime import PaperSession
from quantagent.paper_runtime import build_monitor_session as build_session
from quantagent.providers.eastmoney_ocr import (
    OcrFrame,
    parse_watchlist,
    reconcile_previous_closes,
    to_market_quotes,
)


class QueryClient(Protocol):
    def query(
        self, api_name: str, params: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]: ...


class FrameSource(Protocol):
    def capture(self, process_id: int) -> OcrFrame: ...


def build_monitor_session(
    *,
    client: QueryClient,
    frame_source: FrameSource,
    process_id: int,
    now: datetime,
) -> PaperSession:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("monitor runtime requires a timezone")
    trading_date = now.date()
    calendar = client.query(
        "trade_cal",
        {
            "exchange": "SSE",
            "start_date": (trading_date - timedelta(days=10)).strftime("%Y%m%d"),
            "end_date": trading_date.strftime("%Y%m%d"),
        },
    )
    open_dates = sorted(
        datetime.strptime(str(row["cal_date"]), "%Y%m%d").date()
        for row in calendar
        if int(row["is_open"]) == 1
    )
    if trading_date not in open_dates:
        raise ValueError("current date is not an exchange trading day")
    previous_dates = [item for item in open_dates if item < trading_date]
    if not previous_dates:
        raise ValueError("previous trading date is unavailable")
    previous_date = previous_dates[-1]

    frame = frame_source.capture(process_id)
    ocr_quotes = parse_watchlist(frame.words, captured_at=frame.captured_at)
    symbols = {quote.symbol for quote in ocr_quotes}
    previous_rows = client.query(
        "daily", {"trade_date": previous_date.strftime("%Y%m%d")}
    )
    previous_closes = {
        str(row["ts_code"]): Decimal(str(row["close"]))
        for row in previous_rows
        if str(row["ts_code"]) in symbols
    }
    verified = reconcile_previous_closes(ocr_quotes, previous_closes)
    limit_rows = client.query(
        "stk_limit", {"trade_date": trading_date.strftime("%Y%m%d")}
    )
    price_limits = {
        str(row["ts_code"]): (
            Decimal(str(row["up_limit"])),
            Decimal(str(row["down_limit"])),
        )
        for row in limit_rows
        if str(row["ts_code"]) in symbols
    }
    suspension_rows = client.query(
        "suspend_d", {"trade_date": trading_date.strftime("%Y%m%d")}
    )
    suspended_symbols = {
        str(row["ts_code"]) for row in suspension_rows if str(row["ts_code"]) in symbols
    }
    market_quotes = to_market_quotes(
        verified,
        previous_closes=previous_closes,
        price_limits=price_limits,
        suspended_symbols=suspended_symbols,
    )
    return build_session(
        quotes=market_quotes,
        trading_date=trading_date,
        captured_at=frame.captured_at,
        is_trading_day=True,
    )
