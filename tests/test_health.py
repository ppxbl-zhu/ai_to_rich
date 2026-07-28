from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from quantagent.health import build_health_report, main
from quantagent.settings import Settings


def test_health_report_accepts_deterministic_offline_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "quotes.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "quotes": [
                    {
                        "symbol": "000001.SZ",
                        "market_time": "2024-01-02T15:00:00+08:00",
                        "price": "9.80",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_health_report(Settings.from_env({}), fixture)

    assert report == {
        "status": "ok",
        "execution_mode": "paper",
        "database": "sqlite",
        "offline_fixture": {"status": "ok", "quote_count": 1},
    }


def test_health_report_rejects_malformed_offline_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "quotes.json"
    fixture.write_text('{"schema_version": 1, "quotes": []}', encoding="utf-8")

    report = build_health_report(Settings.from_env({}), fixture)

    assert report["status"] == "error"
    assert report["offline_fixture"] == {
        "status": "error",
        "reason": "quotes must contain at least one item",
    }


def test_health_command_prints_json_and_returns_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = tmp_path / "quotes.json"
    fixture.write_text(
        '{"schema_version":1,"quotes":[{"symbol":"600000.SH",'
        '"market_time":"2024-01-02T15:00:00+08:00","price":"8.20"}]}',
        encoding="utf-8",
    )

    exit_code = main(["--fixture", str(fixture)], environ={})
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)["status"] == "ok"


def test_health_module_entrypoint_prints_report() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src"
    process_environment = os.environ.copy()
    process_environment["PYTHONPATH"] = str(source_root)
    result = subprocess.run(
        [sys.executable, "-m", "quantagent.health"],
        check=True,
        capture_output=True,
        env=process_environment,
        text=True,
    )

    assert json.loads(result.stdout)["status"] == "ok"
