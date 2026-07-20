from __future__ import annotations

import json
import gzip
import time
from datetime import datetime, time as clock_time
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .market import TENCENT_QUOTE_URL, is_st_name, market_symbol


SHANGHAI = ZoneInfo("Asia/Shanghai")


def in_trading_session(now: datetime | None = None) -> bool:
    now = now or datetime.now(SHANGHAI)
    current = now.timetz().replace(tzinfo=None)
    return now.weekday() < 5 and (
        clock_time(9, 25) <= current <= clock_time(11, 30)
        or clock_time(13, 0) <= current <= clock_time(15, 0)
    )


def _fetch_quotes_batch(symbols: list[str], timeout: float = 10, retries: int = 3) -> list[dict]:
    request = Request(TENCENT_QUOTE_URL + ",".join(market_symbol(symbol) for symbol in symbols), headers={"User-Agent": "Mozilla/5.0 quantlab/0.2"})
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("gbk")
            break
        except (OSError, ValueError):
            if attempt + 1 == retries:
                raise
            time.sleep(0.5 * (attempt + 1))
    captured_at = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    quotes = []
    for line in payload.splitlines():
        fields = line.split('="', 1)[-1].rstrip('";').split("~")
        if len(fields) < 38:
            continue
        name = fields[1].strip()
        if is_st_name(name):
            continue
        quotes.append({
            "captured_at": captured_at,
            "provider_time": fields[30],
            "symbol": fields[2],
            "name": name,
            "last": float(fields[3]),
            "pct_change": float(fields[32]),
            "change": float(fields[31]),
            "volume": float(fields[6]),
            "amount": float(fields[37]),
            "high": float(fields[33]),
            "low": float(fields[34]),
            "open": float(fields[5]),
            "previous_close": float(fields[4]),
        })
    return quotes


def fetch_quotes(symbols: list[str], timeout: float = 10, retries: int = 3, batch_size: int = 100) -> list[dict]:
    quotes = []
    for offset in range(0, len(symbols), batch_size):
        quotes.extend(_fetch_quotes_batch(symbols[offset:offset + batch_size], timeout, retries))
    return quotes


def append_snapshot(path: Path, quotes: list[dict]) -> int:
    if not quotes:
        raise RuntimeError("实时行情接口没有返回可用的非ST股票")
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "at", encoding="utf-8") as handle:
        for quote in quotes:
            handle.write(json.dumps(quote, ensure_ascii=False) + "\n")
    return len(quotes)


def ensure_fresh(quotes: list[dict], now: datetime, maximum_age_seconds: float = 120) -> None:
    timestamps = [
        datetime.strptime(quote["provider_time"], "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI)
        for quote in quotes if quote.get("provider_time")
    ]
    if not timestamps or (now - max(timestamps)).total_seconds() > maximum_age_seconds:
        raise RuntimeError("实时行情时间戳陈旧，拒绝写入训练样本")


def monitor(symbols: list[str], directory: Path, interval: float = 5, minutes: float = 240, once: bool = False) -> int:
    if interval < 1:
        raise ValueError("采样间隔不能小于1秒")
    deadline = time.monotonic() + max(0, minutes) * 60
    total = 0
    while True:
        now = datetime.now(SHANGHAI)
        if once or in_trading_session(now):
            path = directory / f"{now.date().isoformat()}.jsonl.gz"
            quotes = fetch_quotes(symbols)
            if not once:
                ensure_fresh(quotes, now)
            total += append_snapshot(path, quotes)
        if once or time.monotonic() >= deadline:
            return total
        time.sleep(interval)
