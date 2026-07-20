from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timedelta
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .engine import Bar
from .tushare_client import TushareClient, from_ts_code
from .universe import build_liquid_universe


TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="


def _secid(symbol: str) -> str:
    symbol = symbol.strip()
    if len(symbol) != 6 or not symbol.isdigit():
        raise ValueError(f"无效的A股代码：{symbol}")
    return f"1.{symbol}" if symbol.startswith(("5", "6", "9")) else f"0.{symbol}"


def market_symbol(symbol: str) -> str:
    return ("sh" if _secid(symbol).startswith("1.") else "sz") + symbol


def is_st_name(name: str) -> bool:
    return "ST" in name.upper().replace(" ", "")


def fetch_names(symbols: list[str], timeout: float = 10) -> dict[str, str]:
    request = Request(TENCENT_QUOTE_URL + ",".join(market_symbol(symbol) for symbol in symbols), headers={"User-Agent": "Mozilla/5.0 quantlab/0.2"})
    with urlopen(request, timeout=timeout) as response:
        text = response.read().decode("gbk")
    names = {}
    for line in text.splitlines():
        fields = line.split('="', 1)[-1].rstrip('";').split("~")
        if len(fields) > 2:
            names[fields[2]] = fields[1].strip()
    return names


def fetch_instrument(symbol: str, limit: int = 500, timeout: float = 20, retries: int = 3) -> tuple[str, list[Bar]]:
    """Fetch forward-adjusted daily bars from Tencent's public quote endpoint."""
    provider_symbol = market_symbol(symbol)
    query = urlencode({"param": f"{provider_symbol},day,,,{limit},qfq"})
    request = Request(f"{TENCENT_KLINE_URL}?{query}", headers={"User-Agent": "Mozilla/5.0 quantlab/0.2"})
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            break
        except (OSError, ValueError):
            if attempt + 1 == retries:
                raise
            time.sleep(0.5 * (attempt + 1))
    data = (payload.get("data") or {}).get(provider_symbol) or {}
    lines = data.get("qfqday") or data.get("day") or []
    if not lines:
        raise RuntimeError(f"行情接口未返回 {symbol} 的日线数据")
    bars = []
    for fields in lines:
        # Tencent order: date, open, close, high, low, volume.
        bars.append(Bar(fields[0], symbol, float(fields[1]), float(fields[3]), float(fields[4]), float(fields[2]), float(fields[5])))
    return symbol, bars


def fetch_eastmoney(symbol: str, limit: int = 500, timeout: float = 20) -> list[Bar]:
    """Compatibility wrapper returning only unadjusted daily bars."""
    return fetch_instrument(symbol, limit, timeout)[1]


def update_market_csv(symbols: list[str], path: Path, limit: int = 500) -> Path:
    if not symbols:
        raise ValueError("watchlist 不能为空")
    names = fetch_names(symbols)
    allowed_symbols = [symbol for symbol in symbols if names.get(symbol) and not is_st_name(names[symbol])]
    instruments = [(names[symbol], fetch_instrument(symbol, limit=limit)[1]) for symbol in allowed_symbols]
    allowed = [(name, bars) for name, bars in instruments if not is_st_name(name)]
    if not allowed:
        raise ValueError("自选股全部属于ST股票，已停止更新")
    rows = [(name, bar) for name, bars in allowed for bar in bars]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*asdict(rows[0][1]), "name"])
        writer.writeheader()
        writer.writerows({**asdict(bar), "name": name} for name, bar in rows)
    temporary.replace(path)
    return path


def update_tushare_market_csv(client: TushareClient, path: Path, universe_size: int = 100, history_days: int = 500, minimum_listing_days: int = 120) -> tuple[Path, dict]:
    trade_date = client.latest_open_date()
    universe = build_liquid_universe(client, trade_date, universe_size, minimum_listing_days)
    if not universe:
        raise RuntimeError("Tushare没有返回合规股票池")
    start_date = (datetime.strptime(trade_date, "%Y%m%d") - timedelta(days=max(730, history_days * 2))).strftime("%Y%m%d")
    names = {row["ts_code"]: row["name"] for row in universe}
    daily_rows, factor_rows = [], []
    codes = list(names)
    for offset in range(0, len(codes), 10):
        batch = ",".join(codes[offset:offset + 10])
        daily_rows.extend(client.query("daily", {"ts_code": batch, "start_date": start_date, "end_date": trade_date}, "ts_code,trade_date,open,high,low,close,vol"))
        factor_rows.extend(client.query("adj_factor", {"ts_code": batch, "start_date": start_date, "end_date": trade_date}, "ts_code,trade_date,adj_factor"))
    factors = {(row["ts_code"], row["trade_date"]): float(row["adj_factor"]) for row in factor_rows}
    latest_factor = {}
    for row in factor_rows:
        code = row["ts_code"]
        if code not in latest_factor or row["trade_date"] > latest_factor[code][0]:
            latest_factor[code] = (row["trade_date"], float(row["adj_factor"]))
    grouped = {}
    for row in daily_rows:
        grouped.setdefault(row["ts_code"], []).append(row)
    output = []
    for code, rows in grouped.items():
        base = latest_factor.get(code, (trade_date, 1.0))[1]
        for row in sorted(rows, key=lambda item: item["trade_date"])[-history_days:]:
            ratio = factors.get((code, row["trade_date"]), base) / base
            output.append({
                "date": datetime.strptime(row["trade_date"], "%Y%m%d").date().isoformat(),
                "symbol": from_ts_code(code),
                "open": float(row["open"]) * ratio,
                "high": float(row["high"]) * ratio,
                "low": float(row["low"]) * ratio,
                "close": float(row["close"]) * ratio,
                "volume": float(row["vol"]),
                "name": names[code],
            })
    if not output:
        raise RuntimeError("Tushare股票池没有历史行情")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fields = ["date", "symbol", "open", "high", "low", "close", "volume", "name"]
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    temporary.replace(path)
    return path, {"source": "tushare", "trade_date": trade_date, "universe_size": len(grouped), "rows": len(output)}
