import json
import tempfile
import unittest
from pathlib import Path

from quantlab.engine import make_demo, run_paper


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


if __name__ == "__main__":
    unittest.main()
