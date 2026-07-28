"""
交易日历 — 判断A股交易日
复用现有 auction-stock-picker 逻辑
"""
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Optional

# 复用现有交易日历
EXISTING_SYSTEM = Path("/mnt/d/AI/auction-stock-picker")
if str(EXISTING_SYSTEM) not in sys.path:
    sys.path.append(str(EXISTING_SYSTEM))  # append, not insert(0), 避免遮蔽quant-agent自身模块


class TradingCalendar:
    """A股交易日历"""

    # A股固定休市日期 (非周末的节日)
    FIXED_HOLIDAYS_2026 = {
        date(2026, 1, 1),    # 元旦
        date(2026, 1, 2),
        date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
        date(2026, 2, 19), date(2026, 2, 20),  # 春节
        date(2026, 4, 6),    # 清明
        date(2026, 5, 1), date(2026, 5, 4), date(2026, 5, 5),  # 劳动节
        date(2026, 6, 22),   # 端午
        date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30),  # 中秋+国庆
        date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5),
        date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8),
    }

    def is_trading_day(self, d: date = None) -> bool:
        """判断是否为交易日"""
        if d is None:
            d = date.today()

        # 周末
        if d.weekday() >= 5:  # 5=Sat, 6=Sun
            return False

        # 固定假期
        if d in self.FIXED_HOLIDAYS_2026:
            return False

        return True

    def next_trading_day(self, d: date = None) -> date:
        """下一个交易日"""
        if d is None:
            d = date.today()
        d = d + timedelta(days=1)
        while not self.is_trading_day(d):
            d = d + timedelta(days=1)
        return d

    def prev_trading_day(self, d: date = None) -> date:
        """上一个交易日"""
        if d is None:
            d = date.today()
        d = d - timedelta(days=1)
        while not self.is_trading_day(d):
            d = d - timedelta(days=1)
        return d

    def trading_days_between(self, start: date, end: date) -> list:
        """区间内的交易日列表"""
        days = []
        d = start
        while d <= end:
            if self.is_trading_day(d):
                days.append(d)
            d += timedelta(days=1)
        return days

    def is_trading_time(self, dt: datetime = None) -> bool:
        """是否在交易时段内 (9:30-11:30, 13:00-15:00)"""
        if dt is None:
            dt = datetime.now()

        if not self.is_trading_day(dt.date()):
            return False

        t = dt.time()
        return (
            (t.hour == 9 and t.minute >= 30) or
            (t.hour == 10) or
            (t.hour == 11 and t.minute <= 30) or
            (t.hour == 13) or
            (t.hour == 14) or
            (t.hour == 15 and t.minute == 0)
        )


# 全局单例
trading_calendar = TradingCalendar()
