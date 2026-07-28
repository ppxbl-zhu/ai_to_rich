"""
Composite Merger — 多策略信号合并与冲突消解
将多个策略的信号去重、合并、排序, 输出统一推荐列表
"""
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict
from loguru import logger

from strategies.base_strategy import StrategySignal


class SignalMerger:
    """
    多策略信号合并器
    职责:
    1. 同股票多信号 → 去重 (保留最高置信度)
    2. 同板块超配 → 限制数量
    3. 资金约束 → 按总仓位过滤
    4. 综合排序 → 按置信度+多样性
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.max_positions = self.config.get("max_positions", 5)
        self.max_per_sector = self.config.get("max_per_sector", 2)
        self.min_confidence = self.config.get("min_confidence", 0.40)
        self.strategy_weights = self.config.get("strategy_weights", {
            "auction": 1.0,     # 竞价策略权重最高 (历史胜率最高)
            "trend": 0.9,       # 趋势策略
            "reversal": 0.7,    # 反转策略 (风险较高)
            "event": 0.7,       # 事件策略
        })

    def merge(self, all_signals: List[StrategySignal],
              stock_sector_map: Dict[str, List[str]] = None) -> List[StrategySignal]:
        """
        合并多策略信号
        Args:
            all_signals: 所有策略的原始信号列表
            stock_sector_map: {code: [sector1, sector2, ...]}
        Returns:
            合并后的精选信号列表
        """
        if not all_signals:
            return []

        stock_sector_map = stock_sector_map or {}
        logger.info(f"[信号合并] 输入 {len(all_signals)} 个信号")

        # Step 1: 过滤低置信度
        signals = [s for s in all_signals if s.confidence >= self.min_confidence]
        logger.info(f"[信号合并] 置信度过滤后: {len(signals)} (min={self.min_confidence})")

        # Step 2: 同股票去重 — 保留置信度×策略权重的最高分
        by_code: Dict[str, StrategySignal] = {}
        for s in signals:
            weighted_conf = s.confidence * self.strategy_weights.get(
                s.strategy_name, 0.5
            )
            if s.code not in by_code:
                by_code[s.code] = s
                by_code[s.code].confidence = weighted_conf  # 更新为加权置信度
            else:
                existing_weighted = by_code[s.code].confidence
                if weighted_conf > existing_weighted:
                    by_code[s.code] = s
                    by_code[s.code].confidence = weighted_conf

        logger.info(f"[信号合并] 去重后: {len(by_code)} 只")

        # Step 3: 同板块限制
        selected = []
        sector_counts: Dict[str, int] = defaultdict(int)

        # 按置信度排序
        sorted_signals = sorted(by_code.values(), key=lambda s: s.confidence, reverse=True)

        for signal in sorted_signals:
            code = signal.code
            sectors = stock_sector_map.get(code, ["未分类"])

            # 检查板块限制
            blocked = False
            for sector in sectors:
                if sector_counts.get(sector, 0) >= self.max_per_sector:
                    blocked = True
                    break

            if not blocked:
                selected.append(signal)
                for sector in sectors:
                    sector_counts[sector] += 1

            if len(selected) >= self.max_positions:
                break

        logger.info(f"[信号合并] 最终精选: {len(selected)} 只")

        # 恢复原始置信度 (去加权)
        for s in selected:
            s.confidence = min(s.confidence / self.strategy_weights.get(s.strategy_name, 0.5), 1.0)

        return selected

    def analyze_conflicts(self, signals: List[StrategySignal]) -> List[Dict]:
        """
        分析信号冲突 — 同一股票出现买卖矛盾信号
        """
        by_code = defaultdict(list)
        for s in signals:
            by_code[s.code].append(s)

        conflicts = []
        for code, sigs in by_code.items():
            directions = set(s.direction for s in sigs)
            if len(directions) > 1:
                conflicts.append({
                    "code": code,
                    "name": sigs[0].name,
                    "signals": [s.to_dict() for s in sigs],
                })

        if conflicts:
            logger.warning(f"[信号冲突] 发现 {len(conflicts)} 个冲突: "
                          f"{[c['code'] for c in conflicts]}")

        return conflicts


class CapitalAllocator:
    """
    资金分配器
    基于凯利公式或等权分配资金
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.total_capital = self.config.get("total_capital", 100000)
        self.max_position_pct = self.config.get("max_position_pct", 0.25)
        self.min_position_pct = self.config.get("min_position_pct", 0.05)
        self.method = self.config.get("method", "equal_weight")  # "equal_weight" | "kelly" | "confidence_weighted"

    def allocate(self, signals: List[StrategySignal],
                 current_positions: Dict[str, float] = None) -> Dict[str, Dict]:
        """
        为信号分配资金
        Args:
            signals: 精选信号列表
            current_positions: {code: current_market_value} 现有持仓
        Returns:
            {code: {"shares": int, "amount": float, "pct": float}}
        """
        if not signals:
            return {}

        current_positions = current_positions or {}

        # 计算已占用资金
        used_capital = sum(current_positions.values())
        available = self.total_capital - used_capital

        if available <= 0:
            logger.warning("[资金分配] 无可用资金")
            return {}

        n = len(signals)
        allocation = {}

        if self.method == "equal_weight":
            # 等权分配
            per_signal = available / n
            per_signal = min(per_signal, self.total_capital * self.max_position_pct)
            per_signal = max(per_signal, self.total_capital * self.min_position_pct)

            for s in signals:
                allocation[s.code] = {
                    "amount": round(per_signal, 2),
                    "pct": round(per_signal / self.total_capital, 4),
                }

        elif self.method == "confidence_weighted":
            # 按置信度加权
            total_conf = sum(s.confidence for s in signals)
            for s in signals:
                weight = s.confidence / total_conf if total_conf > 0 else 1/n
                amount = min(
                    available * weight,
                    self.total_capital * self.max_position_pct
                )
                allocation[s.code] = {
                    "amount": round(amount, 2),
                    "pct": round(amount / self.total_capital, 4),
                }

        elif self.method == "kelly":
            # 简化凯利公式: f* = win_rate - (1-win_rate)/(avg_win/avg_loss)
            # 使用策略历史胜率作为win_rate近似
            for s in signals:
                # 默认参数
                win_rate = 0.60
                avg_win_loss_ratio = 1.5
                kelly_f = win_rate - (1 - win_rate) / avg_win_loss_ratio
                kelly_f = max(0.05, min(kelly_f, self.max_position_pct))  # 限制范围

                amount = available * kelly_f / len(signals)
                allocation[s.code] = {
                    "amount": round(amount, 2),
                    "pct": round(kelly_f, 4),
                    "kelly_f": round(kelly_f, 4),
                }

        logger.info(f"[资金分配] {self.method}: {len(allocation)} 只, "
                    f"总分配={sum(a['amount'] for a in allocation.values()):.0f}")

        return allocation


# 默认实例
merger = SignalMerger()
allocator = CapitalAllocator()
