from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from quantagent.paper_cli import load_session, save_session
from quantagent.providers.eastmoney_monitor import build_monitor_session
from quantagent.providers.eastmoney_ocr import OcrFrame, OcrWord

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 9, 50, tzinfo=CST)


class FakeTushareClient:
    def query(
        self, api_name: str, params: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        responses = {
            "trade_cal": (
                {"cal_date": "20260728", "is_open": 1},
                {"cal_date": "20260729", "is_open": 1},
            ),
            "daily": ({"ts_code": "300207.SZ", "close": 17.98},),
            "stk_limit": (
                {
                    "ts_code": "300207.SZ",
                    "up_limit": 21.58,
                    "down_limit": 14.38,
                },
            ),
            "suspend_d": (),
        }
        return responses[api_name]


class FakeFrameSource:
    def capture(self, process_id: int) -> OcrFrame:
        return OcrFrame(
            window_title="东方财富终端",
            window_width=1437,
            window_height=745,
            captured_at=NOW,
            words=(
                OcrWord("300207", 113, 128, 140, 32),
                OcrWord("欣", 329, 128, 30, 32),
                OcrWord("旺", 379, 128, 30, 32),
                OcrWord("达", 429, 128, 30, 32),
                OcrWord("18", 788, 128, 44, 32),
                OcrWord("·", 836, 152, 8, 8),
                OcrWord("15", 848, 128, 44, 32),
                OcrWord("0", 957, 128, 19, 32),
                OcrWord("·", 980, 152, 8, 8),
                OcrWord("95", 992, 128, 44, 32),
            ),
        )


def test_eastmoney_and_tushare_build_a_serializable_monitor_session(
    tmp_path: Path,
) -> None:
    session = build_monitor_session(
        client=FakeTushareClient(),
        frame_source=FakeFrameSource(),
        process_id=9904,
        now=NOW,
    )

    assert tuple(session.quotes) == ("300207.SZ",)
    assert session.quotes["300207.SZ"].price == Decimal("18.15")
    assert session.swing_candidates == ()
    assert session.closing_candidates == ()

    path = tmp_path / "monitor.json"
    save_session(session, path)
    assert load_session(path) == session
