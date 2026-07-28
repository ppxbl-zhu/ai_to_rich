"""
Base Notification Channel — 通知渠道基类
所有通知渠道继承此类
"""
from abc import ABC, abstractmethod


class BaseChannel(ABC):
    """通知渠道基类"""

    channel_name: str = "base"

    @abstractmethod
    def send(self, title: str, body: str, priority: str = "normal") -> bool:
        """
        发送通知
        Args:
            title: 通知标题
            body: 通知内容
            priority: urgent | high | normal | low
        Returns:
            是否发送成功
        """
        ...

    def is_available(self) -> bool:
        """检查渠道是否可用"""
        return True

    def get_channel_info(self) -> dict:
        return {
            "name": self.channel_name,
            "available": self.is_available(),
        }
