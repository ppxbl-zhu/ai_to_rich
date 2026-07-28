"""
Trading Skills — 模拟交易执行 + 策略扫描
每个Skill独立调用，可被Monitor/Select Agent动态使用
"""
from typing import Dict, Any, List
from datetime import date
from loguru import logger

from skills.base import BaseSkill, skill_registry


# ============================================================
# Skill: 模拟买入
# ============================================================
class SimBuySkill(BaseSkill):
    name = "execute_sim_buy"
    description = "在模拟盘执行买入操作(需要先获取实时价格), 返回成交详情。用于Agent下达交易指令。"
    schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "股票代码"},
            "name": {"type": "string", "description": "股票名称"},
            "price": {"type": "number", "description": "买入价格(0=市价)"},
            "amount": {"type": "number", "description": "买入金额(默认25000)"},
            "strategy": {"type": "string", "description": "策略名称"},
            "reason": {"type": "string", "description": "买入理由"},
        },
        "required": ["code"],
    }

    def execute(self, code: str = "", name: str = "", price: float = 0,
                amount: float = 25000, strategy: str = "manual", reason: str = "",
                **kwargs) -> Dict[str, Any]:
        try:
            from agents.tools.trading_tools import trading_tools

            result = trading_tools.execute_buy(
                code=code, name=name, price=price,
                amount=amount, strategy_id=strategy, reason=reason,
            )
            return result
        except Exception as e:
            return {"status": "failed", "error": str(e)}


# ============================================================
# Skill: 模拟卖出
# ============================================================
class SimSellSkill(BaseSkill):
    name = "execute_sim_sell"
    description = "在模拟盘执行卖出操作, 返回盈亏详情。"
    schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "股票代码"},
            "price": {"type": "number", "description": "卖出价格(0=市价)"},
            "reason": {"type": "string", "description": "卖出理由"},
        },
        "required": ["code"],
    }

    def execute(self, code: str = "", price: float = 0, reason: str = "",
                **kwargs) -> Dict[str, Any]:
        try:
            from agents.tools.trading_tools import trading_tools
            return trading_tools.execute_sell(code=code, price=price, reason=reason)
        except Exception as e:
            return {"status": "failed", "error": str(e)}


# ============================================================
# Skill: 组合摘要
# ============================================================
class PortfolioSkill(BaseSkill):
    name = "get_portfolio"
    description = "获取当前模拟盘组合摘要: 总资产、持仓数、盈亏、各持仓明细。"
    schema = {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            from agents.tools.trading_tools import trading_tools
            return trading_tools.get_portfolio_summary()
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# Skill: 策略扫描 (统一入口, 按类型分发)
# ============================================================
class ScanStrategySkill(BaseSkill):
    name = "scan_strategy"
    description = "运行指定策略扫描A股, 返回交易信号。支持: auction(竞价)/trend(趋势)/reversal(反转)/event(事件)。"
    schema = {
        "type": "object",
        "properties": {
            "strategy_type": {
                "type": "string",
                "enum": ["auction", "trend", "reversal", "event"],
                "description": "策略类型",
            },
        },
        "required": ["strategy_type"],
    }

    def execute(self, strategy_type: str = "auction", **kwargs) -> Dict[str, Any]:
        try:
            if strategy_type == "auction":
                from strategies.auction_strategy.runner import AuctionStrategy
                strategy = AuctionStrategy()
            elif strategy_type == "trend":
                from strategies.trend_strategy.runner import TrendStrategy
                strategy = TrendStrategy()
            elif strategy_type == "reversal":
                from strategies.reversal_strategy.runner import ReversalStrategy
                strategy = ReversalStrategy()
            elif strategy_type == "event":
                from strategies.event_strategy.runner import EventStrategy
                strategy = EventStrategy()
            else:
                return {"error": f"未知策略: {strategy_type}", "signals": []}

            signals = strategy.generate_signals()
            return {
                "strategy": strategy_type,
                "count": len(signals),
                "signals": [s.to_dict() for s in signals[:10]],
            }
        except Exception as e:
            return {"error": str(e), "strategy": strategy_type, "signals": []}


# 注册
skill_registry.register(SimBuySkill())
skill_registry.register(SimSellSkill())
skill_registry.register(PortfolioSkill())
skill_registry.register(ScanStrategySkill())
