"""
Monitor Agent — 实时盘中监控 (完整实现)
持仓追踪 + 告警规则评估 + LLM确认 + 推送建议
"""
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger

from core.agent_runner import BaseAgent, AgentRunResult
from core.context_manager import TradingContext
from agents.tools.data_tools import data_tools
from agents.tools.analysis_tools import analysis_tools
from agents.tools.notification_tools import notification_tools


class AlertEngine:
    """告警规则引擎"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        # 默认告警规则
        self.rules = self.config.get("rules", [
            {
                "name": "stop_loss",
                "condition": "pnl_pct <= -3.0",
                "priority": "urgent",
                "message": "触及止损线, 建议立即卖出",
            },
            {
                "name": "take_profit",
                "condition": "pnl_pct >= 8.0",
                "priority": "high",
                "message": "达到止盈目标, 建议卖出或移动止盈",
            },
            {
                "name": "volume_spike",
                "condition": "volume_ratio > 3.0",
                "priority": "normal",
                "message": "异常放量, 关注方向",
            },
            {
                "name": "drawdown_warning",
                "condition": "pnl_pct <= -5.0 and pnl_pct > -3.0",
                "priority": "high",
                "message": "亏损扩大, 需关注是否止损",
            },
            {
                "name": "price_break_ma20",
                "condition": "price < ma20 and pnl_pct < 0",
                "priority": "normal",
                "message": "跌破MA20且亏损, 关注趋势变化",
            },
            {
                "name": "gap_down",
                "condition": "day_change <= -5.0",
                "priority": "urgent",
                "message": "日内大幅下跌, 建议立即评估",
            },
        ])

    def evaluate(self, stock_data: Dict[str, Any]) -> List[Dict]:
        """
        评估单只股票的所有规则
        Args:
            stock_data: {"code":..., "price":..., "pnl_pct":..., "volume_ratio":..., ...}
        Returns:
            触发的告警列表
        """
        alerts = []
        for rule in self.rules:
            try:
                if self._check_condition(rule["condition"], stock_data):
                    alerts.append({
                        "rule": rule["name"],
                        "priority": rule["priority"],
                        "message": rule["message"],
                        "code": stock_data.get("code", ""),
                        "name": stock_data.get("name", ""),
                        "timestamp": datetime.now().isoformat(),
                        "data_snapshot": {
                            k: v for k, v in stock_data.items()
                            if k in ("price", "pnl_pct", "volume_ratio", "day_change")
                        },
                    })
            except Exception as e:
                logger.debug(f"[AlertEngine] 规则{rule['name']}评估失败: {e}")

        return alerts

    def _check_condition(self, condition: str, data: Dict) -> bool:
        """安全地评估告警条件"""
        # 安全的表达式评估 (只用基础比较)
        allowed_names = {
            "pnl_pct": data.get("pnl_pct", 0),
            "volume_ratio": data.get("volume_ratio", 1),
            "day_change": data.get("day_change", 0),
            "price": data.get("price", 0),
            "ma20": data.get("ma20", 0),
        }
        try:
            return eval(condition, {"__builtins__": {}}, allowed_names)
        except Exception:
            return False


class MonitorAgent(BaseAgent):
    """实时监控Agent — 交易时段持续运行"""

    agent_name = "monitor_agent"
    agent_description = "实时盘中监控: 持仓追踪 + 告警规则评估 + LLM二次确认 + 推送操作建议"

    def __init__(self):
        super().__init__()
        self.alert_engine = AlertEngine()
        self._last_check: Dict[str, float] = {}  # code → last_alert_time

    def run(self, context: TradingContext = None, **kwargs) -> AgentRunResult:
        """
        单次监控检查
        用于定时轮询(每30秒)或事件触发
        """
        logger.debug("[Monitor Agent] 检查...")
        t0 = time.time()

        try:
            event = kwargs.get("event")

            # 获取持仓
            positions = self._get_positions(context)
            if not positions:
                return AgentRunResult(self.agent_name, "completed",
                                     output={"positions": 0, "alerts": 0})

            # 获取实时行情
            codes = list(positions.keys())
            quotes = data_tools.get_realtime_quote(codes)

            # 更新持仓价格
            for code, pos in positions.items():
                if code in quotes:
                    pos["price"] = quotes[code].get("price", pos.get("entry_price", 0))
                    pos["day_change"] = quotes[code].get("change_pct", 0)
                    pos["pnl_pct"] = (pos["price"] / pos["entry_price"] - 1) * 100

            # 评估告警
            all_alerts = []
            for code, pos in positions.items():
                if pos.get("price", 0) <= 0:
                    continue

                # 计算技术指标
                kline = data_tools.get_kline(code, days=60)
                if kline.get("data"):
                    indicators = analysis_tools.compute_indicators(kline["data"])
                    pos["ma20"] = indicators.get("ma", {}).get("ma20")
                    pos["volume_ratio"] = indicators.get("volume", {}).get("vol_ratio_5", 1)

                # 评估规则
                alerts = self.alert_engine.evaluate(pos)
                for alert in alerts:
                    # 防抖: 同一股票同一规则5分钟内不重复告警
                    key = f"{code}_{alert['rule']}"
                    last = self._last_check.get(key, 0)
                    if time.time() - last < 300:
                        continue
                    self._last_check[key] = time.time()
                    all_alerts.append(alert)

            # 处理告警
            if all_alerts:
                logger.info(f"[Monitor] {len(all_alerts)} 个告警触发")
                self._handle_alerts(all_alerts, context)

            duration_ms = (time.time() - t0) * 1000
            return AgentRunResult(
                agent_name=self.agent_name,
                status="completed",
                output={
                    "positions": len(positions),
                    "alerts": len(all_alerts),
                    "quotes_updated": len(quotes),
                },
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"[Monitor Agent] 失败: {e}")
            return AgentRunResult(self.agent_name, "failed", error=str(e))

    def _get_positions(self, context) -> Dict[str, Dict]:
        """获取持仓数据"""
        positions = {}

        if context and context.positions:
            for code, pos in context.positions.items():
                positions[code] = {
                    "code": code,
                    "name": pos.name,
                    "entry_price": pos.entry_price,
                    "price": pos.current_price,
                    "shares": pos.shares,
                    "pnl_pct": pos.pnl_pct,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                }
            return positions

        # 从模拟盘获取
        try:
            from agents.tools.trading_tools import trading_tools
            portfolio = trading_tools.get_portfolio_summary()
            for p in portfolio.get("positions", []):
                code = p["code"]
                positions[code] = {
                    "code": code,
                    "name": p["name"],
                    "entry_price": p["entry_price"],
                    "price": p.get("current_price", p["entry_price"]),
                    "shares": p["shares"],
                    "pnl_pct": (p["current_price"] / p["entry_price"] - 1) * 100,
                }
        except Exception:
            pass

        return positions

    def _handle_alerts(self, alerts: List[Dict], context):
        """处理告警: 推送 + LLM确认 (高优先级)"""
        urgent = [a for a in alerts if a["priority"] == "urgent"]
        high = [a for a in alerts if a["priority"] == "high"]
        normal = [a for a in alerts if a["priority"] == "normal"]

        # 紧急告警 → 立即推送 + LLM确认
        for alert in urgent:
            self._push_alert(alert, use_llm=True)

        # 高优先级 → 推送
        for alert in high[:3]:
            self._push_alert(alert, use_llm=len(high) <= 2)

        # 普通告警 → 聚合推送
        if normal and not urgent and not high:
            self._push_summary(normal)

        # 记录到上下文
        if context:
            for alert in alerts:
                context.add_alert(alert)

    def _push_alert(self, alert: Dict, use_llm: bool = False):
        """推送单个告警"""
        title = f"{'🔴' if alert['priority']=='urgent' else '🟠'} {alert['name']}({alert['code']})"

        body = f"{alert['message']}\n\n"
        snapshot = alert.get("data_snapshot", {})
        body += f"当前价格: {snapshot.get('price', 'N/A')}\n"
        body += f"盈亏: {snapshot.get('pnl_pct', 0):.1f}%\n"

        # LLM二次确认
        if use_llm:
            try:
                llm_suggestion = self._llm_confirm(alert)
                if llm_suggestion:
                    body += f"\n🤖 AI建议: {llm_suggestion}"
            except Exception:
                pass

        notification_tools.send_alert(
            title, body,
            priority=alert["priority"],
        )

    def _llm_confirm(self, alert: Dict) -> Optional[str]:
        """LLM对告警进行二次确认"""
        try:
            from config.llm_config import get_prompt, chat_json
            from config.settings import LLM_API_KEY
            if not LLM_API_KEY:
                return None

            prompt = get_prompt("monitor_alert",
                stock_code=alert.get("code", ""),
                stock_name=alert.get("name", ""),
                alert_type=alert.get("rule", ""),
                current_price=str(alert.get("data_snapshot", {}).get("price", "N/A")),
                entry_price=str(alert.get("data_snapshot", {}).get("entry_price", "N/A")),
                pnl_pct=str(alert.get("data_snapshot", {}).get("pnl_pct", 0)),
                trigger_condition=alert.get("message", ""),
                market_depth="暂无深度数据",
                technical_indicators="暂无技术指标",
            )

            messages = [
                {"role": "system", "content": "你是实时交易监控员, 快速判断告警真伪并给出操作建议。"},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, temperature=0.1, use_cache=False)
            action = result.get("action", "hold")
            reason = result.get("reason", "")
            is_noise = result.get("is_noise", False)

            if is_noise:
                return None  # 噪声信号, 不推送
            return f"[{action}] {reason}"

        except Exception:
            return None

    def _push_summary(self, alerts: List[Dict]):
        """推送聚合告警摘要"""
        if not alerts:
            return

        codes = list(set(a["code"] for a in alerts))
        title = f"⚪ 监控提醒 ({len(alerts)}条)"
        body = "\n".join([
            f"- {a['name']}({a['code']}): {a['message']}"
            for a in alerts[:8]
        ])
        notification_tools.send_alert(title, body, priority="low")
