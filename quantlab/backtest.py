from __future__ import annotations

import json
import math
import statistics
import random
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .engine import Bar, evolve_weights, load_bars, load_industries, load_names, momentum_score
from .trend import main_rise_setup


@dataclass
class BacktestMetrics:
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe: float
    win_rate: float
    profit_factor: float
    trades: int
    final_equity: float


def chronological_split(dates: list[str], train_ratio: float = .60, validation_ratio: float = .20) -> tuple[list[str], list[str], list[str]]:
    if len(dates) < 250:
        raise ValueError("backtest requires at least 250 common trading days")
    train_end = max(1, int(len(dates) * train_ratio))
    validation_end = max(train_end + 1, int(len(dates) * (train_ratio + validation_ratio)))
    return dates[:train_end], dates[train_end:validation_end], dates[validation_end:]


def calculate_metrics(equity_curve: list[float], closed_pnls: list[float], initial_cash: float) -> BacktestMetrics:
    if not equity_curve:
        return BacktestMetrics(0, 0, 0, 0, 0, 0, 0, initial_cash)
    total = equity_curve[-1] / initial_cash - 1
    years = max(1 / 252, len(equity_curve) / 252)
    annual = (equity_curve[-1] / initial_cash) ** (1 / years) - 1 if equity_curve[-1] > 0 else -1
    peak, max_dd = equity_curve[0], 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_dd = max(max_dd, 1 - value / peak) if peak else 1.0
    returns = [b / a - 1 for a, b in zip(equity_curve, equity_curve[1:]) if a > 0]
    sharpe = statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(252) if len(returns) > 1 and statistics.stdev(returns) else 0.0
    wins = [p for p in closed_pnls if p > 0]
    losses = [p for p in closed_pnls if p <= 0]
    win_rate = len(wins) / len(closed_pnls) if closed_pnls else 0.0
    profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) else (float("inf") if wins else 0.0)
    return BacktestMetrics(total, annual, max_dd, sharpe, win_rate, profit_factor, len(closed_pnls), equity_curve[-1])


def _fee(value: float, cfg: dict, sell: bool = False) -> float:
    return max(cfg.get("minimum_commission", 5.0), value * cfg.get("commission_rate", .0003)) + (value * cfg.get("stamp_duty_sell", .0005) if sell else 0)


def _common_dates(grouped: dict[str, list[Bar]]) -> list[str]:
    coverage: dict[str, int] = {}
    for bars in grouped.values():
        for bar in bars:
            coverage[bar.date] = coverage.get(bar.date, 0) + 1
    threshold = max(1, math.ceil(len(grouped) * .70))
    return sorted(day for day, count in coverage.items() if count >= threshold)


def _simulate(grouped: dict[str, list[Bar]], industries: dict[str, str], dates: list[str], weights: tuple[float, float, float], params: dict, cfg: dict) -> tuple[BacktestMetrics, list[float]]:
    cfg = {**cfg, **{k: v for k, v in params.items() if k in cfg}}
    setup_weight = params["setup_weight"]
    sector_weight = params["sector_weight"]
    setup_threshold = params.get("setup_threshold", 0.0)
    indices = {symbol: {bar.date: i for i, bar in enumerate(bars)} for symbol, bars in grouped.items()}
    bars_by_date = {symbol: {bar.date: bar for bar in bars} for symbol, bars in grouped.items()}
    cash = float(cfg["initial_cash"])
    positions: dict[str, dict] = {}
    curve, pnls = [], []
    peak = cash
    rebalance_days = max(1, int(cfg.get("backtest_rebalance_days", 5)))
    lot = int(cfg.get("lot_size", 100))
    slippage = cfg.get("slippage_rate", .001)

    for day_index, day in enumerate(dates):
        todays = {s: table[day] for s, table in bars_by_date.items() if day in table}
        # Decisions use only information available before today's open.
        if day_index and day_index % rebalance_days == 0:
            signals, sector_values = {}, {}
            for symbol in todays:
                idx = indices[symbol][day]
                history = grouped[symbol][:idx]
                if len(history) < 80:
                    continue
                base = momentum_score(history, weights)
                setup = main_rise_setup(history)
                if base <= -900 or setup.score <= setup_threshold:
                    continue
                signals[symbol] = (base, setup.score)
                sector_values.setdefault(industries.get(symbol, "unknown"), []).append(base)
            sector_scores = {k: statistics.mean(v) for k, v in sector_values.items() if len(v) >= 2}
            ranked = sorted(signals, key=lambda s: signals[s][0] + setup_weight * signals[s][1] + sector_weight * sector_scores.get(industries.get(s, "unknown"), 0), reverse=True)
            current_equity = cash + sum(p["shares"] * todays.get(s, grouped[s][-1]).open for s, p in positions.items())
            peak = max(peak, current_equity)
            drawdown = 1 - current_equity / peak
            count = cfg["max_positions"]
            breadth_samples = []
            for symbol in todays:
                idx = indices[symbol][day]
                history = grouped[symbol][:idx]
                if len(history) >= 21:
                    breadth_samples.append(history[-1].close > statistics.mean(b.close for b in history[-20:]))
            breadth = sum(breadth_samples) / len(breadth_samples) if breadth_samples else 0
            if breadth < params.get("breadth_min", 0.0): count = 0
            if drawdown >= cfg.get("halt_drawdown", .20): count = 0
            elif drawdown >= cfg.get("defensive_drawdown", .15): count = min(2, count)
            elif drawdown >= cfg.get("risk_reduce_drawdown", .10): count = max(1, round(count * cfg.get("risk_reduce_exposure", .6)))
            selected, sectors = [], {}
            for symbol in ranked:
                sector = industries.get(symbol, "unknown")
                if sectors.get(sector, 0) >= cfg.get("max_sector_positions", 2):
                    continue
                selected.append(symbol); sectors[sector] = sectors.get(sector, 0) + 1
                if len(selected) >= count: break

            for symbol in list(positions):
                if symbol not in selected and symbol in todays:
                    price = todays[symbol].open * (1 - slippage)
                    value = positions[symbol]["shares"] * price
                    cash += value - _fee(value, cfg, True)
                    pnls.append(value - _fee(value, cfg, True) - positions[symbol]["invested"])
                    del positions[symbol]
            budget = current_equity * cfg.get("initial_position_weight", .10)
            for symbol in selected:
                if symbol in positions or symbol not in todays: continue
                price = todays[symbol].open * (1 + slippage)
                shares = math.floor(min(budget, cash) / price / lot) * lot
                value = shares * price
                fee = _fee(value, cfg)
                if shares > 0 and value + fee <= cash:
                    cash -= value + fee
                    positions[symbol] = {"shares": shares, "cost": price, "high": price, "invested": value + fee}

        # Stops are conservatively executed at the worse of stop price and open.
        for symbol in list(positions):
            if symbol not in todays: continue
            bar, p = todays[symbol], positions[symbol]
            p["high"] = max(p["high"], bar.high)
            hard = p["cost"] * (1 - cfg.get("hard_stop_loss", .08))
            trailing = p["high"] * (1 - cfg.get("trailing_stop", .08)) if p["high"] >= p["cost"] * (1 + cfg.get("trailing_activation", .05)) else 0
            stop = max(hard, trailing)
            if bar.low <= stop:
                price = min(bar.open, stop) * (1 - slippage)
                value = p["shares"] * price
                cash += value - _fee(value, cfg, True)
                pnls.append(value - _fee(value, cfg, True) - p["invested"])
                del positions[symbol]
        close_equity = cash + sum(p["shares"] * todays[s].close for s, p in positions.items() if s in todays)
        curve.append(close_equity)

    if dates:
        last = dates[-1]
        for symbol in list(positions):
            bar = bars_by_date[symbol].get(last)
            if not bar: continue
            p = positions.pop(symbol); value = p["shares"] * bar.close * (1 - slippage)
            sell_fee = _fee(value, cfg, True)
            cash += value - sell_fee; pnls.append(value - sell_fee - p["invested"])
        if curve: curve[-1] = cash
    return calculate_metrics(curve, pnls, float(cfg["initial_cash"])), curve


def _score(metrics: BacktestMetrics) -> float:
    return metrics.annualized_return + .12 * metrics.sharpe - 1.5 * metrics.max_drawdown


def optimize_parameters(grouped: dict[str, list[Bar]], industries: dict[str, str], validation: list[str], weights: tuple[float, float, float], cfg: dict, seed: int = 29, incumbent_params: dict | None = None) -> list[dict]:
    """Deterministic evolutionary search scored on two sequential validation folds."""
    rng = random.Random(seed)
    spaces = {
        "setup_weight": [.35, .50, .65, .80],
        "sector_weight": [.10, .20, .30, .40],
        "setup_threshold": [.0, .15, .30, .45],
        "breadth_min": [.0, .35, .45, .55],
        "backtest_rebalance_days": [3, 5, 10, 15],
        # Risk policy is a hard ceiling, not a parameter the optimizer may loosen.
        "initial_position_weight": [.05, .08, min(.10, cfg.get("initial_position_weight", .10))],
        "hard_stop_loss": [.05, .07, min(.08, cfg.get("hard_stop_loss", .08))],
        "trailing_stop": [.05, .07, min(.08, cfg.get("trailing_stop", .08))],
    }
    midpoint = len(validation) // 2
    folds = [validation[:midpoint], validation[midpoint:]]
    population = [{key: rng.choice(values) for key, values in spaces.items()} for _ in range(12)]
    population.append({"setup_weight": .50, "sector_weight": .25, "setup_threshold": 0, "breadth_min": 0, "backtest_rebalance_days": 5, "initial_position_weight": .10, "hard_stop_loss": .08, "trailing_stop": .08})
    if incumbent_params and all(key in incumbent_params and incumbent_params[key] in values for key, values in spaces.items()):
        population.append({key: incumbent_params[key] for key in spaces})
    evaluated: dict[str, dict] = {}
    for generation in range(3):
        for params in population:
            key = json.dumps(params, sort_keys=True)
            if key in evaluated: continue
            fold_metrics = [_simulate(grouped, industries, fold, weights, params, cfg)[0] for fold in folds]
            scores = [_score(metric) for metric in fold_metrics]
            stability_penalty = statistics.pstdev(scores) if len(scores) > 1 else 0
            evaluated[key] = {**params, "score": statistics.mean(scores) - .35 * stability_penalty, "folds": [asdict(m) for m in fold_metrics], "generation": generation}
        elite = sorted(evaluated.values(), key=lambda item: item["score"], reverse=True)[:5]
        population = []
        for _ in range(12):
            child = {key: elite[rng.randrange(len(elite))][key] for key in spaces}
            for key, values in spaces.items():
                if rng.random() < .30: child[key] = rng.choice(values)
            population.append(child)
    return sorted(evaluated.values(), key=lambda item: item["score"], reverse=True)


def run_backtest(config_path: Path, data_path: Path, state_dir: Path, report_dir: Path) -> Path:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    grouped, names, industries = load_bars(data_path), load_names(data_path), load_industries(data_path)
    grouped = {s: b for s, b in grouped.items() if "ST" not in names.get(s, "").upper().replace(" ", "") and len(b) >= 250}
    dates = _common_dates(grouped)
    train, validation, test = chronological_split(dates, cfg.get("backtest_train_ratio", .60), cfg.get("backtest_validation_ratio", .20))
    train_dates = set(train)
    train_set = {s: [b for b in bars if b.date in train_dates] for s, bars in grouped.items()}
    weights = evolve_weights(train_set, generations=12)
    model_path = state_dir / "models" / "backtest_champion.json"
    incumbent = json.loads(model_path.read_text(encoding="utf-8")) if model_path.exists() else None
    search_state_path = state_dir / "models" / "backtest_search_state.json"
    search_state = json.loads(search_state_path.read_text(encoding="utf-8")) if search_state_path.exists() else {"iteration": 1 if incumbent else 0}
    iteration = int(search_state.get("iteration", 0)) + 1
    search_seed = 29 + (iteration - 1) * 7919
    candidates = optimize_parameters(grouped, industries, validation, weights, cfg, search_seed, incumbent.get("parameters") if incumbent else None)
    winner = candidates[0]
    winner_params = {key: winner[key] for key in ("setup_weight", "sector_weight", "setup_threshold", "breadth_min", "backtest_rebalance_days", "initial_position_weight", "hard_stop_loss", "trailing_stop")}
    validation_metrics, _ = _simulate(grouped, industries, validation, weights, winner_params, cfg)
    winner["validation"] = asdict(validation_metrics)
    incumbent_risk_valid = bool(incumbent) and incumbent.get("parameters", {}).get("initial_position_weight", 1) <= cfg.get("initial_position_weight", .10) and incumbent.get("parameters", {}).get("hard_stop_loss", 1) <= cfg.get("hard_stop_loss", .08) and incumbent.get("parameters", {}).get("trailing_stop", 1) <= cfg.get("trailing_stop", .08)
    incumbent_score = incumbent.get("validation_score", -999) if incumbent_risk_valid else -999
    promoted = incumbent is None or winner["score"] > incumbent_score + cfg.get("model_promotion_margin", .001)
    curve = []
    if promoted:
        test_metrics, curve = _simulate(grouped, industries, test, weights, winner_params, cfg)
        model = {"version": f"five-year-{date.today().isoformat()}-i{iteration}", "weights": list(weights), "parameters": winner_params, "validation": winner["validation"], "test": asdict(test_metrics), "split": {"train": [train[0], train[-1]], "validation": [validation[0], validation[-1]], "test": [test[0], test[-1]]}, "validation_score": winner["score"], "search_seed": search_seed}
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        model = incumbent
        test_metrics = BacktestMetrics(**incumbent["test"])
    search_state_path.write_text(json.dumps({"iteration": iteration, "last_seed": search_seed, "candidate_score": winner["score"], "champion_score": model["validation_score"], "promoted": promoted}, ensure_ascii=False, indent=2), encoding="utf-8")
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"backtest-{date.today().isoformat()}.md"
    m = test_metrics
    report.write_text(f"""# 五年历史回测\n\n- 样本：{len(grouped)} 只（已剔除当前名称含 ST 的股票），{dates[0]} 至 {dates[-1]}\n- 训练：{train[0]} 至 {train[-1]}\n- 双折验证选参：{validation[0]} 至 {validation[-1]}\n- 隔离测试：{test[0]} 至 {test[-1]}\n- 初始资金：{cfg['initial_cash']:,.0f} 元\n- 增量搜索：第 {iteration} 轮，种子 {search_seed}，候选 {len(candidates)} 组\n- 晋级：{'是' if promoted else '否，继续使用上一冠军'}\n- 本轮候选参数：{json.dumps(winner_params, ensure_ascii=False)}\n- 动量权重：{tuple(round(x, 4) for x in weights)}\n\n## 本轮验证结果\n\n- 总收益率：{validation_metrics.total_return:.2%}\n- 最大回撤：{validation_metrics.max_drawdown:.2%}\n- 胜率：{validation_metrics.win_rate:.2%}\n- 稳定性分数：{winner['score']:.4f}（原冠军 {incumbent_score:.4f}）\n\n## 当前冠军隔离测试结果\n\n- 总收益率：{m.total_return:.2%}\n- 年化收益率：{m.annualized_return:.2%}\n- 最大回撤：{m.max_drawdown:.2%}\n- Sharpe：{m.sharpe:.2f}\n- 完整交易：{m.trades}\n- 胜率：{m.win_rate:.2%}\n- 盈亏比：{m.profit_factor:.2f}\n- 期末权益：{m.final_equity:,.2f} 元\n\n## 口径与限制\n\n信号仅使用当时可见的收盘数据，下一交易日开盘成交；已计佣金、卖出印花税、滑点和100股整数手。当前版本使用今天仍上市且流动性靠前的股票池，存在幸存者偏差；历史 ST/退市状态和逐日涨跌停限制尚未完全点时还原，结果不能视为实盘收益承诺。自动迭代只依据双折验证成绩晋级；未晋级候选不会触碰隔离测试集。\n""", encoding="utf-8")
    report.with_suffix(".json").write_text(json.dumps({"model": model, "candidates": candidates, "equity_curve": curve}, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
