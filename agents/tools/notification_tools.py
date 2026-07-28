"""
Agent Notification Tools — 通知推送工具集
Agent可调用这些函数发送告警和消息
"""
from typing import Dict, List, Any, Optional
from loguru import logger


class NotificationTools:
    """通知推送工具集"""

    def send_alert(self, title: str, body: str, priority: str = "normal",
                   channel: str = "all") -> Dict[str, Any]:
        """
        发送告警通知
        Args:
            title: 标题
            body: 内容
            priority: urgent | high | normal | low
            channel: telegram | wechat | all
        Returns:
            {"status": "ok"/"partial"/"failed", "channels": {...}}
        """
        results = {}

        # Telegram
        if channel in ("telegram", "all"):
            results["telegram"] = self._send_telegram(title, body, priority)

        # WeChat (Server酱)
        if channel in ("wechat", "all"):
            results["wechat"] = self._send_wechat(title, body)

        # 记录到数据库
        try:
            from data.storage.sqlite_storage import storage
            for ch, status in results.items():
                storage.log_notification({
                    "channel": ch,
                    "priority": priority,
                    "title": title,
                    "body": body[:500],
                    "status": "sent" if status else "failed",
                })
        except Exception:
            pass

        all_ok = all(results.values())
        return {
            "status": "ok" if all_ok else ("partial" if any(results.values()) else "failed"),
            "channels": results,
        }

    def _send_telegram(self, title: str, body: str, priority: str) -> bool:
        """发送Telegram消息"""
        try:
            from config.settings import TELEGRAM_BOT_TOKEN
            import os
            token = TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
            if not token:
                logger.debug("[Notify] Telegram未配置")
                return False

            import requests

            emoji = {"urgent": "🔴", "high": "🟠", "normal": "🔵", "low": "⚪"}.get(priority, "🔵")
            text = f"{emoji} *{title}*\n\n{body}"

            # 获取chat_id: 环境变量 或 通过getUpdates自动获取
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if not chat_id:
                # 尝试从最近的消息中获取chat_id
                try:
                    updates_url = f"https://api.telegram.org/bot{token}/getUpdates"
                    resp = requests.get(updates_url, timeout=5)
                    updates = resp.json()
                    if updates.get("ok") and updates.get("result"):
                        chat_id = str(updates["result"][-1]["message"]["chat"]["id"])
                        logger.info(f"[Notify] 自动获取Telegram chat_id: {chat_id}")
                except Exception:
                    pass

            if not chat_id:
                logger.warning("[Notify] Telegram chat_id未配置, 请设置TELEGRAM_CHAT_ID或先给Bot发一条消息")
                return False

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }, timeout=10)

            if resp.status_code == 200 and resp.json().get("ok"):
                logger.info(f"[Notify] Telegram发送成功: {title[:30]}")
                return True
            else:
                logger.warning(f"[Notify] Telegram发送失败: {resp.text[:100]}")
                return False

        except Exception as e:
            logger.warning(f"[Notify] Telegram异常: {e}")
            return False

    def _send_wechat(self, title: str, body: str) -> bool:
        """通过Server酱发送微信"""
        try:
            from config.settings import SCT_SEND_KEYS
            if not SCT_SEND_KEYS:
                logger.debug("[Notify] 微信未配置")
                return False

            import requests

            for key in SCT_SEND_KEYS[:2]:  # 最多发2个账号
                url = f"https://sctapi.ftqq.com/{key}.send"
                resp = requests.post(url, data={
                    "title": title,
                    "desp": body,
                }, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"[Notify] 微信推送失败: {resp.text}")

            logger.info(f"[Notify] 微信: {title}")
            return True
        except Exception as e:
            logger.warning(f"[Notify] 微信失败: {e}")
            return False

    def send_morning_brief(self, brief: Dict[str, Any]) -> bool:
        """
        发送盘前简报
        Args:
            brief: MarketBrief字典
        """
        sentiment_text = "乐观" if brief.get("sentiment", 0) > 0.3 else \
                        "悲观" if brief.get("sentiment", 0) < -0.3 else "中性"

        body = f"""
📊 市场情绪: {sentiment_text} ({brief.get('sentiment', 0):.2f})
🔥 热点板块: {', '.join(brief.get('top_sectors', [])[:5])}
⚠️ 风险提示: {', '.join(brief.get('risk_alerts', [])[:3]) or '无'}
📈 市场状态: {brief.get('regime', 'unknown')}

{brief.get('brief', '')}
""".strip()

        return self.send_alert(
            f"盘前简报 - {brief.get('date', '')}",
            body,
            priority="normal",
        )["status"] == "ok"

    def send_trade_signal(self, signal: Dict[str, Any]) -> bool:
        """
        发送交易信号通知
        """
        direction_emoji = "📈" if signal.get("direction") == "buy" else "📉"
        priority = "high" if signal.get("confidence", 0) > 0.7 else "normal"

        body = f"""
{direction_emoji} {signal.get('direction', '')} {signal.get('name', '')}({signal.get('code', '')})
💰 建议价格: {signal.get('price', 0):.2f}
🎯 置信度: {signal.get('confidence', 0):.0%}
🛑 止损: {signal.get('stop_loss', 0):.2f}
✅ 止盈: {signal.get('take_profit', 0):.2f}
📝 理由: {signal.get('reason', '')}
""".strip()

        return self.send_alert(
            f"交易信号: {signal.get('name', '')}",
            body,
            priority=priority,
        )["status"] == "ok"


# 工具函数schema
NOTIFICATION_TOOLS_SCHEMA = [
    {
        "name": "send_alert",
        "description": "发送告警通知(Telegram+微信)",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "通知标题"},
                "body": {"type": "string", "description": "通知内容"},
                "priority": {"type": "string", "enum": ["urgent", "high", "normal", "low"]},
                "channel": {"type": "string", "enum": ["telegram", "wechat", "all"]},
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "send_morning_brief",
        "description": "发送盘前简报",
        "parameters": {
            "type": "object",
            "properties": {
                "brief": {"type": "object", "description": "MarketBrief对象"},
            },
            "required": ["brief"],
        },
    },
    {
        "name": "send_trade_signal",
        "description": "发送交易信号通知",
        "parameters": {
            "type": "object",
            "properties": {
                "signal": {"type": "object", "description": "交易信号对象"},
            },
            "required": ["signal"],
        },
    },
]

# 全局实例
notification_tools = NotificationTools()
