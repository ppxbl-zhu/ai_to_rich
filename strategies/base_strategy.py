"""
Base Strategy Interface — 所有交易策略的基类
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import date


@dataclass
class StrategySignal:
    """策略信号"""
    code: str
    name: str
    direction: str = "buy"            # "buy" | "sell"
    confidence: float = 0.0           # 0-1
    price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    horizon: str = "短线"             # "短线" | "中线" | "长线"
    reason: str = ""
    strategy_name: str = ""
    factors: Dict[str, float] = field(default_factory=dict)  # 因子得分明细

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "direction": self.direction,
            "confidence": round(self.confidence, 4),
            "price": self.price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "horizon": self.horizon,
            "reason": self.reason,
            "strategy_name": self.strategy_name,
            "factors": self.factors,
        }


class BaseStrategy(ABC):
    """
    策略基类
    所有策略继承此类，实现以下接口:
    - generate_signals: 生成交易信号
    - get_parameters: 获取当前参数
    - set_parameters: 设置参数 (GA优化用)
    - explain_signal: 解释信号逻辑
    """

    strategy_name: str = "base"
    strategy_description: str = ""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.signals_today: List[StrategySignal] = []

    @abstractmethod
    def generate_signals(self, context: Any) -> List[StrategySignal]:
        """
        生成交易信号
        Args:
            context: TradingContext 或 DataFrame (取决于调用场景)
        Returns:
            信号列表
        """
        ...

    def get_parameters(self) -> Dict[str, Any]:
        """获取策略当前参数 (供GA读取)"""
        return self.config.copy()

    def set_parameters(self, params: Dict[str, Any]):
        """设置策略参数 (GA优化后更新)"""
        self.config.update(params)

    def explain_signal(self, signal: StrategySignal) -> str:
        """解释信号逻辑 (供LLM分析)"""
        factors_str = ", ".join(f"{k}={v:.3f}" for k, v in signal.factors.items())
        return (
            f"[{self.strategy_name}] {signal.name}({signal.code}) "
            f"方向={signal.direction}, 置信度={signal.confidence:.2f}, "
            f"价格={signal.price:.2f}, 因子: {factors_str}, "
            f"理由: {signal.reason}"
        )

    def reset_daily(self):
        """重置每日状态"""
        self.signals_today = []

    def __repr__(self):
        return f"{self.strategy_name}(enabled={self.enabled})"
