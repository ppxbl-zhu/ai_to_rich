from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Any

from quantagent.paper_runtime import PaperSession, build_monitor_session
from quantagent.providers.closing_session import (
    RealtimeProvider,
    _memberships,
    _quote,
)
from quantagent.providers.tushare_swing import (
    QueryClient,
    _bars,
    _financials,
)
from quantagent.swing import SwingCandidate
from quantagent.swing_factors import DailyFactorBar, derive_swing_candidate


@dataclass(frozen=True, slots=True)
class FullMarketSwingSnapshot:
    as_of: datetime
    benchmark_code: str
    candidates: tuple[SwingCandidate, ...]
    scanned_symbols: int
    completed_trading_days: int


class FullMarketSwingScanner:
    def __init__(
        self,
        *,
        client: QueryClient,
        shortlist_size: int = 100,
        benchmark_code: str = "000001.SH",
    ) -> None:
        if shortlist_size <= 0:
            raise ValueError("shortlist size must be positive")
        self.client = client
        self.shortlist_size = shortlist_size
        self.benchmark_code = benchmark_code

    def scan(self, *, as_of: datetime) -> FullMarketSwingSnapshot:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("full-market scan time requires a timezone")
        end_date = as_of.strftime("%Y%m%d")
        start_date = (as_of.date() - timedelta(days=180)).strftime("%Y%m%d")
        calendar = self.client.query(
            "trade_cal",
            {
                "exchange": "SSE",
                "start_date": start_date,
                "end_date": end_date,
                "is_open": "1",
            },
        )
        trade_dates = sorted(
            {
                str(row["cal_date"])
                for row in calendar
                if int(row.get("is_open", 0)) == 1 and str(row["cal_date"]) <= end_date
            }
        )[-70:]
        if len(trade_dates) < 60:
            raise ValueError(
                "full-market scan requires at least 60 completed trading days"
            )

        active = {
            str(row["ts_code"]): str(row.get("name") or "")
            for row in self.client.query(
                "stock_basic",
                {"exchange": "", "list_status": "L"},
            )
            if row.get("ts_code") and not _excluded_name(str(row.get("name") or ""))
        }
        histories: dict[str, list[dict[str, Any]]] = {}
        for trade_date in trade_dates:
            for row in self.client.query("daily", {"trade_date": trade_date}):
                symbol = str(row.get("ts_code") or "")
                if symbol in active:
                    histories.setdefault(symbol, []).append(row)
        bars_by_symbol = {
            symbol: _bars(tuple(rows))
            for symbol, rows in histories.items()
            if len(rows) >= 60
        }
        if not bars_by_symbol:
            raise ValueError("full-market daily history is empty")

        query_dates = {"start_date": start_date, "end_date": end_date}
        benchmark = _bars(
            self.client.query(
                "index_daily",
                {"ts_code": self.benchmark_code, **query_dates},
            )
        )
        if len(benchmark) < 60:
            raise ValueError("benchmark history is incomplete")
        ranked = sorted(
            (
                (_technical_score(bars, benchmark), symbol)
                for symbol, bars in bars_by_symbol.items()
                if _technical_prefilter(bars, benchmark)
            ),
            reverse=True,
        )[: self.shortlist_size]
        memberships = _memberships(self.client, as_of=end_date)
        indicator_by_symbol = _bulk_financial_rows(
            self.client,
            "fina_indicator_vip",
            as_of=as_of,
        )
        cashflow_by_symbol = _bulk_financial_rows(
            self.client,
            "cashflow_vip",
            as_of=as_of,
        )
        candidates = []
        sector_cache: dict[str, tuple[DailyFactorBar, ...]] = {}
        for _, symbol in ranked:
            sector_code = memberships.get(symbol)
            if sector_code is None:
                continue
            if sector_code not in sector_cache:
                sector_cache[sector_code] = _bars(
                    self.client.query(
                        "index_daily",
                        {"ts_code": sector_code, **query_dates},
                    )
                )
            financials = _financials(
                indicator_by_symbol.get(symbol, ()),
                cashflow_by_symbol.get(symbol, ()),
                decision_time=as_of,
            )
            stock_bars = bars_by_symbol[symbol]
            candidates.append(
                derive_swing_candidate(
                    symbol=symbol,
                    price=stock_bars[-1].close,
                    stock_bars=stock_bars,
                    benchmark_bars=benchmark,
                    sector_bars=sector_cache[sector_code],
                    financials=financials,
                )
            )
        if not candidates:
            raise ValueError("full-market scan produced no complete swing candidates")
        return FullMarketSwingSnapshot(
            as_of=as_of,
            benchmark_code=self.benchmark_code,
            candidates=tuple(candidates),
            scanned_symbols=len(bars_by_symbol),
            completed_trading_days=len(trade_dates),
        )


def build_full_market_swing_session(
    *,
    snapshot: FullMarketSwingSnapshot,
    client: QueryClient,
    realtime: RealtimeProvider,
    now: datetime,
) -> PaperSession:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("full-market monitor time requires a timezone")
    if snapshot.as_of.date() != now.date():
        raise ValueError("swing snapshot is not from the current trading day")
    trade_date = now.strftime("%Y%m%d")
    rows = realtime.fetch(now)
    limits = {
        str(row["ts_code"]): (
            Decimal(str(row["up_limit"])),
            Decimal(str(row["down_limit"])),
        )
        for row in client.query("stk_limit", {"trade_date": trade_date})
        if row.get("up_limit") is not None and row.get("down_limit") is not None
    }
    suspended = {
        str(row["ts_code"])
        for row in client.query("suspend_d", {"trade_date": trade_date})
    }
    quotes = tuple(
        _quote(row, limits[row.symbol], now)
        for row in rows
        if row.symbol in limits and row.symbol not in suspended
    )
    monitor = build_monitor_session(
        quotes=quotes,
        trading_date=now.date(),
        captured_at=now,
        is_trading_day=True,
    )
    prices = {row.symbol: row.price for row in rows}
    candidates = tuple(
        replace(candidate, price=prices[candidate.symbol])
        for candidate in snapshot.candidates
        if candidate.symbol in prices and candidate.symbol in monitor.quotes
    )
    if not candidates:
        raise ValueError("no scanned swing candidate has a valid realtime quote")
    canonical = json.dumps(
        {
            "monitor_dataset_version": monitor.dataset_version,
            "scan": {
                **asdict(snapshot),
                "candidates": [asdict(item) for item in snapshot.candidates],
            },
            "candidates": [asdict(item) for item in candidates],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return replace(
        monitor,
        session_id=f"swing-full-{now:%Y%m%d-%H%M%S}-{digest[:12]}",
        dataset_version=f"sha256:{digest}",
        swing_candidates=candidates,
    )


def _technical_prefilter(
    bars: tuple[DailyFactorBar, ...],
    benchmark: tuple[DailyFactorBar, ...],
) -> bool:
    if len(bars) < 60 or len(benchmark) < 60:
        return False
    ma20 = sum((bar.close for bar in bars[-20:]), Decimal()) / Decimal(20)
    ma60 = sum((bar.close for bar in bars[-60:]), Decimal()) / Decimal(60)
    return bars[-1].close > ma20 > ma60 and _technical_score(bars, benchmark) > 0


def _technical_score(
    bars: tuple[DailyFactorBar, ...],
    benchmark: tuple[DailyFactorBar, ...],
) -> Decimal:
    stock_return = bars[-1].close / bars[-60].previous_close - Decimal(1)
    benchmark_return = benchmark[-1].close / benchmark[-60].previous_close - Decimal(1)
    return stock_return - benchmark_return


def _excluded_name(name: str) -> bool:
    normalized = name.strip().upper()
    return normalized.startswith(("ST", "*ST", "S*ST")) or "退" in normalized


def _bulk_financial_rows(
    client: QueryClient,
    api_name: str,
    *,
    as_of: datetime,
) -> dict[str, tuple[dict[str, Any], ...]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    year = as_of.year
    periods = [
        f"{year - 1}1231",
        f"{year}0331",
        f"{year}0630",
        f"{year}0930",
    ]
    for period in periods:
        if period > as_of.strftime("%Y%m%d"):
            continue
        offset = 0
        while True:
            page = client.query(
                api_name,
                {"period": period, "limit": 5000, "offset": offset},
            )
            for row in page:
                symbol = str(row.get("ts_code") or "")
                if symbol:
                    rows.setdefault(symbol, []).append(row)
            if len(page) < 5000:
                break
            offset += 5000
    return {symbol: tuple(items) for symbol, items in rows.items()}
