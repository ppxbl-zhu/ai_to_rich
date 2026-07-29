from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from quantagent.paper_cli import load_session, save_session
from quantagent.providers.tushare import TushareClient
from quantagent.providers.tushare_swing import enrich_monitor_with_swing


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Enrich a verified monitor session with Tushare swing factors"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--at",
        type=datetime.fromisoformat,
        default=None,
        help="timezone-aware decision time; defaults to local current time",
    )
    arguments = parser.parse_args(argv)
    environment = os.environ if environ is None else environ
    token = environment.get("TUSHARE_TOKEN")
    if not token:
        parser.error("TUSHARE_TOKEN is required")
    now = arguments.at or datetime.now().astimezone()
    session = enrich_monitor_with_swing(
        client=TushareClient(token=token),
        monitor=load_session(arguments.input),
        decision_time=now,
    )
    save_session(session, arguments.output)
    print(
        json.dumps(
            {
                "status": "enriched",
                "session_id": session.session_id,
                "dataset_version": session.dataset_version,
                "quote_count": len(session.quotes),
                "swing_candidate_count": len(session.swing_candidates),
                "closing_candidate_count": 0,
                "output": str(arguments.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
