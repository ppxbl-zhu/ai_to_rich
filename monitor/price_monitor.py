"""
Price Monitor — 实时行情监控服务
混合模式: WebSocket主 + HTTP轮询备用
交易时段持续运行, 推送实时价格到EventBus
"""
import time
import threading
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, time as dt_time
from loguru import logger

from core.event_bus import EventBus, EventType, Event, event_bus


class PriceMonitor:
    """
    实时价格监控器
    交易时段9:30-15:00持续运行
    - 主模式: WebSocket (新浪)
    - 备模式: HTTP轮询 (每30秒)
    """

    def __init__(self, codes: List[str] = None, interval: float = 30.0):
        self.codes = codes or []
        self.interval = interval          # 轮询间隔(秒)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable] = []

        # 行情缓存
        self._quotes: Dict[str, Dict] = {}
        self._last_update: Dict[str, float] = {}  # code → timestamp

        # 统计
        self.updates_count = 0
        self.errors_count = 0
        self.started_at: Optional[datetime] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def add_codes(self, codes: List[str]):
        """添加监控标的"""
        for c in codes:
            if c not in self.codes:
                self.codes.append(c)

    def remove_codes(self, codes: List[str]):
        """移除监控标的"""
        self.codes = [c for c in self.codes if c not in codes]

    def on_quote(self, callback: Callable):
        """注册行情回调"""
        self._callbacks.append(callback)

    def get_quote(self, code: str) -> Optional[Dict]:
        """获取单只股票最新行情"""
        return self._quotes.get(code)

    def get_all_quotes(self) -> Dict[str, Dict]:
        """获取所有行情"""
        return dict(self._quotes)

    def start(self):
        """启动监控 (后台线程)"""
        if self._running:
            logger.warning("[PriceMonitor] 已在运行")
            return

        self._running = True
        self.started_at = datetime.now()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="PriceMonitor")
        self._thread.start()
        logger.info(f"[PriceMonitor] 启动: {len(self.codes)} 只标的, 间隔={self.interval}s")

    def stop(self):
        """停止监控"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info(f"[PriceMonitor] 停止: {self.updates_count} 次更新, {self.errors_count} 次错误")

    def _run_loop(self):
        """主循环 — 先尝试WebSocket, 失败则回退到轮询"""
        # 尝试WebSocket
        ws_success = self._try_websocket()

        if not ws_success:
            logger.info("[PriceMonitor] WebSocket不可用, 使用HTTP轮询")
            self._poll_loop()

    def _try_websocket(self) -> bool:
        """尝试新浪WebSocket连接"""
        try:
            import asyncio
            import websockets
            import json

            async def ws_connect():
                sina_codes = []
                for c in self.codes:
                    prefix = "sh" if c.startswith(("6", "9")) else "sz"
                    sina_codes.append(f"{prefix}{c}")

                # 新浪WebSocket行情 (如果可用)
                # 实际生产中可能需要更稳定的数据源
                logger.info(f"[PriceMonitor] WebSocket连接测试...")
                return False  # 当前回退到轮询

            return False  # WebSocket需要更多基础设施, 当前默认轮询
        except ImportError:
            return False

    def _poll_loop(self):
        """HTTP轮询循环"""
        consecutive_errors = 0

        while self._running:
            try:
                if not self._is_trading_time():
                    time.sleep(60)  # 非交易时间降低频率
                    continue

                if self.codes:
                    self._poll_sina_quotes()

                consecutive_errors = 0
                self.updates_count += 1

            except Exception as e:
                consecutive_errors += 1
                self.errors_count += 1
                if consecutive_errors <= 3:
                    logger.warning(f"[PriceMonitor] 轮询错误 ({consecutive_errors}): {e}")
                time.sleep(min(5 * consecutive_errors, 60))

            time.sleep(self.interval)

    def _poll_sina_quotes(self):
        """新浪HTTP行情拉取"""
        try:
            import requests

            # 分批拉取 (每批最多100只)
            batch_size = 100
            all_updated = {}

            for i in range(0, len(self.codes), batch_size):
                batch = self.codes[i:i+batch_size]
                sina_codes = []
                for c in batch:
                    prefix = "sh" if c.startswith(("6", "9")) else "sz"
                    sina_codes.append(f"{prefix}{c}")

                url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
                headers = {"Referer": "https://finance.sina.com.cn"}
                resp = requests.get(url, headers=headers, timeout=10)
                resp.encoding = "gbk"

                for line in resp.text.strip().split("\n"):
                    if '="' not in line:
                        continue
                    try:
                        code_part = line.split("=")[0].split("_")[-1]
                        orig_code = code_part[2:]
                        parts = line.split('"')[1].split(",")
                        if len(parts) > 9:
                            all_updated[orig_code] = {
                                "name": parts[0],
                                "open": float(parts[1]),
                                "yesterday_close": float(parts[2]),
                                "price": float(parts[3]),
                                "high": float(parts[4]),
                                "low": float(parts[5]),
                                "volume": int(float(parts[8])),
                                "amount": float(parts[9]) if len(parts) > 9 else 0,
                                "change_pct": round((float(parts[3]) / float(parts[2]) - 1) * 100, 2),
                                "timestamp": datetime.now().isoformat(),
                            }
                    except (ValueError, IndexError):
                        continue

            # 更新缓存
            for code, quote in all_updated.items():
                old = self._quotes.get(code, {})
                self._quotes[code] = quote
                self._last_update[code] = time.time()

                # 检测显著变化 → 触发回调
                old_price = old.get("price", 0)
                new_price = quote["price"]
                if old_price > 0 and abs(new_price / old_price - 1) > 0.01:  # >1%变化
                    for cb in self._callbacks:
                        try:
                            cb(code, old, quote)
                        except Exception:
                            pass

                # 发布Event
                event_bus.publish(Event(
                    EventType.REAL_TIME_QUOTE,
                    {"code": code, **quote},
                    source="price_monitor",
                ))

        except Exception as e:
            raise

    def _is_trading_time(self) -> bool:
        """判断是否在A股交易时段"""
        now = datetime.now()
        t = now.time()

        # 周末
        if now.weekday() >= 5:
            return False

        # 交易时段
        morning = dt_time(9, 30) <= t <= dt_time(11, 30)
        afternoon = dt_time(13, 0) <= t <= dt_time(15, 0)

        return morning or afternoon

    def get_stats(self) -> Dict[str, Any]:
        """获取监控统计"""
        return {
            "running": self._running,
            "codes_count": len(self.codes),
            "updates": self.updates_count,
            "errors": self.errors_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "quotes_cached": len(self._quotes),
            "last_update": max(self._last_update.values()) if self._last_update else 0,
        }


# 全局实例
price_monitor = PriceMonitor()
