from pathlib import Path
import argparse
import json

from .engine import load_bars, make_demo, run_paper
from .market import update_market_csv, update_tushare_market_csv
from .notifier import publish_pushplus
from .realtime import monitor
from .tushare_client import TushareClient
from .backtest import run_backtest
from .feature_store import backfill_features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["demo", "fetch", "run", "daily", "monitor", "backtest", "features"])
    parser.add_argument("--interval", type=float, default=5, help="实时采样间隔（秒）")
    parser.add_argument("--minutes", type=float, default=240, help="监控持续时间（分钟）")
    parser.add_argument("--once", action="store_true", help="忽略交易时段，仅采集一次以便诊断")
    parser.add_argument("--feature-limit", type=int, default=0, help="辅助特征回填股票数，0表示固定训练池全部")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    data = root / "data" / ("demo_market.csv" if args.command == "demo" else "market.csv")
    if args.command == "demo":
        make_demo(data)
        print(f"演示数据已生成：{data}")
        return
    config_path = root / "config.json"
    if args.command == "features":
        bars = load_bars(root / "data" / "market.csv")
        dates = [bar.date for history in bars.values() for bar in history]
        metadata = backfill_features(TushareClient.from_environment(), root / "data" / "training_universe.json", root / "data" / "features", min(dates).replace("-", ""), max(dates).replace("-", ""), limit=args.feature_limit)
        print(json.dumps(metadata, ensure_ascii=False))
        return
    if args.command == "backtest":
        report = run_backtest(config_path, data, root / "state", root / "reports")
        print(report)
        return
    if args.command == "monitor":
        config = json.loads(config_path.read_text(encoding="utf-8"))
        roster_path = root / "data" / "universe.json"
        if roster_path.exists():
            symbols = sorted(row["ts_code"].split(".")[0] for row in json.loads(roster_path.read_text(encoding="utf-8")))
        else:
            symbols = sorted(load_bars(data)) if data.exists() else config["watchlist"]
        count = monitor(symbols, root / "data" / "realtime", args.interval, args.minutes, args.once)
        print(f"实时训练样本已保存：{count} 条")
        return
    if args.command in {"fetch", "daily"}:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config.get("data_source", "tushare") == "tushare":
            try:
                updated, metadata = update_tushare_market_csv(
                    TushareClient.from_environment(), data,
                    config.get("universe_size", 100), config.get("history_days", 500),
                    config.get("minimum_listing_days", 120), config.get("training_universe_size", 500),
                )
            except Exception:
                if not config.get("allow_public_fallback", True):
                    raise
                updated = update_market_csv(config["watchlist"], data, config.get("history_days", 500))
                metadata = {"source": "tencent-fallback", "universe_size": len(config["watchlist"])}
        else:
            updated = update_market_csv(config["watchlist"], data, config.get("history_days", 500))
            metadata = {"source": "tencent", "universe_size": len(config["watchlist"])}
        (root / "data" / "market.meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"行情已更新：{updated}；来源：{metadata['source']}；股票数：{metadata['universe_size']}")
        if args.command == "fetch":
            return
    report = run_paper(config_path, data, root / "state", root / "reports")
    print(report)
    if args.command == "daily":
        sent = publish_pushplus(f"A股模拟盘日报 {report.stem}", report.read_text(encoding="utf-8"))
        print("微信推送已发送" if sent else "未配置 PUSHPLUS_TOKEN，仅保存本地日报")


if __name__ == "__main__":
    main()
