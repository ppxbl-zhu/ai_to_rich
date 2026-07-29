from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Any, Protocol

from quantagent.paper_runtime import PaperSession
from quantagent.swing_factors import (
    DailyFactorBar,
    FinancialFactors,
    derive_swing_candidate,
)


class QueryClient(Protocol):
    def query(
        self, api_name: str, params: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]: ...


def enrich_monitor_with_swing(
    *,
    client: QueryClient,
    monitor: PaperSession,
    decision_time: datetime,
    benchmark_code: str = "000001.SH",
) -> PaperSession:
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("decision time requires a timezone")
    if decision_time.date() != monitor.trading_date:
        raise ValueError("decision and monitor trading dates differ")

    query_dates = {
        "start_date": (monitor.trading_date - timedelta(days=180)).strftime("%Y%m%d"),
        "end_date": monitor.trading_date.strftime("%Y%m%d"),
    }
    benchmark = _bars(
        client.query("index_daily", {"ts_code": benchmark_code, **query_dates})
    )
    candidates = []
    for symbol, quote in sorted(monitor.quotes.items()):
        stock = _bars(client.query("daily", {"ts_code": symbol, **query_dates}))
        membership = client.query(
            "index_member_all",
            {"ts_code": symbol, "is_new": "Y"},
        )
        sector_code = _sector_code(
            membership,
            symbol,
            as_of=monitor.trading_date.strftime("%Y%m%d"),
        )
        sector = _bars(
            client.query("index_daily", {"ts_code": sector_code, **query_dates})
        )
        financials = _financials(
            client.query(
                "fina_indicator_vip",
                {"ts_code": symbol, "end_date": query_dates["end_date"]},
            ),
            client.query(
                "cashflow_vip",
                {"ts_code": symbol, "end_date": query_dates["end_date"]},
            ),
            decision_time=decision_time,
        )
        candidates.append(
            derive_swing_candidate(
                symbol=symbol,
                price=quote.price,
                stock_bars=stock,
                benchmark_bars=benchmark,
                sector_bars=sector,
                financials=financials,
            )
        )

    payload = {
        "monitor_dataset_version": monitor.dataset_version,
        "decision_time": decision_time.isoformat(),
        "benchmark_code": benchmark_code,
        "swing_candidates": [asdict(item) for item in candidates],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return replace(
        monitor,
        session_id=(
            f"swing-{monitor.trading_date:%Y%m%d}-{decision_time:%H%M%S}-{digest[:12]}"
        ),
        captured_at=decision_time,
        dataset_version=f"sha256:{digest}",
        swing_candidates=tuple(candidates),
        closing_candidates=(),
    )


def _bars(rows: tuple[dict[str, Any], ...]) -> tuple[DailyFactorBar, ...]:
    result = [
        DailyFactorBar(
            trading_date=datetime.strptime(str(row["trade_date"]), "%Y%m%d").date(),
            high=_decimal(row["high"]),
            low=_decimal(row["low"]),
            close=_decimal(row["close"]),
            previous_close=_decimal(row["pre_close"]),
        )
        for row in rows
    ]
    return tuple(sorted(result, key=lambda item: item.trading_date))


def _sector_code(
    rows: tuple[dict[str, Any], ...],
    symbol: str,
    *,
    as_of: str,
) -> str:
    effective = [
        row
        for row in rows
        if row.get("l1_code")
        and str(row.get("in_date") or "") <= as_of
        and (not row.get("out_date") or str(row["out_date"]) >= as_of)
    ]
    if not effective:
        raise ValueError(f"{symbol} has no effective level-one sector")
    latest_date = max(str(row.get("in_date") or "") for row in effective)
    current = {
        str(row["l1_code"])
        for row in effective
        if str(row.get("in_date") or "") == latest_date
    }
    if len(current) != 1:
        raise ValueError(f"{symbol} requires one current level-one sector")
    return current.pop()


def _financials(
    indicator_rows: tuple[dict[str, Any], ...],
    cashflow_rows: tuple[dict[str, Any], ...],
    *,
    decision_time: datetime,
) -> FinancialFactors:
    cutoff = decision_time.strftime("%Y%m%d")
    indicators = [
        row
        for row in indicator_rows
        if str(row.get("ann_date") or "") <= cutoff
        and row.get("roe") is not None
        and row.get("debt_to_assets") is not None
    ]
    cashflows = [
        row
        for row in cashflow_rows
        if str(row.get("ann_date") or "") <= cutoff
        and row.get("n_cashflow_act") is not None
    ]
    if not indicators or not cashflows:
        raise ValueError("point-in-time financial factors are incomplete")
    indicator = max(indicators, key=lambda row: str(row["ann_date"]))
    cashflow = max(cashflows, key=lambda row: str(row["ann_date"]))
    return FinancialFactors(
        roe_percent=_decimal(indicator["roe"]),
        debt_to_assets_percent=_decimal(indicator["debt_to_assets"]),
        operating_cashflow=_decimal(cashflow["n_cashflow_act"]),
    )


def _decimal(value: Any) -> Decimal:
    if value is None:
        raise ValueError("numeric factor is missing")
    return Decimal(str(value))
