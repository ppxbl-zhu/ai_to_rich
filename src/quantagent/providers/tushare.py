from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.request import Request, urlopen

Transport = Callable[[str, dict[str, Any], float], dict[str, Any]]


class TushareError(RuntimeError):
    """Raised when Tushare rejects or malforms a request."""


class CapabilityStatus(StrEnum):
    EXPECTED_AVAILABLE = "expected_available"
    SEPARATE_PERMISSION = "separate_permission"
    NEEDS_LIVE_PROBE = "needs_live_probe"
    INSUFFICIENT_POINTS = "insufficient_points"


@dataclass(frozen=True, slots=True)
class TushareCapability:
    api_name: str
    status: CapabilityStatus
    requirement: str


class TushareClient:
    _URL = "https://api.tushare.pro"

    def __init__(self, *, token: str, transport: Transport | None = None) -> None:
        self._token = token
        self._transport = transport or _http_transport

    def query(
        self, api_name: str, params: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        response = self._transport(
            self._URL,
            {
                "api_name": api_name,
                "token": self._token,
                "params": params,
                "fields": "",
            },
            20.0,
        )
        if response.get("code") != 0:
            raise TushareError(str(response.get("msg") or "Tushare request failed"))
        data = response.get("data")
        if not isinstance(data, dict):
            raise TushareError("Tushare response data is missing")
        fields = data.get("fields")
        items = data.get("items")
        if not isinstance(fields, list) or not isinstance(items, list):
            raise TushareError("Tushare response shape is invalid")
        return tuple(dict(zip(fields, item, strict=True)) for item in items)


def assess_capabilities(
    *, points: int, separate_permissions: set[str]
) -> tuple[TushareCapability, ...]:
    point_requirements = {
        "stock_basic": 120,
        "trade_cal": 0,
        "daily": 120,
        "daily_basic": 2000,
        "stk_limit": 2000,
        "suspend_d": 2000,
        "income_vip": 5000,
        "balancesheet_vip": 5000,
        "cashflow_vip": 5000,
        "fina_indicator_vip": 5000,
        "disclosure_date": 500,
        "moneyflow": 2000,
        "index_daily": 2000,
        "share_float": 120,
    }
    capabilities = [
        TushareCapability(
            api_name=api_name,
            status=(
                CapabilityStatus.EXPECTED_AVAILABLE
                if points >= required
                else CapabilityStatus.INSUFFICIENT_POINTS
            ),
            requirement=f"{required} points",
        )
        for api_name, required in point_requirements.items()
    ]
    for api_name in ("rt_min", "news", "major_news"):
        capabilities.append(
            TushareCapability(
                api_name=api_name,
                status=(
                    CapabilityStatus.NEEDS_LIVE_PROBE
                    if api_name in separate_permissions
                    else CapabilityStatus.SEPARATE_PERMISSION
                ),
                requirement="separate permission",
            )
        )
    return tuple(capabilities)


def probe_endpoints(
    client: TushareClient, requests: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for api_name, params in requests.items():
        try:
            rows = client.query(api_name, params)
            results[api_name] = {"status": "available", "rows": len(rows)}
        except TushareError as error:
            results[api_name] = {"status": "unavailable", "reason": str(error)}
    return results


def _http_transport(
    url: str, payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    return result
