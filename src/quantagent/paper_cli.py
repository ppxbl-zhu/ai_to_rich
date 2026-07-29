from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from quantagent.closing import ClosingCandidate
from quantagent.domain import Board, MarketQuote, SecurityStatus
from quantagent.paper_runtime import (
    JsonStateStore,
    PaperRuntime,
    PaperSession,
    RuntimeStatus,
)
from quantagent.swing import MarketRegime, SwingCandidate


def load_session(path: Path) -> PaperSession:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported paper session schema")
    quotes = {
        item["symbol"]: MarketQuote(
            symbol=item["symbol"],
            name=item["name"],
            board=Board(item["board"]),
            market_time=datetime.fromisoformat(item["market_time"]),
            captured_at=datetime.fromisoformat(item["captured_at"]),
            price=Decimal(item["price"]),
            previous_close=Decimal(item["previous_close"]),
            limit_up=Decimal(item["limit_up"]),
            limit_down=Decimal(item["limit_down"]),
            status=SecurityStatus(item["status"]),
            source=item["source"],
        )
        for item in payload["quotes"]
    }
    swing_candidates = tuple(
        SwingCandidate(
            symbol=item["symbol"],
            price=Decimal(item["price"]),
            ma20=Decimal(item["ma20"]),
            ma60=Decimal(item["ma60"]),
            weekly_ma10=Decimal(item["weekly_ma10"]),
            relative_strength_60d=Decimal(item["relative_strength_60d"]),
            sector_relative_strength=Decimal(item["sector_relative_strength"]),
            roe=Decimal(item["roe"]),
            operating_cashflow_positive=bool(item["operating_cashflow_positive"]),
            debt_ratio=Decimal(item["debt_ratio"]),
            atr=Decimal(item["atr"]),
            market_regime=MarketRegime(item["market_regime"]),
        )
        for item in payload["swing_candidates"]
    )
    closing_candidates = tuple(
        ClosingCandidate(
            symbol=item["symbol"],
            observed_at=time.fromisoformat(item["observed_at"]),
            price=Decimal(item["price"]),
            vwap=Decimal(item["vwap"]),
            close_location=Decimal(item["close_location"]),
            volume_ratio=Decimal(item["volume_ratio"]),
            turnover=Decimal(item["turnover"]),
            stock_relative_strength=Decimal(item["stock_relative_strength"]),
            sector_relative_strength=Decimal(item["sector_relative_strength"]),
            sector_breadth=Decimal(item["sector_breadth"]),
            at_limit_up=bool(item["at_limit_up"]),
            fresh=bool(item["fresh"]),
        )
        for item in payload["closing_candidates"]
    )
    return PaperSession(
        session_id=payload["session_id"],
        trading_date=date.fromisoformat(payload["trading_date"]),
        captured_at=datetime.fromisoformat(payload["captured_at"]),
        dataset_version=payload["dataset_version"],
        is_trading_day=bool(payload["is_trading_day"]),
        quotes=quotes,
        swing_candidates=swing_candidates,
        closing_candidates=closing_candidates,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Operate the QuantAgent paper runtime")
    parser.add_argument(
        "--state",
        type=Path,
        default=Path("data/paper/runtime.json"),
        help="local runtime state; never commit this file",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("--at", type=datetime.fromisoformat, required=True)
    stop_parser = commands.add_parser("stop")
    stop_parser.add_argument("--at", type=datetime.fromisoformat, required=True)
    stop_parser.add_argument("--reason", required=True)
    commands.add_parser("status")
    run_parser = commands.add_parser("run-once")
    run_parser.add_argument("--session", type=Path, required=True)
    run_parser.add_argument("--at", type=datetime.fromisoformat, required=True)
    arguments = parser.parse_args(argv)

    runtime = PaperRuntime(JsonStateStore(arguments.state))
    if arguments.command == "start":
        result: Any = runtime.start(arguments.at)
        exit_code = 0
    elif arguments.command == "stop":
        result = runtime.stop(arguments.at, reason=arguments.reason)
        exit_code = 0
    elif arguments.command == "status":
        result = runtime.status()
        exit_code = 0
    else:
        result = runtime.run_once(load_session(arguments.session), now=arguments.at)
        exit_code = (
            0
            if result.status
            in (RuntimeStatus.COMPLETED, RuntimeStatus.ALREADY_PROCESSED)
            else 2
        )
    print(json.dumps(_jsonable(asdict(result)), ensure_ascii=False, sort_keys=True))
    return exit_code


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


if __name__ == "__main__":
    raise SystemExit(main())
