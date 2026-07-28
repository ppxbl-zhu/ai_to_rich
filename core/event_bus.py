"""
Event Bus — 进程内发布/订阅事件系统
解耦各模块, 支持异步事件驱动架构
"""
from typing import Dict, List, Callable, Any, Set
from collections import defaultdict
from loguru import logger
from enum import Enum


class EventType(str, Enum):
    """系统事件类型"""
    # 交易日状态
    MARKET_OPEN = "market_open"
    MARKET_CLOSE = "market_close"
    AUCTION_START = "auction_start"
    AUCTION_END = "auction_end"
    LUNCH_BREAK_START = "lunch_break_start"
    LUNCH_BREAK_END = "lunch_break_end"

    # 策略信号
    STRATEGY_SIGNAL = "strategy_signal"         # 策略产生交易信号
    SIGNAL_CONFIRMED = "signal_confirmed"       # 信号经LLM确认
    SIGNAL_REJECTED = "signal_rejected"         # 信号被拒绝

    # 告警
    ALERT_TRIGGERED = "alert_triggered"         # 告警触发
    ALERT_RESOLVED = "alert_resolved"           # 告警解除

    # 仓位变化
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    POSITION_CHANGED = "position_changed"

    # 数据
    DATA_REFRESHED = "data_refreshed"
    REAL_TIME_QUOTE = "real_time_quote"

    # 优化
    OPTIMIZATION_STARTED = "optimization_started"
    OPTIMIZATION_GENERATION = "optimization_generation"
    OPTIMIZATION_COMPLETE = "optimization_complete"

    # 系统
    ERROR_CRITICAL = "error_critical"
    ERROR_WARNING = "error_warning"
    SYSTEM_HEALTH = "system_health"


class Event:
    """事件对象"""

    def __init__(self, event_type: EventType, data: Dict[str, Any] = None,
                 source: str = ""):
        self.type = event_type
        self.data = data or {}
        self.source = source

    def __repr__(self):
        return f"Event({self.type.value}, source={self.source})"


# 回调函数类型
Callback = Callable[[Event], None]


class EventBus:
    """
    进程内事件总线
    支持发布/订阅模式, 同步执行回调
    """

    def __init__(self):
        self._subscribers: Dict[EventType, List[Callback]] = defaultdict(list)
        self._history: List[Event] = []         # 事件历史(最近1000条)
        self._max_history = 1000

    def subscribe(self, event_type: EventType, callback: Callback):
        """订阅事件"""
        self._subscribers[event_type].append(callback)
        logger.debug(f"订阅事件: {event_type.value} -> {callback.__name__}")

    def unsubscribe(self, event_type: EventType, callback: Callback):
        """取消订阅"""
        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)

    def publish(self, event: Event):
        """发布事件 — 同步通知所有订阅者"""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        subscribers = self._subscribers.get(event.type, [])
        if not subscribers:
            logger.debug(f"事件无订阅者: {event.type.value}")
            return

        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"事件回调失败 {callback.__name__}({event.type.value}): {e}")

    def get_history(self, event_type: EventType = None, limit: int = 50) -> List[Event]:
        """获取事件历史"""
        if event_type:
            return [e for e in self._history if e.type == event_type][-limit:]
        return self._history[-limit:]

    def clear_history(self):
        """清空事件历史"""
        self._history.clear()

    @property
    def subscriber_count(self) -> Dict[str, int]:
        """各事件类型的订阅数"""
        return {k.value: len(v) for k, v in self._subscribers.items() if v}


# 全局单例
event_bus = EventBus()
