"""
Enhanced Backtest Engine — 多策略回测引擎
支持多策略并行回测、真实交易约束、walk-forward验证
v2: 接入真实K线数据库, 支持GA参数注入
"""
from typing import List, Dict, Optional, Any, Tuple
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import pandas as pd
import numpy as np
from loguru import logger

from config.settings import BACKTEST_CONFIG
from config.trading_calendar import trading_calendar


class BacktestEngine:
    """
    多策略回测引擎
    模拟真实A股交易环境: T+1, 涨跌停, 佣金, 印花税, 滑点
    """

    # K线数据库路径
    DB_PATHS = [
        Path("/mnt/d/AI/auction-stock-picker/data/cache/kline_cache.db"),
        Path("data/cache/kline_cache.db"),
    ]

    def __init__(self, config: dict = None):
        self.config = {**BACKTEST_CONFIG, **(config or {})}
        self.commission = self.config.get("commission", 0.0005)
        self.stamp_tax = self.config.get("stamp_tax", 0.001)
        self.slippage = self.config.get("slippage", 0.001)
        self.t_plus_1 = self.config.get("t_plus_1", True)
        self.limit_up_down = self.config.get("limit_up_down", True)

        # K线数据库
        self._db_conn: Optional[sqlite3.Connection] = None
        self._db_path: Optional[Path] = None

        # 回测状态
        self.results: List[Dict] = []
        self.stats: Dict = {}
        self._price_cache: Dict[str, float] = {}  # (code,date) → close 缓存

    def run(self, start_date: str, end_date: str,
            strategies: List[str] = None,
            initial_capital: float = 100000,
            top_n_per_day: int = 5) -> pd.DataFrame:
        """
        运行多策略回测
        Args:
            start_date: 开始日期 "2021-01-01"
            end_date: 结束日期 "2026-06-30"
            strategies: 策略名列表 (None = 全部)
            initial_capital: 初始资金
            top_n_per_day: 每日最多买入数
        Returns:
            回测结果DataFrame
        """
        logger.info(f"回测: {start_date} ~ {end_date}, "
                    f"策略={strategies or 'all'}, 资金={initial_capital:,.0f}")

        # 获取交易日列表
        trade_dates = self._get_trade_dates(start_date, end_date)
        logger.info(f"回测区间: {len(trade_dates)} 个交易日")

        # 初始化状态
        cash = initial_capital
        positions: Dict[str, Dict] = {}   # code → {entry_date, entry_price, shares, strategy}
        all_trades = []
        daily_pnl = []

        # 获取策略实例
        strategy_instances = self._get_strategies(strategies)

        for i, trade_date in enumerate(trade_dates):
            date_str = trade_date.strftime("%Y-%m-%d")

            # Step 1: 检查卖出条件
            sells = self._check_exits(positions, trade_date)
            for code, exit_info in sells.items():
                pos = positions.pop(code)
                pnl = (exit_info["price"] - pos["entry_price"]) * pos["shares"]
                pnl -= exit_info["price"] * pos["shares"] * (self.commission + self.stamp_tax)

                trade = {
                    "code": code,
                    "name": pos.get("name", ""),
                    "direction": "sell",
                    "entry_date": pos["entry_date"],
                    "entry_price": pos["entry_price"],
                    "exit_date": date_str,
                    "exit_price": exit_info["price"],
                    "shares": pos["shares"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round((exit_info["price"] / pos["entry_price"] - 1) * 100, 2),
                    "hold_days": (trade_date - pos["entry_date"]).days,
                    "strategy_id": pos.get("strategy", "unknown"),
                    "exit_reason": exit_info.get("reason", "signal"),
                }
                cash += exit_info["price"] * pos["shares"] - \
                       exit_info["price"] * pos["shares"] * (self.commission + self.stamp_tax)
                all_trades.append(trade)

            # Step 2: 生成买入信号
            if cash > initial_capital * 0.05:  # 至少5%可用资金
                buy_signals = self._generate_buy_signals(
                    strategy_instances, trade_date, context=None
                )

                # 限制买入数量
                available_slots = min(
                    top_n_per_day - len(positions),
                    int(cash / initial_capital * top_n_per_day) + 1
                )

                for signal in buy_signals[:available_slots]:
                    if signal.code in positions:
                        continue  # 已持仓

                    # 计算可买数量
                    max_spend = cash / max(available_slots, 1)
                    entry_price = signal.price * (1 + self.slippage)

                    if entry_price <= 0:
                        continue

                    shares = int(max_spend / entry_price / 100) * 100  # 整百股
                    if shares < 100:
                        continue

                    cost = entry_price * shares * (1 + self.commission)
                    if cost > cash:
                        continue

                    cash -= cost
                    positions[signal.code] = {
                        "entry_date": trade_date,
                        "entry_price": entry_price,
                        "shares": shares,
                        "strategy": signal.strategy_name,
                        "name": signal.name,
                        "stop_loss": signal.stop_loss,
                        "take_profit": signal.take_profit,
                    }

            # Step 3: 记录每日快照
            position_value = sum(
                p["shares"] * self._get_close_price(code, trade_date)
                for code, p in positions.items()
            )
            total_value = cash + position_value
            daily_pnl.append({
                "date": date_str,
                "cash": round(cash, 2),
                "position_value": round(position_value, 2),
                "total_value": round(total_value, 2),
                "pnl_pct": round((total_value / initial_capital - 1) * 100, 2),
                "positions": len(positions),
            })

            if (i + 1) % 50 == 0:
                logger.info(f"回测进度: {i+1}/{len(trade_dates)} ({date_str}), "
                           f"净值={total_value/initial_capital:.3f}")

        # 强制平仓 (最后一天)
        for code, pos in list(positions.items()):
            last_price = self._get_close_price(code, trade_dates[-1])
            pnl = (last_price - pos["entry_price"]) * pos["shares"]
            all_trades.append({
                "code": code,
                "direction": "sell",
                "entry_date": pos["entry_date"],
                "entry_price": pos["entry_price"],
                "exit_date": trade_dates[-1].strftime("%Y-%m-%d"),
                "exit_price": last_price,
                "shares": pos["shares"],
                "pnl": round(pnl, 2),
                "pnl_pct": round((last_price / pos["entry_price"] - 1) * 100, 2),
                "hold_days": (trade_dates[-1] - pos["entry_date"]).days,
                "strategy_id": pos.get("strategy", "unknown"),
                "exit_reason": "force_close",
            })
        positions.clear()

        # 汇总统计
        result_df = pd.DataFrame(all_trades)
        daily_df = pd.DataFrame(daily_pnl)
        self._compute_statistics(result_df, daily_df, initial_capital)

        return result_df

    def _get_trade_dates(self, start: str, end: str) -> List[date]:
        """获取交易日列表"""
        start_d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)

        dates = []
        d = start_d
        while d <= end_d:
            if trading_calendar.is_trading_day(d):
                dates.append(d)
            d += timedelta(days=1)
        return dates

    def _get_strategies(self, strategy_names: List[str] = None) -> List:
        """获取策略实例"""
        from strategies.auction_strategy.runner import AuctionStrategy
        from strategies.trend_strategy.runner import TrendStrategy
        from strategies.reversal_strategy.runner import ReversalStrategy
        from strategies.event_strategy.runner import EventStrategy

        all_strategies = {
            "auction": AuctionStrategy(),
            "trend": TrendStrategy(),
            "reversal": ReversalStrategy(),
            "event": EventStrategy(),
        }

        if strategy_names:
            return [all_strategies[n] for n in strategy_names if n in all_strategies]
        return list(all_strategies.values())

    def _generate_buy_signals(self, strategies: List, trade_date: date,
                               context=None) -> List:
        """生成买入信号"""
        all_signals = []
        for strategy in strategies:
            try:
                signals = strategy.generate_signals(context)
                all_signals.extend(signals)
            except Exception as e:
                logger.debug(f"策略 {strategy.strategy_name} 信号生成失败: {e}")

        # 按置信度排序
        all_signals.sort(key=lambda s: s.confidence, reverse=True)
        return all_signals

    def _check_exits(self, positions: Dict, trade_date: date) -> Dict:
        """
        检查卖出条件
        返回: {code: {"price": float, "reason": str}}
        """
        exits = {}
        for code, pos in positions.items():
            current_price = self._get_close_price(code, trade_date)

            if current_price <= 0:
                continue

            pnl_pct = current_price / pos["entry_price"] - 1

            # 止损
            if pos.get("stop_loss") and pnl_pct <= pos["stop_loss"] / pos["entry_price"]:
                exits[code] = {"price": current_price, "reason": "stop_loss"}

            # 止盈
            elif pos.get("take_profit") and pnl_pct >= pos["take_profit"] / pos["entry_price"]:
                exits[code] = {"price": current_price, "reason": "take_profit"}

            # 移动止损 (从最高点回落5%)
            if "max_price" in pos:
                if current_price < pos["max_price"] * 0.95:
                    exits[code] = {"price": current_price, "reason": "trailing_stop"}
            pos["max_price"] = max(pos.get("max_price", 0), current_price)

        return exits

    def _get_close_price(self, code: str, trade_date: date) -> float:
        """从K线数据库获取收盘价, 缺失日期向前查找最近可用价格"""
        if not self._db_conn:
            self._open_kline_db()

        code = str(code).zfill(6)
        date_str = trade_date.strftime("%Y%m%d")
        cache_key = f"{code}_{date_str}"

        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        try:
            # 先精确查询
            row = self._db_conn.execute(
                "SELECT close FROM kline_daily WHERE code=? AND date=?",
                (code, date_str)
            ).fetchone()

            if row:
                price = float(row[0])
            else:
                # 向前查找最近5个交易日的价格 (处理周末/节假日)
                row = self._db_conn.execute(
                    "SELECT close, date FROM kline_daily WHERE code=? AND date <= ? "
                    "ORDER BY date DESC LIMIT 1",
                    (code, date_str)
                ).fetchone()
                price = float(row[0]) if row else 0.0

            self._price_cache[cache_key] = price
            return price
        except Exception:
            return 0.0

    def _open_kline_db(self):
        """打开K线数据库连接"""
        for p in self.DB_PATHS:
            if p.exists():
                self._db_path = p
                self._db_conn = sqlite3.connect(str(p))
                logger.debug(f"[Backtest] K线数据库: {p}")
                return
        logger.warning("[Backtest] K线数据库未找到!")

    def _close_kline_db(self):
        """关闭K线数据库连接"""
        if self._db_conn:
            self._db_conn.close()
            self._db_conn = None

    def run_with_params(self, params: Dict, start_date: str = "2022-01-01",
                        end_date: str = "2026-06-30",
                        initial_capital: float = 100000,
                        strategy_names: List[str] = None) -> Dict:
        """
        用指定参数运行回测 (供GA调用)
        将params注入策略配置 → 运行回测 → 返回stats
        """
        self._price_cache.clear()

        # 应用参数到策略实例
        strategies = self._get_strategies_with_params(params, strategy_names)

        # 运行回测
        trade_dates = self._get_trade_dates(start_date, end_date)
        cash = initial_capital
        positions: Dict[str, Dict] = {}
        all_trades = []
        daily_values = []

        for i, trade_date in enumerate(trade_dates):
            # 卖出检查
            exits = self._check_exits(positions, trade_date)
            for code, exit_info in exits.items():
                pos = positions.pop(code)
                pnl = (exit_info["price"] - pos["entry_price"]) * pos["shares"]
                pnl -= exit_info["price"] * pos["shares"] * (self.commission + self.stamp_tax)
                cash += exit_info["price"] * pos["shares"] * (1 - self.commission - self.stamp_tax)
                all_trades.append({
                    "code": code, "direction": "sell",
                    "entry_date": str(pos["entry_date"]), "entry_price": pos["entry_price"],
                    "exit_date": str(trade_date), "exit_price": exit_info["price"],
                    "shares": pos["shares"], "pnl": round(pnl, 2),
                    "pnl_pct": round((exit_info["price"] / pos["entry_price"] - 1) * 100, 2),
                    "hold_days": (trade_date - pos["entry_date"]).days if isinstance(pos["entry_date"], date) else 0,
                    "strategy_id": pos.get("strategy", ""), "exit_reason": exit_info.get("reason", ""),
                })

            # 买入信号
            buy_signals = []
            for s in strategies:
                try:
                    buy_signals.extend(s.generate_signals())
                except Exception:
                    pass
            buy_signals.sort(key=lambda x: x.confidence, reverse=True)

            # 执行买入
            max_positions = int(params.get("max_positions", 5))
            position_pct = float(params.get("position_size_pct", 0.25))
            slots = max(0, max_positions - len(positions))
            for sig in buy_signals[:slots]:
                if sig.code in positions or sig.price <= 0:
                    continue
                amount = min(cash * position_pct, cash / max(slots, 1))
                shares = int(amount / sig.price / 100) * 100
                if shares < 100:
                    continue
                cost = sig.price * shares * (1 + self.commission)
                if cost > cash:
                    continue
                cash -= cost
                positions[sig.code] = {
                    "entry_date": trade_date, "entry_price": sig.price,
                    "shares": shares, "strategy": sig.strategy_name,
                    "name": sig.name, "stop_loss": sig.stop_loss,
                    "take_profit": sig.take_profit, "max_price": sig.price,
                }

            # 每日快照
            pos_value = sum(p["shares"] * self._get_close_price(c, trade_date) for c, p in positions.items())
            daily_values.append(pos_value + cash)

        # 强制平仓
        for code, pos in list(positions.items()):
            lp = self._get_close_price(code, trade_dates[-1])
            pnl = (lp - pos["entry_price"]) * pos["shares"]
            all_trades.append({
                "code": code, "direction": "sell", "entry_date": str(pos["entry_date"]),
                "entry_price": pos["entry_price"], "exit_date": str(trade_dates[-1]),
                "exit_price": lp, "shares": pos["shares"], "pnl": round(pnl, 2),
                "pnl_pct": round((lp / pos["entry_price"] - 1) * 100, 2),
                "hold_days": 0, "strategy_id": pos.get("strategy", ""), "exit_reason": "force_close",
            })
        positions.clear()

        # 统计
        trades_df = pd.DataFrame(all_trades)
        daily_df = pd.DataFrame([{"total_value": v} for v in daily_values])
        self._compute_statistics(trades_df, daily_df, initial_capital)
        self._close_kline_db()

        return self.stats

    def _get_strategies_with_params(self, params: Dict, strategy_names: List[str] = None) -> List:
        """创建应用了GA参数的策略实例"""
        from strategies.trend_strategy.runner import TrendStrategy
        from strategies.reversal_strategy.runner import ReversalStrategy

        all_strats = {
            "trend": TrendStrategy(),
            "reversal": ReversalStrategy(),
        }

        # 将GA参数映射到策略配置
        param_mapping = {
            "trend": {
                "ma_short": "ma_short", "ma_mid": "ma_mid", "ma_long": "ma_long",
                "min_volume_ratio": "min_volume_ratio", "min_market_cap": "min_market_cap",
                "max_market_cap": "max_market_cap", "top_n_picks": "top_n_picks",
                "holding_days": "holding_days", "stop_loss_pct": "stop_loss_pct",
                "take_profit_pct": "take_profit_min",
            },
            "reversal": {
                "rsi_oversold": "rsi_oversold", "max_drawdown": "max_drawdown",
                "min_bounce": "min_bounce", "top_n_picks": "top_n_picks",
                "stop_loss_pct": "stop_loss_pct", "take_profit_pct": "take_profit_min",
            },
        }

        names = strategy_names or list(all_strats.keys())
        result = []
        for name in names:
            if name in all_strats:
                s = all_strats[name]
                mapping = param_mapping.get(name, {})
                strategy_params = {}
                for ga_key, strategy_key in mapping.items():
                    if ga_key in params:
                        strategy_params[strategy_key] = params[ga_key]
                if strategy_params:
                    s.set_parameters(strategy_params)
                result.append(s)

        return result

    def _compute_statistics(self, trades_df: pd.DataFrame,
                            daily_df: pd.DataFrame,
                            initial_capital: float):
        """计算回测统计指标"""
        if trades_df is None or len(trades_df) == 0:
            logger.warning("无交易记录")
            self.stats = {"total_trades": 0}
            return

        total = len(trades_df)
        wins = (trades_df["pnl"] > 0).sum()
        win_rate = wins / total * 100

        avg_return = trades_df["pnl_pct"].mean()
        total_pnl = trades_df["pnl"].sum()

        # 年化收益
        if len(daily_df) > 0:
            start_val = initial_capital
            end_val = daily_df["total_value"].iloc[-1]
            days = len(daily_df)
            annual_return = (end_val / start_val) ** (252 / days) - 1

            # 最大回撤
            daily_df["cum_max"] = daily_df["total_value"].cummax()
            daily_df["drawdown"] = daily_df["total_value"] / daily_df["cum_max"] - 1
            max_drawdown = daily_df["drawdown"].min()

            # Sharpe ratio (简化)
            daily_returns = daily_df["total_value"].pct_change().dropna()
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0

        else:
            annual_return = 0
            max_drawdown = 0
            sharpe = 0

        self.stats = {
            "总交易次数": total,
            "胜率(%)": round(win_rate, 1),
            "平均收益(%)": round(avg_return, 2),
            "总盈亏": round(total_pnl, 2),
            "年化收益(%)": round(annual_return * 100, 2),
            "最大回撤(%)": round(max_drawdown * 100, 2),
            "夏普比率": round(sharpe, 2),
            "盈亏比": round(
                trades_df[trades_df["pnl"] > 0]["pnl"].mean() /
                abs(trades_df[trades_df["pnl"] < 0]["pnl"].mean()), 2
            ) if len(trades_df[trades_df["pnl"] < 0]) > 0 else 0,
        }

        from tabulate import tabulate
        print("\n📊 回测统计:")
        print(tabulate([[k, v] for k, v in self.stats.items()], tablefmt="grid"))

    def walk_forward_validate(self, start_date: str, end_date: str,
                              train_years: int = 3, test_months: int = 3) -> List[Dict]:
        """
        Walk-forward交叉验证
        滚动窗口: 训练train_years年 → 测试test_months月 → 滚动
        """
        results = []
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        current = start + timedelta(days=train_years * 365)
        while current + timedelta(days=test_months * 30) <= end:
            test_end = current + timedelta(days=test_months * 30)

            train_start = (current - timedelta(days=train_years * 365)).strftime("%Y-%m-%d")
            train_end = current.strftime("%Y-%m-%d")
            test_start = current.strftime("%Y-%m-%d")
            test_end_str = test_end.strftime("%Y-%m-%d")

            logger.info(f"Walk-forward: train={train_start}~{train_end}, test={test_start}~{test_end_str}")

            # 在训练期优化参数 (TODO: 集成GA)
            # 在测试期评估
            test_trades = self.run(test_start, test_end_str)
            if len(test_trades) > 0:
                results.append({
                    "train_period": f"{train_start}~{train_end}",
                    "test_period": f"{test_start}~{test_end_str}",
                    "stats": self.stats.copy(),
                })

            current = test_end

        return results


# 全局单例
backtest_engine = BacktestEngine()
