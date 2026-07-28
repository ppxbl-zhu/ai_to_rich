"""
Notification Router — 多渠道路由与去重
优先级路由, 渠道管理, 频控
"""
from typing import Dict, List, Any, Optional
from enum import Enum
from datetime import datetime
from loguru import logger

from notification.base_channel import BaseChannel


class Priority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class NotificationRouter:
    """
    通知路由器
    - 优先级 → 渠道选择
    - 去重 (相同内容N秒内不重复)
    - 频率控制 (每分钟上限)
    """

    def __init__(self):
        self.channels: Dict[str, BaseChannel] = {}
        self._sent_cache: Dict[str, float] = {}   # hash → timestamp
        self._dedup_window = 300                    # 去重窗口(秒)
        self._rate_limits: Dict[str, Dict] = {      # priority → {window, max_count, sent}
            "urgent": {"window": 60, "max": 20, "sent": []},
            "high": {"window": 60, "max": 10, "sent": []},
            "normal": {"window": 60, "max": 5, "sent": []},
            "low": {"window": 300, "max": 10, "sent": []},
        }

    def register_channel(self, channel: BaseChannel):
        """注册通知渠道"""
        self.channels[channel.channel_name] = channel
        logger.info(f"[NotifyRouter] 渠道注册: {channel.channel_name}")

    def route(self, title: str, body: str, priority: str = "normal",
              channel: str = "all") -> Dict[str, Any]:
        """
        路由通知到指定渠道
        Args:
            title: 标题
            body: 内容
            priority: urgent | high | normal | low
            channel: telegram | wechat | all
        Returns:
            各渠道发送结果
        """
        # 去重
        import hashlib
        content_hash = hashlib.md5(f"{title}{body}".encode()).hexdigest()
        last_time = self._sent_cache.get(content_hash, 0)
        now = datetime.now().timestamp()

        if now - last_time < self._dedup_window:
            logger.debug(f"[NotifyRouter] 去重: {title[:30]}")
            return {"status": "dedup", "channels": {}}

        # 频率控制
        if not self._check_rate_limit(priority):
            logger.warning(f"[NotifyRouter] 频率限制: {priority}")
            return {"status": "rate_limited", "channels": {}}

        self._sent_cache[content_hash] = now

        # 清理过期缓存
        self._sent_cache = {
            h: t for h, t in self._sent_cache.items()
            if now - t < self._dedup_window * 2
        }

        # 目标渠道
        target_channels = self._select_channels(priority, channel)

        # 发送
        results = {}
        for ch_name in target_channels:
            ch = self.channels.get(ch_name)
            if not ch:
                results[ch_name] = False
                continue

            try:
                success = ch.send(title, body, priority)
                results[ch_name] = success
            except Exception as e:
                logger.warning(f"[NotifyRouter] {ch_name}发送失败: {e}")
                results[ch_name] = False

        all_ok = all(results.values()) if results else False
        return {
            "status": "ok" if all_ok else "partial" if any(results.values()) else "failed",
            "channels": results,
            "priority": priority,
        }

    def _select_channels(self, priority: str, channel_spec: str) -> List[str]:
        """根据优先级和指定选择渠道"""
        if channel_spec != "all":
            channels = [c.strip() for c in channel_spec.split(",")]
            return [c for c in channels if c in self.channels]

        # "all" — 按优先级筛选
        channel_priority = {
            "urgent": ["telegram", "wechat"],
            "high": ["telegram", "wechat"],
            "normal": ["telegram"],
            "low": ["telegram"],
        }
        preferred = channel_priority.get(priority, ["telegram"])
        return [c for c in preferred if c in self.channels]

    def _check_rate_limit(self, priority: str) -> bool:
        """检查频率限制"""
        limit = self._rate_limits.get(priority)
        if not limit:
            return True

        now = datetime.now().timestamp()
        window_start = now - limit["window"]

        # 清理过期记录
        limit["sent"] = [t for t in limit["sent"] if t > window_start]

        if len(limit["sent"]) >= limit["max"]:
            return False

        limit["sent"].append(now)
        return True

    def get_status(self) -> Dict[str, Any]:
        """获取路由状态"""
        return {
            "channels": {
                name: ch.is_available()
                for name, ch in self.channels.items()
            },
            "cache_size": len(self._sent_cache),
            "rate_limits": {
                p: {
                    "max": l["max"],
                    "recent": len(l["sent"]),
                }
                for p, l in self._rate_limits.items()
            },
        }


# 创建默认路由器
router = NotificationRouter()

# 注册默认渠道
try:
    from agents.tools.notification_tools import notification_tools

    class TelegramChannel(BaseChannel):
        channel_name = "telegram"
        def send(self, title, body, priority="normal"):
            return notification_tools._send_telegram(title, body, priority)

    class WechatChannel(BaseChannel):
        channel_name = "wechat"
        def send(self, title, body, priority="normal"):
            return notification_tools._send_wechat(title, body)

    router.register_channel(TelegramChannel())
    router.register_channel(WechatChannel())
except Exception:
    pass
