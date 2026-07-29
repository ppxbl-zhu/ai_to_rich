from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import partial
from math import ceil
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from quantagent.closing_snapshot import RealtimeStock

Transport = Callable[[str, int], dict[str, object]]

_FILTERS = {
    "sh": "m:1 t:2,m:1 t:23",
    "sz": "m:0 t:6,m:0 t:80",
}
_FIELDS = "f2,f3,f5,f6,f10,f12,f13,f14,f15,f16,f17,f18"


class EastmoneyWebError(RuntimeError):
    pass


class EastmoneyWebProvider:
    def __init__(
        self,
        *,
        transport: Transport | None = None,
        minimum_universe: int = 1000,
    ) -> None:
        self._transport = transport or _transport
        self._minimum_universe = minimum_universe

    def fetch(self, captured_at: datetime) -> tuple[RealtimeStock, ...]:
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("realtime capture requires a timezone")
        rows = []
        for market in ("sh", "sz"):
            first = self._transport(market, 1)
            data = _data(first)
            total = int(data["total"])
            if total <= 0 or total > 4000:
                raise EastmoneyWebError(f"{market} realtime total is implausible")
            pages = ceil(total / 100)
            payloads = [first]
            if pages > 1:
                with ThreadPoolExecutor(max_workers=8) as executor:
                    payloads.extend(
                        executor.map(
                            partial(self._transport, market),
                            range(2, pages + 1),
                        )
                    )
            for payload in payloads:
                for item in _data(payload)["diff"]:
                    normalized = _normalize(item, captured_at)
                    if normalized is not None:
                        rows.append(normalized)
        unique = {item.symbol: item for item in rows}
        if len(unique) < self._minimum_universe:
            raise EastmoneyWebError("realtime universe is unexpectedly small")
        return tuple(unique[symbol] for symbol in sorted(unique))


def _data(payload: dict[str, object]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise EastmoneyWebError("Eastmoney realtime payload is missing data")
    if not isinstance(data.get("total"), int) or not isinstance(data.get("diff"), list):
        raise EastmoneyWebError("Eastmoney realtime payload shape is invalid")
    return data


def _normalize(
    item: object,
    captured_at: datetime,
) -> RealtimeStock | None:
    if not isinstance(item, dict):
        return None
    code = str(item.get("f12") or "")
    if len(code) != 6 or not code.isdigit():
        return None
    try:
        return RealtimeStock(
            symbol=f"{code}.{'SH' if code.startswith('6') else 'SZ'}",
            name=str(item["f14"]),
            price=_decimal(item["f2"]),
            pct_change_percent=_decimal(item["f3"]),
            volume_hands=_decimal(item["f5"]),
            amount=_decimal(item["f6"]),
            high=_decimal(item["f15"]),
            low=_decimal(item["f16"]),
            open=_decimal(item["f17"]),
            previous_close=_decimal(item["f18"]),
            volume_ratio=_decimal(item["f10"]),
            captured_at=captured_at,
        )
    except (KeyError, InvalidOperation, ValueError):
        return None


def _decimal(value: object) -> Decimal:
    if value in (None, "-"):
        raise ValueError("numeric realtime field is missing")
    return Decimal(str(value))


def _transport(market: str, page: int) -> dict[str, object]:
    params = {
        "pn": str(page),
        "pz": "100",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f12",
        "fs": _FILTERS[market],
        "fields": _FIELDS,
    }
    url = f"https://82.push2.eastmoney.com/api/qt/clist/get?{urlencode(params)}"
    with urlopen(url, timeout=10) as response:
        result: dict[str, object] = json.loads(response.read().decode("utf-8"))
    return result
