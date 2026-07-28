"""
Trading Day State Machine — 交易日状态机
管理交易日的生命周期状态转换
"""
from enum import Enum
from typing import Optional, Callable, Dict, List
from datetime import datetime, time
from loguru import logger


class TradingState(str, Enum):
    """交易日状态"""
    PRE_MARKET = "pre_market"              # 盘前 (< 9:15)
    AUCTION = "auction"                    # 集合竞价 (9:15-9:25)
    AUCTION_WAITING = "auction_waiting"    # 竞价等待开盘 (9:25-9:30)
    CONTINUOUS = "continuous"              # 连续交易 (9:30-11:30)
    LUNCH_BREAK = "lunch_break"           # 午休 (11:30-13:00)
    AFTERNOON = "afternoon"               # 午后交易 (13:00-15:00)
    CLOSING_AUCTION = "closing_auction"   # 尾盘集合竞价 (15:00-15:30)
    POST_MARKET = "post_market"           # 盘后 (15:30+)
    OVERNIGHT = "overnight"               # 夜间/非交易日


# 状态转移回调
StateCallback = Callable[[TradingState, TradingState], None]


class TradingStateMachine:
    """
    交易日状态机
    根据时间自动转换状态, 触发回调
    """

    # 关键时间点
    AUCTION_START = time(9, 15)
    AUCTION_END = time(9, 25)
    TRADING_START = time(9, 30)
    LUNCH_START = time(11, 30)
    LUNCH_END = time(13, 0)
    TRADING_END = time(15, 0)
    POST_MARKET_END = time(15, 30)

    def __init__(self):
        self._state = TradingState.OVERNIGHT
        self._callbacks: Dict[TradingState, List[StateCallback]] = {
            s: [] for s in TradingState
        }

    @property
    def state(self) -> TradingState:
        return self._state

    @property
    def is_trading(self) -> bool:
        """是否在交易时段"""
        return self._state in (
            TradingState.AUCTION,
            TradingState.CONTINUOUS,
            TradingState.AFTERNOON,
        )

    @property
    def is_market_open(self) -> bool:
        """市场是否开盘"""
        return self._state in (
            TradingState.CONTINUOUS,
            TradingState.LUNCH_BREAK,
            TradingState.AFTERNOON,
        )

    @property
    def state_label(self) -> str:
        """中文状态名"""
        labels = {
            TradingState.PRE_MARKET: "盘前",
            TradingState.AUCTION: "集合竞价",
            TradingState.AUCTION_WAITING: "竞价等待",
            TradingState.CONTINUOUS: "早盘交易",
            TradingState.LUNCH_BREAK: "午休",
            TradingState.AFTERNOON: "午后交易",
            TradingState.CLOSING_AUCTION: "尾盘竞价",
            TradingState.POST_MARKET: "盘后",
            TradingState.OVERNIGHT: "夜间",
        }
        return labels.get(self._state, "未知")

    def on_enter(self, state: TradingState, callback: StateCallback):
        """注册状态进入回调"""
        self._callbacks[state].append(callback)

    def on_leave(self, state: TradingState, callback: StateCallback):
        """注册状态离开回调 (等同于下一个状态的进入回调)"""
        self._callbacks[state].append(callback)

    def _fire_callbacks(self, old_state: TradingState, new_state: TradingState):
        """触发状态转移回调"""
        for cb in self._callbacks.get(new_state, []):
            try:
                cb(old_state, new_state)
            except Exception as e:
                logger.error(f"状态回调失败 {cb.__name__}: {e}")

    def update(self, current_time: time = None) -> TradingState:
        """
        根据当前时间更新状态
        返回新状态 (如果没有变化则返回当前状态)
        """
        if current_time is None:
            current_time = datetime.now().time()

        old_state = self._state

        # 按时间段判断
        if current_time < self.AUCTION_START:
            new_state = TradingState.PRE_MARKET
        elif current_time < self.AUCTION_END:
            new_state = TradingState.AUCTION
        elif current_time < self.TRADING_START:
            new_state = TradingState.AUCTION_WAITING
        elif current_time < self.LUNCH_START:
            new_state = TradingState.CONTINUOUS
        elif current_time < self.LUNCH_END:
            new_state = TradingState.LUNCH_BREAK
        elif current_time < self.TRADING_END:
            new_state = TradingState.AFTERNOON
        elif current_time < self.POST_MARKET_END:
            new_state = TradingState.CLOSING_AUCTION
        else:
            new_state = TradingState.POST_MARKET

        if new_state != old_state:
            self._state = new_state
            self._fire_callbacks(old_state, new_state)
            logger.info(f"状态转移: {old_state.value} -> {new_state.value}")
            return new_state

        return old_state

    def force_state(self, state: TradingState):
        """强制设置状态 (测试用)"""
        old = self._state
        self._state = state
        self._fire_callbacks(old, state)

    def get_next_states(self, minutes_ahead: int = 5) -> List[TradingState]:
        """预测接下来N分钟的状态 (用于调度)"""
        from datetime import timedelta
        now = datetime.now()
        future = now + timedelta(minutes=minutes_ahead)
        return [self._state, self._get_state_for_time(future.time())]

    def _get_state_for_time(self, t: time) -> TradingState:
        """获取指定时间的状态"""
        if t < self.AUCTION_START:
            return TradingState.PRE_MARKET
        elif t < self.AUCTION_END:
            return TradingState.AUCTION
        elif t < self.TRADING_START:
            return TradingState.AUCTION_WAITING
        elif t < self.LUNCH_START:
            return TradingState.CONTINUOUS
        elif t < self.LUNCH_END:
            return TradingState.LUNCH_BREAK
        elif t < self.TRADING_END:
            return TradingState.AFTERNOON
        elif t < self.POST_MARKET_END:
            return TradingState.CLOSING_AUCTION
        else:
            return TradingState.POST_MARKET


# 全局单例
state_machine = TradingStateMachine()
