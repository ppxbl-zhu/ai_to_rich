from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any, Protocol

from quantagent.closing_snapshot import (
    RealtimeStock,
    build_closing_candidates,
)
from quantagent.domain import Board, MarketQuote, SecurityStatus
from quantagent.paper_runtime import PaperSession, build_monitor_session
from quantagent.providers.tushare_swing import QueryClient


class RealtimeProvider(Protocol):
    def fetch(self, captured_at: datetime) -> tuple[RealtimeStock, ...]: ...


def build_closing_session(
    *,
    client: QueryClient,
    realtime: RealtimeProvider,
    now: datetime,
) -> PaperSession:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("closing session time requires a timezone")
    trade_date = now.strftime("%Y%m%d")
    calendar = client.query(
        "trade_cal",
        {"exchange": "SSE", "start_date": trade_date, "end_date": trade_date},
    )
    is_trading_day = bool(calendar and int(calendar[0]["is_open"]) == 1)
    rows = realtime.fetch(now)
    memberships = _memberships(client, as_of=trade_date)
    limit_rows = client.query("stk_limit", {"trade_date": trade_date})
    upper_limits = {
        str(item["ts_code"]): Decimal(str(item["up_limit"]))
        for item in limit_rows
        if item.get("up_limit") is not None
    }
    limits = {
        str(item["ts_code"]): (
            Decimal(str(item["up_limit"])),
            Decimal(str(item["down_limit"])),
        )
        for item in limit_rows
        if item.get("up_limit") is not None and item.get("down_limit") is not None
    }
    suspended = {
        str(item["ts_code"])
        for item in client.query("suspend_d", {"trade_date": trade_date})
    }
    candidates = build_closing_candidates(
        rows,
        memberships=memberships,
        upper_limits=upper_limits,
        suspended_symbols=suspended,
        observed_at=now,
    )
    row_by_symbol = {item.symbol: item for item in rows}
    quotes = tuple(
        _quote(row_by_symbol[item.symbol], limits[item.symbol], now)
        for item in candidates
        if item.symbol in limits
    )
    allowed_symbols = {item.symbol for item in quotes}
    candidates = tuple(item for item in candidates if item.symbol in allowed_symbols)
    monitor = build_monitor_session(
        quotes=quotes,
        trading_date=now.date(),
        captured_at=now,
        is_trading_day=is_trading_day,
    )
    canonical = json.dumps(
        {
            "monitor_dataset_version": monitor.dataset_version,
            "closing_candidates": [asdict(item) for item in candidates],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return replace(
        monitor,
        session_id=f"closing-{now:%Y%m%d-%H%M%S}-{digest[:12]}",
        dataset_version=f"sha256:{digest}",
        closing_candidates=candidates,
    )


def _memberships(client: QueryClient, *, as_of: str) -> dict[str, str]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = client.query(
            "index_member_all",
            {"is_new": "Y", "limit": 3000, "offset": offset},
        )
        rows.extend(page)
        if len(page) < 3000:
            break
        offset += 3000
    effective: dict[str, tuple[str, str]] = {}
    for item in rows:
        symbol = str(item.get("ts_code") or "")
        sector = str(item.get("l1_code") or "")
        in_date = str(item.get("in_date") or "")
        out_date = str(item.get("out_date") or "")
        if (
            not symbol
            or not sector
            or in_date > as_of
            or (out_date and out_date < as_of)
        ):
            continue
        previous = effective.get(symbol)
        if previous is None or in_date > previous[0]:
            effective[symbol] = (in_date, sector)
        elif in_date == previous[0] and sector != previous[1]:
            raise ValueError(f"{symbol} has ambiguous same-date sector membership")
    return {symbol: value[1] for symbol, value in effective.items()}


def _quote(
    row: RealtimeStock,
    limits: tuple[Decimal, Decimal],
    captured_at: datetime,
) -> MarketQuote:
    return MarketQuote(
        symbol=row.symbol,
        name=row.name,
        board=_board(row.symbol),
        market_time=captured_at,
        captured_at=captured_at,
        price=row.price,
        previous_close=row.previous_close,
        limit_up=limits[0],
        limit_down=limits[1],
        status=SecurityStatus.ACTIVE,
        source="eastmoney-web+tushare",
    )


def _board(symbol: str) -> Board:
    code = symbol.split(".", maxsplit=1)[0]
    if code.startswith(("300", "301")):
        return Board.CHINEXT
    if code.startswith(("688", "689")):
        return Board.STAR
    return Board.MAIN
