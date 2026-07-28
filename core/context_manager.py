"""
Context Manager — 共享交易上下文
整个交易日的"工作记忆", 所有Agent共享读写
"""
import threading
from typing import Dict, Any, List, Optional
from datetime import date, datetime
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class Position:
    """持仓"""
    code: str
    name: str
    entry_date: str
    entry_price: float
    shares: int
    strategy_id: str
    stop_loss: float
    take_profit: float
    current_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0


@dataclass
class Signal:
    """交易信号"""
    code: str
    name: str
    direction: str          # "buy" | "sell"
    strategy_id: str
    confidence: float
    price: float
    stop_loss: float = 0
    take_profit: float = 0
    horizon: str = "短线"   # "短线" | "中线" | "长线"
    reason: str = ""


@dataclass
class MarketBrief:
    """市场研判摘要"""
    sentiment: float = 0.0              # -1 to 1
    top_sectors: List[str] = field(default_factory=list)
    risk_alerts: List[str] = field(default_factory=list)
    regime: str = "unknown"             # trending_up | trending_down | range_bound | volatile
    brief: str = ""


class TradingContext:
    """
    交易日共享上下文
    线程安全, 所有Agent读写
    """

    def __init__(self, date_str: str = None):
        self._lock = threading.RLock()
        self.date = date_str or date.today().strftime("%Y-%m-%d")
        self.created_at = datetime.now()

        # 市场状态
        self.market_brief: Optional[MarketBrief] = None
        self.market_index: Dict[str, float] = {}       # 上证/深证/创业板涨跌

        # 策略信号
        self.signals: List[Signal] = []
        self.confirmed_signals: List[Signal] = []
        self.rejected_signals: List[Signal] = []

        # 持仓
        self.positions: Dict[str, Position] = {}       # code -> Position
        self.closed_positions: List[Position] = []

        # 模拟盘
        self.sim_capital: float = 100000.0
        self.sim_available: float = 100000.0

        # Agent产出
        self.research_output: Dict[str, Any] = {}
        self.review_output: Dict[str, Any] = {}
        self.alerts: List[Dict[str, Any]] = []

        # 策略DNA (当前激活的参数)
        self.active_dna: Dict[str, Any] = {}

        # 额外k-v (Agent间自由传递)
        self.meta: Dict[str, Any] = {}

    def add_signal(self, signal: Signal):
        with self._lock:
            self.signals.append(signal)

    def confirm_signal(self, signal: Signal):
        with self._lock:
            self.confirmed_signals.append(signal)

    def reject_signal(self, signal: Signal):
        with self._lock:
            self.rejected_signals.append(signal)

    def open_position(self, position: Position):
        with self._lock:
            self.positions[position.code] = position

    def close_position(self, code: str) -> Optional[Position]:
        with self._lock:
            pos = self.positions.pop(code, None)
            if pos:
                self.closed_positions.append(pos)
            return pos

    def add_alert(self, alert: Dict[str, Any]):
        with self._lock:
            self.alerts.append(alert)

    def get_summary(self) -> Dict[str, Any]:
        """生成当前状态摘要 (供LLM Agent使用)"""
        with self._lock:
            return {
                "date": self.date,
                "market_regime": self.market_brief.regime if self.market_brief else "unknown",
                "market_sentiment": self.market_brief.sentiment if self.market_brief else 0,
                "active_positions": len(self.positions),
                "total_pnl": sum(p.pnl for p in self.positions.values()),
                "signals_today": len(self.signals),
                "confirmed_signals": len(self.confirmed_signals),
                "alerts": len(self.alerts),
                "sim_capital": self.sim_capital,
            }

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        with self._lock:
            return {
                "date": self.date,
                "market_brief": {
                    "sentiment": self.market_brief.sentiment,
                    "top_sectors": self.market_brief.top_sectors,
                    "regime": self.market_brief.regime,
                    "brief": self.market_brief.brief,
                } if self.market_brief else None,
                "positions": {
                    code: {
                        "name": p.name,
                        "entry_price": p.entry_price,
                        "current_price": p.current_price,
                        "pnl_pct": p.pnl_pct,
                        "strategy": p.strategy_id,
                    }
                    for code, p in self.positions.items()
                },
                "signals_count": len(self.signals),
                "alerts_count": len(self.alerts),
                "sim_capital": self.sim_capital,
            }


# 全局上下文实例 (每个交易日重置)
_context: Optional[TradingContext] = None
_lock = threading.Lock()


def get_context() -> TradingContext:
    """获取当前交易日上下文"""
    global _context
    with _lock:
        if _context is None:
            _context = TradingContext()
        return _context


def reset_context(date_str: str = None):
    """重置上下文 (新交易日)"""
    global _context
    with _lock:
        _context = TradingContext(date_str)
        logger.info(f"交易上下文已重置: {_context.date}")
