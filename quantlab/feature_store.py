from __future__ import annotations

import gzip
import json
import math
import time
from datetime import datetime
from pathlib import Path

from .tushare_client import TushareClient


DAILY_BASIC_FIELDS = "ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,pe_ttm,pb,ps_ttm,dv_ttm,total_mv,circ_mv"
MONEYFLOW_FIELDS = "ts_code,trade_date,buy_sm_amount,sell_sm_amount,buy_md_amount,sell_md_amount,buy_lg_amount,sell_lg_amount,buy_elg_amount,sell_elg_amount,net_mf_amount"
FINANCIAL_FIELDS = "ts_code,ann_date,end_date,roe_dt,roic,grossprofit_margin,netprofit_margin,debt_to_assets,ocf_to_profit,q_sales_yoy,q_netprofit_yoy"


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def load_feature_scores(output_dir: Path, symbols: list[str], allowed_dates: set[str]) -> dict[str, dict[str, tuple[float, float, float]]]:
    """Return point-in-time (flow, activity, quality) scores in roughly [-1, 1]."""
    allowed_compact = {day.replace("-", ""): day for day in allowed_dates}
    result: dict[str, dict[str, tuple[float, float, float]]] = {}
    for symbol in symbols:
        paths = {name: output_dir / name / f"{symbol}.json.gz" for name in ("daily_basic", "moneyflow", "fina_indicator")}
        if not all(path.exists() for path in paths.values()):
            continue
        with gzip.open(paths["daily_basic"], "rt", encoding="utf-8") as handle:
            basics = json.load(handle)
        with gzip.open(paths["moneyflow"], "rt", encoding="utf-8") as handle:
            flows = json.load(handle)
        with gzip.open(paths["fina_indicator"], "rt", encoding="utf-8") as handle:
            financials = json.load(handle)
        flow_by_date, window = {}, []
        for row in sorted(flows, key=lambda item: item["trade_date"]):
            value = _number(row.get("net_mf_amount"))
            window.append(value)
            if len(window) > 20:
                window.pop(0)
            scale = sum(abs(item) for item in window) / max(1, len(window))
            flow_by_date[row["trade_date"]] = math.tanh(sum(window[-5:]) / max(1.0, scale * 5))
        basic_by_date = {}
        for row in basics:
            compact = row["trade_date"]
            if compact not in allowed_compact:
                continue
            volume_ratio = _number(row.get("volume_ratio"))
            turnover = _number(row.get("turnover_rate_f") or row.get("turnover_rate"))
            activity = .60 * math.tanh(volume_ratio - 1) + .40 * max(-1.0, 1 - abs(turnover - 5) / 5)
            basic_by_date[compact] = (flow_by_date.get(compact, 0.0), activity)
        reports = sorted((row for row in financials if row.get("ann_date")), key=lambda item: item["ann_date"])
        report_index, latest = 0, None
        scores = {}
        for compact in sorted(allowed_compact):
            while report_index < len(reports) and reports[report_index]["ann_date"] <= compact:
                latest = reports[report_index]
                report_index += 1
            if compact not in basic_by_date:
                continue
            quality = 0.0
            if latest:
                components = [
                    max(-1, min(1, _number(latest.get("roe_dt")) / 20)),
                    max(-1, min(1, _number(latest.get("roic")) / 15)),
                    max(-1, min(1, _number(latest.get("ocf_to_profit")) / 100)),
                    max(-1, min(1, _number(latest.get("q_sales_yoy")) / 30)),
                    max(-1, min(1, _number(latest.get("q_netprofit_yoy")) / 40)),
                    max(-1, min(1, (60 - _number(latest.get("debt_to_assets"))) / 40)),
                ]
                quality = sum(components) / len(components)
            flow, activity = basic_by_date[compact]
            scores[allowed_compact[compact]] = (flow, activity, quality)
        if scores:
            result[symbol] = scores
    return result


def _write_gzip_json(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, separators=(",", ":"))
    temporary.replace(path)


def backfill_features(client: TushareClient, universe_path: Path, output_dir: Path, start_date: str, end_date: str, pause: float = .05, limit: int = 0) -> dict:
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    if limit > 0:
        universe = universe[:limit]
    completed, failed = 0, []
    for index, stock in enumerate(universe, 1):
        code = stock["ts_code"]
        symbol = code.split(".", 1)[0]
        targets = {
            "daily_basic": output_dir / "daily_basic" / f"{symbol}.json.gz",
            "moneyflow": output_dir / "moneyflow" / f"{symbol}.json.gz",
            "fina_indicator": output_dir / "fina_indicator" / f"{symbol}.json.gz",
        }
        try:
            if not targets["daily_basic"].exists():
                rows = client.query("daily_basic", {"ts_code": code, "start_date": start_date, "end_date": end_date}, DAILY_BASIC_FIELDS)
                _write_gzip_json(targets["daily_basic"], rows)
                time.sleep(pause)
            if not targets["moneyflow"].exists():
                rows = client.query("moneyflow", {"ts_code": code, "start_date": start_date, "end_date": end_date}, MONEYFLOW_FIELDS)
                _write_gzip_json(targets["moneyflow"], rows)
                time.sleep(pause)
            if not targets["fina_indicator"].exists():
                rows = client.query("fina_indicator", {"ts_code": code, "start_date": start_date, "end_date": end_date}, FINANCIAL_FIELDS)
                _write_gzip_json(targets["fina_indicator"], rows)
                time.sleep(pause)
            completed += 1
        except Exception as exc:
            failed.append({"ts_code": code, "error": str(exc)})
        if index % 25 == 0 or index == len(universe):
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "progress.json").write_text(json.dumps({"completed": completed, "failed": failed, "total": len(universe), "updated_at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {"start_date": start_date, "end_date": end_date, "symbols": len(universe), "completed": completed, "failed": failed}
    (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata
