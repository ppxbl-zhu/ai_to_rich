"""
Alert Engine — 告警规则引擎
YAML可配置的多级告警, 支持去抖和冷却
"""
import time
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from loguru import logger
import yaml


class AlertRule:
    """单条告警规则"""

    def __init__(self, name: str, condition: str, priority: str = "normal",
                 message: str = "", cooldown_seconds: int = 300,
                 enabled: bool = True):
        self.name = name
        self.condition = condition
        self.priority = priority      # urgent | high | normal | low
        self.message = message
        self.cooldown_seconds = cooldown_seconds
        self.enabled = enabled


class Alert:
    """告警实例"""

    def __init__(self, rule: AlertRule, code: str, name: str = "",
                 data: Dict = None):
        self.rule_name = rule.name
        self.code = code
        self.name = name
        self.priority = rule.priority
        self.message = rule.message
        self.data = data or {}
        self.timestamp = datetime.now().isoformat()
        self.acknowledged = False


class AlertEngine:
    """
    告警规则引擎
    - 加载YAML规则文件
    - 评估每个标的的所有规则
    - 去抖 (同规则同标的不重复)
    - 冷却 (触发后N秒内不再触发)
    """

    DEFAULT_RULES = [
        # 止损
        {"name": "stop_loss", "condition": "pnl_pct <= -3.0",
         "priority": "urgent", "message": "触及止损线(-3%), 建议立即卖出",
         "cooldown": 600},
        # 深度亏损
        {"name": "deep_loss", "condition": "pnl_pct <= -7.0",
         "priority": "urgent", "message": "深度亏损(-7%), 必须止损!",
         "cooldown": 300},
        # 止盈
        {"name": "take_profit", "condition": "pnl_pct >= 8.0",
         "priority": "high", "message": "达到止盈目标(+8%), 建议卖出或移动止盈",
         "cooldown": 1800},
        # 放量
        {"name": "volume_spike", "condition": "volume_ratio > 3.0 and day_change > 0",
         "priority": "normal", "message": "放量拉升, 关注突破机会",
         "cooldown": 600},
        # 放量下跌
        {"name": "volume_spike_down", "condition": "volume_ratio > 2.5 and day_change < -3",
         "priority": "high", "message": "放量下跌, 警惕风险!",
         "cooldown": 300},
        # 跌破均线
        {"name": "break_ma20", "condition": "price < ma20 and pnl_pct < 0",
         "priority": "normal", "message": "跌破MA20且亏损, 趋势可能转弱",
         "cooldown": 3600},
        # 日内大跌
        {"name": "intraday_crash", "condition": "day_change <= -7.0",
         "priority": "urgent", "message": "日内暴跌! 建议立即评估持仓",
         "cooldown": 300},
        # 日内大涨
        {"name": "intraday_surge", "condition": "day_change >= 9.0",
         "priority": "high", "message": "日内大涨接近涨停, 关注封板力度",
         "cooldown": 600},
        # 连续下跌
        {"name": "consecutive_loss", "condition": "consecutive_down_days >= 3 and pnl_pct < -5",
         "priority": "high", "message": "连续3日下跌, 需关注是否止损",
         "cooldown": 3600},
        # RSI超买
        {"name": "rsi_overbought", "condition": "rsi14 > 80",
         "priority": "normal", "message": "RSI超买, 短期可能回调",
         "cooldown": 3600},
        # RSI超卖
        {"name": "rsi_oversold", "condition": "rsi14 < 20",
         "priority": "normal", "message": "RSI超卖, 关注反弹机会",
         "cooldown": 3600},
    ]

    def __init__(self, rules_config: str = None):
        self.rules: List[AlertRule] = []
        self._last_triggered: Dict[str, float] = {}  # key → timestamp
        self._alert_history: List[Alert] = []
        self._max_history = 1000
        self._handlers: List[Callable] = []

        # 加载规则
        if rules_config:
            self.load_rules(rules_config)
        else:
            self._load_default_rules()

    def _load_default_rules(self):
        """加载默认规则"""
        for r in self.DEFAULT_RULES:
            self.rules.append(AlertRule(
                name=r["name"],
                condition=r["condition"],
                priority=r["priority"],
                message=r["message"],
                cooldown_seconds=r.get("cooldown", 300),
            ))
        logger.info(f"[AlertEngine] {len(self.rules)} 条默认规则已加载")

    def load_rules(self, config_path: str):
        """从YAML文件加载规则"""
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)

            self.rules = []
            for r in config.get("alerts", []):
                self.rules.append(AlertRule(**r))

            logger.info(f"[AlertEngine] 从{config_path}加载{len(self.rules)}条规则")
        except Exception as e:
            logger.warning(f"[AlertEngine] 规则加载失败: {e}, 使用默认规则")
            self._load_default_rules()

    def save_rules(self, config_path: str):
        """保存规则到YAML"""
        config = {
            "alerts": [
                {
                    "name": r.name,
                    "condition": r.condition,
                    "priority": r.priority,
                    "message": r.message,
                    "cooldown_seconds": r.cooldown_seconds,
                    "enabled": r.enabled,
                }
                for r in self.rules
            ]
        }
        with open(config_path, "w") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    def add_rule(self, rule: AlertRule):
        self.rules.append(rule)

    def remove_rule(self, name: str):
        self.rules = [r for r in self.rules if r.name != name]

    def on_alert(self, handler: Callable):
        """注册告警处理器"""
        self._handlers.append(handler)

    def evaluate(self, stock_data: Dict[str, Any]) -> List[Alert]:
        """
        评估单只股票的所有规则
        Args:
            stock_data: {"code":..., "price":..., "pnl_pct":...,
                          "volume_ratio":..., "day_change":...,
                          "ma20":..., "rsi14":..., "consecutive_down_days":...}
        Returns:
            触发的告警列表
        """
        alerts = []
        code = stock_data.get("code", "")

        for rule in self.rules:
            if not rule.enabled:
                continue

            # 冷却检查
            key = f"{code}_{rule.name}"
            last = self._last_triggered.get(key, 0)
            if time.time() - last < rule.cooldown_seconds:
                continue

            # 条件评估
            try:
                if self._check_condition(rule.condition, stock_data):
                    alert = Alert(rule, code, stock_data.get("name", ""), {
                        k: v for k, v in stock_data.items()
                        if k in ("price", "pnl_pct", "volume_ratio", "day_change",
                                 "ma20", "rsi14", "consecutive_down_days")
                    })
                    alerts.append(alert)
                    self._last_triggered[key] = time.time()
                    self._alert_history.append(alert)

                    # 限制历史长度
                    if len(self._alert_history) > self._max_history:
                        self._alert_history = self._alert_history[-self._max_history:]
            except Exception as e:
                logger.debug(f"[AlertEngine] 规则'{rule.name}'评估异常: {e}")

        # 触发处理器
        for alert in alerts:
            for handler in self._handlers:
                try:
                    handler(alert)
                except Exception:
                    pass

        return alerts

    def _check_condition(self, condition: str, data: Dict) -> bool:
        """安全评估告警条件表达式"""
        allowed = {
            "pnl_pct": data.get("pnl_pct", 0),
            "volume_ratio": data.get("volume_ratio", 1),
            "day_change": data.get("day_change", 0),
            "price": data.get("price", 0),
            "ma20": data.get("ma20", data.get("price", 0)),
            "ma60": data.get("ma60", data.get("price", 0)),
            "rsi14": data.get("rsi14", 50),
            "consecutive_down_days": data.get("consecutive_down_days", 0),
        }
        try:
            return bool(eval(condition, {"__builtins__": {}}, allowed))
        except Exception:
            return False

    def get_history(self, limit: int = 50) -> List[Dict]:
        """获取告警历史"""
        alerts = self._alert_history[-limit:]
        return [
            {
                "rule": a.rule_name,
                "code": a.code,
                "priority": a.priority,
                "message": a.message,
                "timestamp": a.timestamp,
                "acknowledged": a.acknowledged,
            }
            for a in alerts
        ]

    def acknowledge(self, code: str, rule_name: str = None):
        """确认告警"""
        for a in self._alert_history:
            if a.code == code and (rule_name is None or a.rule_name == rule_name):
                a.acknowledged = True

    def get_stats(self) -> Dict[str, int]:
        """告警统计"""
        today = datetime.now().strftime("%Y-%m-%d")
        today_alerts = [a for a in self._alert_history if a.timestamp.startswith(today)]

        by_priority = {"urgent": 0, "high": 0, "normal": 0, "low": 0}
        for a in today_alerts:
            by_priority[a.priority] = by_priority.get(a.priority, 0) + 1

        return {
            "total_today": len(today_alerts),
            "total_all": len(self._alert_history),
            "by_priority": by_priority,
            "rules_count": len(self.rules),
        }


# 全局实例
alert_engine = AlertEngine()
