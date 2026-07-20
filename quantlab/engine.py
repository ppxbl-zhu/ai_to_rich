from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Bar:
    date: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def load_bars(path: Path) -> dict[str, list[Bar]]:
    grouped: dict[str, list[Bar]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            bar = Bar(row["date"], row["symbol"], *[float(row[k]) for k in ("open", "high", "low", "close", "volume")])
            grouped.setdefault(bar.symbol, []).append(bar)
    for bars in grouped.values():
        bars.sort(key=lambda x: x.date)
    return grouped


def momentum_score(bars: list[Bar], weights: tuple[float, float, float]) -> float:
    if len(bars) < 61 or bars[-21].close <= 0 or bars[-61].close <= 0:
        return -999.0
    ret20 = bars[-1].close / bars[-21].close - 1
    ret60 = bars[-1].close / bars[-61].close - 1
    recent = [math.log(b.close / a.close) for a, b in zip(bars[-21:-1], bars[-20:]) if a.close > 0]
    vol = math.sqrt(sum(x * x for x in recent) / max(1, len(recent)))
    liquidity = math.log1p(sum(b.close * b.volume for b in bars[-20:]) / 20)
    return weights[0] * ret20 + weights[1] * ret60 - weights[2] * vol + 0.0001 * liquidity


def evolve_weights(grouped: dict[str, list[Bar]], seed: int = 7, generations: int = 20) -> tuple[float, float, float]:
    """Small deterministic GA. Optimizes walk-forward rank correlation, not raw in-sample PnL."""
    rng = random.Random(seed)
    population = [(rng.uniform(.1, 1), rng.uniform(.1, 1), rng.uniform(.1, 2)) for _ in range(30)]

    def fitness(w: tuple[float, float, float]) -> float:
        observations = []
        for bars in grouped.values():
            for i in range(80, len(bars) - 6, 20):
                score = momentum_score(bars[:i], w)
                future = bars[i + 5].close / bars[i].close - 1
                observations.append((score, future))
        if len(observations) < 10:
            return -999.0
        observations.sort()
        q = max(1, len(observations) // 5)
        spread = sum(x[1] for x in observations[-q:]) / q - sum(x[1] for x in observations[:q]) / q
        complexity = .002 * sum(abs(x) for x in w)
        return spread - complexity

    for _ in range(generations):
        elite = sorted(population, key=fitness, reverse=True)[:8]
        population = elite[:]
        while len(population) < 30:
            a, b = rng.sample(elite, 2)
            child = tuple(max(.01, (x + y) / 2 + rng.gauss(0, .08)) for x, y in zip(a, b))
            population.append(child)
    return max(population, key=fitness)


def run_paper(config_path: Path, data_path: Path, state_dir: Path, report_dir: Path) -> Path:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    grouped = load_bars(data_path)
    common_dates = sorted(set.intersection(*(set(b.date for b in bars) for bars in grouped.values())))
    if len(common_dates) < 90:
        raise ValueError("至少需要90个共同交易日，且演示数据不能用于收益评价")
    weights = evolve_weights(grouped)
    signal_date = common_dates[-2]
    trade_date = common_dates[-1]
    histories = {s: [b for b in bars if b.date <= signal_date] for s, bars in grouped.items()}
    ranked = sorted(((momentum_score(b, weights), s) for s, b in histories.items()), reverse=True)

    state_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "portfolio.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"cash": cfg["initial_cash"], "peak": cfg["initial_cash"], "positions": {}, "last_date": None}
    if state["last_date"] == trade_date:
        return report_dir / f"{trade_date}.md"

    opens = {s: next(b.open for b in bars if b.date == trade_date) for s, bars in grouped.items()}
    equity = state["cash"] + sum(p["shares"] * opens.get(s, p["last_price"]) for s, p in state["positions"].items())
    state["peak"] = max(state["peak"], equity)
    drawdown = 1 - equity / state["peak"]
    target_count = 0 if drawdown >= cfg["halt_drawdown"] else (2 if drawdown >= cfg["defensive_drawdown"] else cfg["max_positions"])
    selected = [s for score, s in ranked if score > -900][:target_count]

    trades = []
    for symbol in list(state["positions"]):
        if symbol not in selected:
            p = state["positions"].pop(symbol)
            px = opens[symbol] * (1 - cfg["slippage_rate"])
            gross = p["shares"] * px
            fee = max(cfg["minimum_commission"], gross * cfg["commission_rate"]) + gross * cfg["stamp_duty_sell"]
            state["cash"] += gross - fee
            trades.append(f"卖出 {symbol} {p['shares']}股 @ {px:.2f}")

    budget = equity * cfg["initial_position_weight"]
    for symbol in selected:
        if symbol in state["positions"]:
            continue
        px = opens[symbol] * (1 + cfg["slippage_rate"])
        shares = int(budget / px / cfg["lot_size"]) * cfg["lot_size"]
        gross = shares * px
        fee = max(cfg["minimum_commission"], gross * cfg["commission_rate"]) if shares else 0
        if shares and gross + fee <= state["cash"]:
            state["cash"] -= gross + fee
            state["positions"][symbol] = {"shares": shares, "cost": px, "last_price": px}
            trades.append(f"买入 {symbol} {shares}股 @ {px:.2f}")
    for symbol, p in state["positions"].items():
        p["last_price"] = opens.get(symbol, p["last_price"])
    state["last_date"] = trade_date
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [f"# 模拟盘日报 {trade_date}", "", f"- 信号日期：{signal_date}", f"- 模拟权益：{equity:.2f}元", f"- 当前回撤：{drawdown:.2%}", f"- 现金：{state['cash']:.2f}元", f"- GA权重：{tuple(round(x, 4) for x in weights)}", "", "## 模拟成交", ""]
    report.extend([f"- {x}" for x in trades] or ["- 无"])
    report.extend(["", "## 当前持仓", ""])
    report.extend([f"- {s}: {p['shares']}股，模拟成本 {p['cost']:.2f}" for s, p in state["positions"].items()] or ["- 空仓"])
    report.extend(["", "> 仅用于模型训练和模拟验证，不构成实盘投资建议。"])
    out = report_dir / f"{trade_date}.md"
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    return out


def make_demo(path: Path, days: int = 180) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(11)
    symbols = ["600000", "600036", "600519", "000001", "000333", "000651", "300750", "002594"]
    start = date(2025, 1, 2)
    rows = []
    for n, symbol in enumerate(symbols):
        px = 8 + n * 7
        d, count = start, 0
        while count < days:
            if d.weekday() < 5:
                change = rng.gauss(.0002 + n * .00005, .015)
                op = px * (1 + rng.gauss(0, .003))
                close = max(.5, px * (1 + change))
                rows.append(Bar(d.isoformat(), symbol, op, max(op, close) * 1.005, min(op, close) * .995, close, rng.randint(2_000_000, 20_000_000)))
                px, count = close, count + 1
            d += timedelta(days=1)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(x) for x in rows)
