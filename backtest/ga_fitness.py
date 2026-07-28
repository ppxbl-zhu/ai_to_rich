"""
GA Fitness Function — 多目标适应度计算
将回测结果转换为单一适应度分数, 供GA优化
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from loguru import logger

from config.genome_config import FITNESS_WEIGHTS


class GAFitness:
    """
    GA适应度计算器
    多目标加权 → 单一标量分数 (越大越好)
    """

    def __init__(self, weights: Dict[str, float] = None):
        self.weights = weights or FITNESS_WEIGHTS

    def compute(self, backtest_stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        从回测统计计算适应度
        Args:
            backtest_stats: 回测统计结果 {"sharpe_ratio":..., "win_rate":..., ...}
        Returns:
            {"fitness": float, "breakdown": {...}}
        """
        breakdown = {}
        fitness = 0.0

        # 1. Sharpe ratio (越大越好)
        sharpe = backtest_stats.get("夏普比率", backtest_stats.get("sharpe_ratio", 0)) or 0
        sharpe_norm = self._normalize(sharpe, -1, 3)
        breakdown["sharpe_ratio"] = round(sharpe_norm, 4)
        fitness += sharpe_norm * self.weights.get("sharpe_ratio", 0.30)

        # 2. 年化收益 (越大越好)
        ann_return = backtest_stats.get("年化收益(%)", backtest_stats.get("annual_return", 0)) or 0
        ann_return_norm = self._normalize(ann_return, -20, 50)
        breakdown["annual_return"] = round(ann_return_norm, 4)
        fitness += ann_return_norm * self.weights.get("annual_return", 0.20)

        # 3. 胜率 (越大越好)
        win_rate = backtest_stats.get("胜率(%)", backtest_stats.get("win_rate", 0)) or 0
        win_rate_norm = win_rate / 100
        breakdown["win_rate"] = round(win_rate_norm, 4)
        fitness += win_rate_norm * self.weights.get("win_rate", 0.15)

        # 4. Calmar ratio (越大越好, =年化收益/最大回撤绝对值)
        max_dd = abs(backtest_stats.get("最大回撤(%)", backtest_stats.get("max_drawdown", 0)) or 0)
        if max_dd > 0:
            calmar = (ann_return or 0) / max_dd
        else:
            calmar = 0
        calmar_norm = self._normalize(calmar, -1, 5)
        breakdown["calmar_ratio"] = round(calmar_norm, 4)
        fitness += calmar_norm * self.weights.get("calmar_ratio", 0.10)

        # 5. 最大回撤 (越小越好, 取负)
        max_dd_norm = 1 - self._normalize(max_dd, 0, 50)
        breakdown["max_drawdown"] = round(max_dd_norm, 4)
        fitness += max_dd_norm * self.weights.get("max_drawdown", 0.15)

        # 6. 盈亏比 (越大越好)
        profit_factor = backtest_stats.get("盈亏比", backtest_stats.get("profit_factor", 0)) or 0
        pf_norm = self._normalize(profit_factor, 0.5, 5)
        breakdown["profit_factor"] = round(pf_norm, 4)
        fitness += pf_norm * self.weights.get("profit_factor", 0.05)

        # 7. 信号质量 (基于样本外一致性)
        signal_quality = self._estimate_signal_quality(backtest_stats)
        breakdown["signal_quality"] = round(signal_quality, 4)
        fitness += signal_quality * self.weights.get("signal_quality", 0.03)

        # 8. 稳定性 (避免过拟合)
        stability = self._estimate_stability(backtest_stats)
        breakdown["turnover_stability"] = round(stability, 4)
        fitness += stability * self.weights.get("turnover_stability", 0.02)

        return {
            "fitness": round(fitness, 6),
            "breakdown": breakdown,
            "weights_used": self.weights,
        }

    def _normalize(self, value: float, lo: float, hi: float) -> float:
        """归一化到[0, 1] (超出边界截断)"""
        if hi <= lo:
            return 0.5
        return float(np.clip((value - lo) / (hi - lo), 0, 1))

    def _estimate_signal_quality(self, stats: Dict) -> float:
        """估计信号质量 (基于已知指标)"""
        quality = 0.5

        win_rate = stats.get("胜率(%)", stats.get("win_rate", 50)) or 50
        if win_rate >= 60:
            quality += 0.2
        elif win_rate >= 50:
            quality += 0.1
        elif win_rate < 40:
            quality -= 0.2

        # 盈亏比 > 1.5 加分
        pf = stats.get("盈亏比", stats.get("profit_factor", 1)) or 1
        if pf > 2:
            quality += 0.15
        elif pf > 1.5:
            quality += 0.05

        return np.clip(quality, 0, 1)

    def _estimate_stability(self, stats: Dict) -> float:
        """估计策略稳定性"""
        stability = 0.5

        total_trades = stats.get("总交易次数", stats.get("total_trades", 0)) or 0
        if total_trades < 30:
            stability -= 0.3  # 样本太少, 可能过拟合

        max_dd = abs(stats.get("最大回撤(%)", stats.get("max_drawdown", 20)) or 20)
        if max_dd < 15:
            stability += 0.15
        elif max_dd > 40:
            stability -= 0.2

        return np.clip(stability, 0, 1)

    def compare(self, stats_list: List[Dict]) -> pd.DataFrame:
        """
        比较多组回测结果
        Returns:
            按适应度降序排列的DataFrame
        """
        results = []
        for i, stats in enumerate(stats_list):
            fit = self.compute(stats)
            results.append({
                "id": i,
                "fitness": fit["fitness"],
                **fit["breakdown"],
                **{k: stats.get(k, None) for k in ["夏普比率", "胜率(%)", "年化收益(%)", "最大回撤(%)"]},
            })

        df = pd.DataFrame(results)
        return df.sort_values("fitness", ascending=False)


# 全局实例
ga_fitness = GAFitness()
