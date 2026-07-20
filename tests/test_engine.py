import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quantlab.engine import make_demo, run_paper
from quantlab.market import _secid, is_st_name, update_market_csv
from quantlab.notifier import publish_pushplus
from quantlab.realtime import append_snapshot, ensure_fresh, in_trading_session
from quantlab.tushare_client import from_ts_code, to_ts_code
from quantlab.universe import build_liquid_universe


class EngineTest(unittest.TestCase):
    def test_paper_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "data.csv"
            make_demo(data, 120)
            cfg = Path(__file__).resolve().parents[1] / "config.json"
            first = run_paper(cfg, data, root / "state", root / "reports")
            state1 = json.loads((root / "state" / "portfolio.json").read_text(encoding="utf-8"))
            second = run_paper(cfg, data, root / "state", root / "reports")
            state2 = json.loads((root / "state" / "portfolio.json").read_text(encoding="utf-8"))
            self.assertEqual(first, second)
            self.assertEqual(state1, state2)

    def test_market_code_mapping_and_atomic_csv(self):
        self.assertEqual(_secid("600519"), "1.600519")
        self.assertEqual(_secid("000001"), "0.000001")
        with self.assertRaises(ValueError):
            _secid("bad")
        with tempfile.TemporaryDirectory() as td, patch("quantlab.market.fetch_instrument") as fetch, patch("quantlab.market.fetch_names") as names:
            data = Path(td) / "market.csv"
            demo = Path(td) / "demo.csv"
            make_demo(demo, 90)
            from quantlab.engine import load_bars
            bars = load_bars(demo)["600000"]
            names.return_value = {"600000": "浦发银行", "000001": "*ST测试"}
            fetch.side_effect = lambda symbol, limit: (symbol, bars)
            update_market_csv(["600000", "000001"], data)
            self.assertTrue(data.exists())
            self.assertFalse(data.with_suffix(".csv.tmp").exists())
            content = data.read_text(encoding="utf-8")
            self.assertIn("浦发银行", content)
            self.assertNotIn("*ST测试", content)

    def test_st_and_realtime_snapshot_guards(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        self.assertTrue(is_st_name("*ST测试"))
        self.assertFalse(is_st_name("贵州茅台"))
        zone = ZoneInfo("Asia/Shanghai")
        self.assertTrue(in_trading_session(datetime(2026, 7, 21, 10, 0, tzinfo=zone)))
        self.assertFalse(in_trading_session(datetime(2026, 7, 21, 12, 0, tzinfo=zone)))
        ensure_fresh([{"provider_time": "20260721100000"}], datetime(2026, 7, 21, 10, 1, tzinfo=zone))
        with self.assertRaises(RuntimeError):
            ensure_fresh([{"provider_time": "20260721090000"}], datetime(2026, 7, 21, 10, 1, tzinfo=zone))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "quotes.jsonl"
            self.assertEqual(append_snapshot(path, [{"symbol": "600000"}]), 1)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)

    def test_pushplus_is_optional(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(publish_pushplus("title", "body"))

    def test_tushare_codes_and_universe_filters(self):
        self.assertEqual(to_ts_code("600000"), "600000.SH")
        self.assertEqual(from_ts_code("000001.SZ"), "000001")
        client = unittest.mock.Mock()
        client.query.side_effect = [
            [
                {"ts_code": "600000.SH", "name": "浦发银行", "list_date": "19991110"},
                {"ts_code": "000001.SZ", "name": "平安银行", "list_date": "19910403"},
                {"ts_code": "000002.SZ", "name": "ST测试", "list_date": "19910129"},
            ],
            [{"ts_code": "000002.SZ"}],
            [
                {"ts_code": "600000.SH", "amount": 200, "vol": 10, "close": 9},
                {"ts_code": "000001.SZ", "amount": 300, "vol": 10, "close": 11},
                {"ts_code": "000002.SZ", "amount": 500, "vol": 10, "close": 3},
            ],
        ]
        result = build_liquid_universe(client, "20260720", size=2)
        self.assertEqual([row["ts_code"] for row in result], ["000001.SZ", "600000.SH"])


if __name__ == "__main__":
    unittest.main()
