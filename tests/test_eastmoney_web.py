from datetime import datetime, timedelta, timezone

from quantagent.providers.eastmoney_web import EastmoneyWebProvider

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 14, 50, tzinfo=CST)


def test_fetches_and_normalizes_paginated_realtime_market_rows() -> None:
    calls = []

    def transport(market: str, page: int) -> dict[str, object]:
        calls.append((market, page))
        code = "600001" if market == "sh" else "300001"
        return {
            "data": {
                "total": 1,
                "diff": [
                    {
                        "f2": 10.0,
                        "f3": 8.0,
                        "f5": 120000,
                        "f6": 120000000,
                        "f10": 1.8,
                        "f12": code,
                        "f13": 1 if market == "sh" else 0,
                        "f14": "测试股份",
                        "f15": 10.0,
                        "f16": 8.0,
                        "f17": 8.5,
                        "f18": 9.0,
                    }
                ],
            }
        }

    rows = EastmoneyWebProvider(transport=transport, minimum_universe=2).fetch(NOW)

    assert tuple(item.symbol for item in rows) == ("300001.SZ", "600001.SH")
    assert rows[0].amount == 120000000
    assert rows[0].volume_hands == 120000
    assert rows[0].captured_at == NOW
    assert calls == [("sh", 1), ("sz", 1)]
