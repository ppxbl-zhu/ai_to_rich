from typing import Any

import pytest

from quantagent.providers.tushare import (
    CapabilityStatus,
    TushareClient,
    TushareError,
    assess_capabilities,
    probe_endpoints,
)


def test_tushare_client_maps_fields_and_items_without_sdk() -> None:
    def transport(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        return {
            "code": 0,
            "msg": None,
            "data": {
                "fields": ["ts_code", "trade_date", "close"],
                "items": [["000001.SZ", "20260728", 10.2]],
            },
        }

    client = TushareClient(token="secret-token", transport=transport)

    assert client.query("daily", {"trade_date": "20260728"}) == (
        {"ts_code": "000001.SZ", "trade_date": "20260728", "close": 10.2},
    )
    assert "secret-token" not in repr(client)


def test_tushare_client_fails_closed_on_api_error_without_leaking_token() -> None:
    def transport(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        return {"code": -2001, "msg": "permission denied", "data": None}

    client = TushareClient(token="secret-token", transport=transport)

    with pytest.raises(TushareError, match="permission denied") as captured:
        client.query("rt_min", {"ts_code": "000001.SZ", "freq": "1MIN"})
    assert "secret-token" not in str(captured.value)


def test_6238_point_account_catalog_distinguishes_separate_permissions() -> None:
    capabilities = {
        item.api_name: item
        for item in assess_capabilities(points=6238, separate_permissions=set())
    }

    assert capabilities["daily_basic"].status is CapabilityStatus.EXPECTED_AVAILABLE
    assert (
        capabilities["fina_indicator_vip"].status is CapabilityStatus.EXPECTED_AVAILABLE
    )
    assert capabilities["rt_min"].status is CapabilityStatus.SEPARATE_PERMISSION
    assert capabilities["news"].status is CapabilityStatus.SEPARATE_PERMISSION


def test_separately_authorized_realtime_minute_is_marked_for_live_probe() -> None:
    capabilities = {
        item.api_name: item
        for item in assess_capabilities(points=6238, separate_permissions={"rt_min"})
    }

    assert capabilities["rt_min"].status is CapabilityStatus.NEEDS_LIVE_PROBE


def test_permission_probe_records_counts_and_sanitized_failures() -> None:
    def transport(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["api_name"] == "daily":
            return {
                "code": 0,
                "msg": None,
                "data": {"fields": ["ts_code"], "items": [["000001.SZ"]]},
            }
        return {"code": -2001, "msg": "permission denied", "data": None}

    results = probe_endpoints(
        TushareClient(token="secret-token", transport=transport),
        {
            "daily": {"trade_date": "20260728"},
            "rt_min": {"ts_code": "000001.SZ", "freq": "1MIN"},
        },
    )

    assert results["daily"] == {"status": "available", "rows": 1}
    assert results["rt_min"] == {
        "status": "unavailable",
        "reason": "permission denied",
    }
    assert "secret-token" not in repr(results)
