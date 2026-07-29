from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from quantagent.paper_cli import save_session
from quantagent.providers.eastmoney_monitor import build_monitor_session
from quantagent.providers.eastmoney_ocr import WindowsEastmoneyFrameSource
from quantagent.providers.tushare import TushareClient


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Capture a read-only Eastmoney monitor session"
    )
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--at",
        type=datetime.fromisoformat,
        default=None,
        help="timezone-aware capture time; defaults to local current time",
    )
    arguments = parser.parse_args(argv)
    environment = os.environ if environ is None else environ
    token = environment.get("TUSHARE_TOKEN")
    if not token:
        parser.error("TUSHARE_TOKEN is required")
    now = arguments.at or datetime.now().astimezone()
    session = build_monitor_session(
        client=TushareClient(token=token),
        frame_source=WindowsEastmoneyFrameSource(),
        process_id=arguments.process_id,
        now=now,
    )
    save_session(session, arguments.output)
    print(
        json.dumps(
            {
                "status": "captured",
                "session_id": session.session_id,
                "dataset_version": session.dataset_version,
                "quote_count": len(session.quotes),
                "output": str(arguments.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
