from __future__ import annotations

import argparse
import json
import os
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import datetime
from datetime import time as wall_time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from quantagent.paper_cli import save_session
from quantagent.paper_runtime import JsonStateStore, PaperRuntime
from quantagent.platform import (
    PlatformController,
    PlatformStore,
    qualify_simulation_day,
)
from quantagent.platform_schedule import CycleKind
from quantagent.providers.closing_session import build_closing_session
from quantagent.providers.eastmoney_web import EastmoneyWebProvider
from quantagent.providers.full_market_swing import (
    FullMarketSwingScanner,
    FullMarketSwingSnapshot,
    build_full_market_swing_session,
)
from quantagent.providers.tushare import TushareClient


class LivePlatform:
    def __init__(
        self,
        *,
        token: str,
        process_id: int,
        platform_state: Path,
        runtime_state: Path,
        session_dir: Path,
    ) -> None:
        self.client = TushareClient(token=token)
        self.process_id = process_id
        self.controller = PlatformController(PlatformStore(platform_state))
        self.runtime = PaperRuntime(JsonStateStore(runtime_state))
        self.platform_store = PlatformStore(platform_state)
        self.runtime_store = JsonStateStore(runtime_state)
        self.session_dir = session_dir
        self.web_realtime = EastmoneyWebProvider()
        self.swing_scanner = FullMarketSwingScanner(client=self.client)
        self.swing_snapshot: FullMarketSwingSnapshot | None = None

    def run_cycle(self, now: datetime) -> object:
        return self.controller.run_due(
            now,
            is_trading_day=self._is_trading_day(now),
            handlers={
                CycleKind.PREOPEN: lambda: self._preopen(now),
                CycleKind.MONITOR: lambda: self._monitor(now),
                CycleKind.CLOSING: lambda: self._closing(now),
                CycleKind.POSTCLOSE: lambda: self._postclose(now),
            },
        )

    def status_payload(self) -> dict[str, object]:
        return {
            "platform": asdict(self.platform_store.load()),
            "paper_account": asdict(self.runtime_store.load()),
            "mode": "paper",
            "live_orders_enabled": False,
        }

    def _is_trading_day(self, now: datetime) -> bool:
        value = now.strftime("%Y%m%d")
        rows = self.client.query(
            "trade_cal",
            {"exchange": "SSE", "start_date": value, "end_date": value},
        )
        return bool(rows and int(rows[0]["is_open"]) == 1)

    def _preopen(self, now: datetime) -> dict[str, object]:
        self.swing_snapshot = self.swing_scanner.scan(as_of=now)
        state = self.runtime.start(now)
        return {
            "runtime_enabled": state.enabled,
            "cash": str(state.cash),
            "swing_universe": "all_a_shares",
            "scanned_symbols": self.swing_snapshot.scanned_symbols,
            "swing_candidates": len(self.swing_snapshot.candidates),
        }

    def _monitor(self, now: datetime) -> dict[str, object]:
        if (
            self.swing_snapshot is None
            or self.swing_snapshot.as_of.date() != now.date()
        ):
            self.swing_snapshot = self.swing_scanner.scan(as_of=now)
        session = build_full_market_swing_session(
            snapshot=self.swing_snapshot,
            client=self.client,
            realtime=self.web_realtime,
            now=now,
        )
        path = self._session_path("swing", session.session_id)
        save_session(session, path)
        if not self.runtime.status().enabled:
            self.runtime.start(session.captured_at)
        report = self.runtime.run_once(
            session,
            now=datetime.now().astimezone(),
        )
        return {
            "session_id": session.session_id,
            "quotes": len(session.quotes),
            "swing_candidates": len(session.swing_candidates),
            "swing_universe": "all_a_shares",
            "scanned_symbols": self.swing_snapshot.scanned_symbols,
            "status": report.status.value,
            "plans": report.generated_plans,
            "fills": report.fills,
            "rejected": report.rejected_plans,
        }

    def _closing(self, now: datetime) -> dict[str, object]:
        session = build_closing_session(
            client=self.client,
            realtime=self.web_realtime,
            now=now,
        )
        path = self._session_path("closing", session.session_id)
        save_session(session, path)
        if not self.runtime.status().enabled:
            self.runtime.start(session.captured_at)
        report = self.runtime.run_once(
            session,
            now=datetime.now().astimezone(),
        )
        return {
            "session_id": session.session_id,
            "quotes": len(session.quotes),
            "closing_candidates": len(session.closing_candidates),
            "status": report.status.value,
            "plans": report.generated_plans,
            "fills": report.fills,
            "rejected": report.rejected_plans,
        }

    def _postclose(self, now: datetime) -> dict[str, object]:
        state = self.runtime.status()
        symbols = set(state.positions)
        metadata_symbols = (
            set(state.position_strategies)
            & set(state.stop_prices)
            & set(state.target_prices)
        )
        if symbols != metadata_symbols:
            raise RuntimeError("position plan metadata does not reconcile")
        day = qualify_simulation_day(
            self.platform_store.load().cycle_results,
            trading_date=now.date(),
            reconciled=True,
            open_incidents=state.open_incidents,
        )
        stopped = self.runtime.stop(now, reason="scheduled post-close")
        return {
            "reconciled": True,
            "workflow_completed": day.completed,
            "critical_incident": day.critical_incident,
            "qualifying_day": (
                day.completed and day.reconciled and not day.critical_incident
            ),
            "cash": str(stopped.cash),
            "positions": len(stopped.positions),
            "fills": len(stopped.fill_ids),
            "critical_incidents": stopped.open_incidents,
        }

    def _session_path(self, kind: str, session_id: str) -> Path:
        return self.session_dir / f"{kind}-{session_id}.json"


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Run the local paper platform")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "cycle", "status"):
        command = subparsers.add_parser(name)
        command.add_argument("--process-id", type=int, required=True)
        command.add_argument(
            "--platform-state",
            type=Path,
            default=Path("data/paper/platform.json"),
        )
        command.add_argument(
            "--runtime-state",
            type=Path,
            default=Path("data/paper/runtime.json"),
        )
        command.add_argument(
            "--session-dir",
            type=Path,
            default=Path("data/paper/sessions"),
        )
    subparsers.choices["serve"].add_argument("--port", type=int, default=8765)
    subparsers.choices["serve"].add_argument("--poll-seconds", type=int, default=15)
    arguments = parser.parse_args(argv)
    environment = os.environ if environ is None else environ
    token = environment.get("TUSHARE_TOKEN")
    if not token:
        parser.error("TUSHARE_TOKEN is required")
    application = LivePlatform(
        token=token,
        process_id=arguments.process_id,
        platform_state=arguments.platform_state,
        runtime_state=arguments.runtime_state,
        session_dir=arguments.session_dir,
    )
    if arguments.command == "status":
        print(_json(application.status_payload()))
        return 0
    if arguments.command == "cycle":
        result = application.run_cycle(datetime.now().astimezone())
        print(_json(asdict(result) if result is not None else {"status": "not_due"}))
        return 0
    server = _dashboard_server(application, port=arguments.port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        while True:
            now = datetime.now().astimezone()
            application.run_cycle(now)
            if now.timetz().replace(tzinfo=None) >= wall_time(15, 30):
                break
            time.sleep(arguments.poll_seconds)
    finally:
        server.shutdown()
        server.server_close()
    return 0


def _dashboard_server(
    application: LivePlatform,
    *,
    port: int,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            payload = application.status_payload()
            if self.path == "/api/status":
                body = _json(payload).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            else:
                body = _dashboard_html(payload).encode("utf-8")
                content_type = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def _dashboard_html(payload: dict[str, object]) -> str:
    escaped = (
        _json(payload).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="15">
<title>QuantAgent 模拟盘</title>
<style>
body{{font-family:system-ui;background:#0b1220;color:#dbeafe;margin:2rem}}
main{{max-width:1100px;margin:auto}}pre{{background:#111827;padding:1.5rem;
border-radius:12px;overflow:auto}}.safe{{color:#34d399}}
</style></head><body><main><h1>QuantAgent 模拟盘</h1>
<p class="safe">仅模拟交易 · 不连接真实下单</p><pre>{escaped}</pre>
</main></body></html>"""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


if __name__ == "__main__":
    raise SystemExit(main())
