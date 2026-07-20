from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, time as clock_time, timedelta
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


TUSHARE_API_URL = "https://api.tushare.pro"


@dataclass
class TushareClient:
    token: str
    timeout: float = 30
    retries: int = 3

    @classmethod
    def from_environment(cls) -> "TushareClient":
        token = os.environ.get("TUSHARE_TOKEN")
        if not token:
            raise RuntimeError("未配置 TUSHARE_TOKEN")
        return cls(token)

    def query(self, api_name: str, params: dict | None = None, fields: str = "") -> list[dict]:
        body = json.dumps({"api_name": api_name, "token": self.token, "params": params or {}, "fields": fields}).encode()
        request = Request(TUSHARE_API_URL, data=body, headers={"Content-Type": "application/json", "User-Agent": "quantlab/0.3"})
        for attempt in range(self.retries):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                if payload.get("code") != 0:
                    raise RuntimeError(f"Tushare {api_name} 失败：{payload.get('msg', '未知错误')}")
                data = payload.get("data") or {}
                columns = data.get("fields") or []
                return [dict(zip(columns, item)) for item in (data.get("items") or [])]
            except OSError:
                if attempt + 1 == self.retries:
                    raise
                time.sleep(0.5 * (attempt + 1))
        return []

    def latest_open_date(self, today: date | None = None) -> str:
        if today is None:
            now = datetime.now(ZoneInfo("Asia/Shanghai"))
            today = now.date() if now.time() >= clock_time(17, 0) else now.date() - timedelta(days=1)
        rows = self.query("trade_cal", {
            "exchange": "SSE",
            "start_date": (today - timedelta(days=20)).strftime("%Y%m%d"),
            "end_date": today.strftime("%Y%m%d"),
            "is_open": "1",
        }, "cal_date,is_open")
        dates = sorted(row["cal_date"] for row in rows if int(row["is_open"]) == 1)
        if not dates:
            raise RuntimeError("Tushare交易日历未返回最近交易日")
        return dates[-1]


def to_ts_code(symbol: str) -> str:
    return f"{symbol}.SH" if symbol.startswith(("5", "6", "9")) else f"{symbol}.SZ"


def from_ts_code(ts_code: str) -> str:
    return ts_code.split(".", 1)[0]
