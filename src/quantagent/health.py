from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from quantagent.settings import Settings


def build_health_report(settings: Settings, fixture_path: Path) -> dict[str, Any]:
    fixture_status: dict[str, Any]
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        quotes = payload.get("quotes")
        if not isinstance(quotes, list) or not quotes:
            raise ValueError("quotes must contain at least one item")
        fixture_status = {"status": "ok", "quote_count": len(quotes)}
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        fixture_status = {"status": "error", "reason": str(error)}

    return {
        "status": "ok" if fixture_status["status"] == "ok" else "error",
        "execution_mode": settings.execution_mode,
        "database": urlsplit(settings.database_url).scheme,
        "offline_fixture": fixture_status,
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Run offline QuantAgent health checks")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("tests/fixtures/quotes.json"),
        help="deterministic offline quote fixture",
    )
    arguments = parser.parse_args(argv)
    settings = Settings.from_env(os.environ if environ is None else environ)
    report = build_health_report(settings, arguments.fixture)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
