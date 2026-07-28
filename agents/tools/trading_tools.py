"""
Agent Trading Tools — 模拟交易工具集
Agent可调用这些函数执行模拟交易、查询持仓
"""
from typing import Dict, List, Any, Optional
from datetime import date, datetime
from loguru import logger


class TradingTools:
    """模拟交易工具集"""

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Dict] = {}
        self.commission = 0.0005
        self.stamp_tax = 0.001
        self._load_positions()  # 从SQLite恢复持仓

    def execute_buy(self, code: str, name: str = "", price: float = 0,
                    amount: float = 0, shares: int = 0,
                    strategy_id: str = "", reason: str = "") -> Dict[str, Any]:
        """
        执行模拟买入
        Args:
            code: 股票代码
            name: 股票名称
            price: 买入价格 (0=市价)
            amount: 买入金额
            shares: 买入股数 (优先)
            strategy_id: 策略ID
            reason: 买入理由
        Returns:
            {"status": "ok"/"failed", "detail": {...}}
        """
        try:
            if code in self.positions:
                return {"status": "failed", "error": f"{code} 已持仓"}

            if price <= 0:
                # 尝试获取实时价格
                from agents.tools.data_tools import data_tools
                quote = data_tools.get_realtime_quote([code])
                if code in quote and quote[code].get("price", 0) > 0:
                    price = quote[code]["price"]
                else:
                    return {"status": "failed", "error": f"无法获取{code}价格"}

            # 计算买入数量
            if shares <= 0:
                if amount <= 0:
                    amount = min(self.cash * 0.25, 50000)  # 默认25%仓位
                shares = int(amount / price / 100) * 100

            if shares < 100:
                return {"status": "failed", "error": "买入数量不足100股"}

            cost = price * shares * (1 + self.commission)
            if cost > self.cash:
                return {"status": "failed", "error": f"资金不足: 需要{cost:.0f}, 可用{self.cash:.0f}"}

            self.cash -= cost
            self.positions[code] = {
                "code": code,
                "name": name,
                "entry_date": date.today().strftime("%Y-%m-%d"),
                "entry_price": price,
                "shares": shares,
                "cost": cost,
                "strategy_id": strategy_id,
                "reason": reason,
            }

            # 记录到数据库 + 持久化持仓
            self._log_trade(code, name, "buy", price, shares, strategy_id, reason)
            self._save_positions()

            logger.info(f"[TradingTools] 买入 {name}({code}): {shares}股 @{price:.2f}")

            return {
                "status": "ok",
                "detail": {
                    "code": code,
                    "name": name,
                    "price": price,
                    "shares": shares,
                    "cost": round(cost, 2),
                    "remaining_cash": round(self.cash, 2),
                }
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def execute_sell(self, code: str, price: float = 0,
                     reason: str = "") -> Dict[str, Any]:
        """
        执行模拟卖出
        """
        try:
            if code not in self.positions:
                return {"status": "failed", "error": f"未持仓 {code}"}

            pos = self.positions.pop(code)

            if price <= 0:
                from agents.tools.data_tools import data_tools
                quote = data_tools.get_realtime_quote([code])
                if code in quote and quote[code].get("price", 0) > 0:
                    price = quote[code]["price"]
                else:
                    return {"status": "failed", "error": f"无法获取{code}卖出价格"}

            income = price * pos["shares"] * (1 - self.commission - self.stamp_tax)
            pnl = income - pos["cost"]
            pnl_pct = (price / pos["entry_price"] - 1) * 100
            hold_days = (date.today() - date.fromisoformat(pos["entry_date"])).days

            self.cash += income

            self._log_trade(code, pos["name"], "sell", price, pos["shares"],
                          pos.get("strategy_id", ""), reason,
                          pnl=pnl, pnl_pct=pnl_pct, hold_days=hold_days)
            self._save_positions()

            logger.info(f"[TradingTools] 卖出 {pos['name']}({code}): "
                       f"盈亏={pnl:.2f} ({pnl_pct:.1f}%), 现金={self.cash:.0f}")

            return {
                "status": "ok",
                "detail": {
                    "code": code,
                    "name": pos["name"],
                    "entry_price": pos["entry_price"],
                    "exit_price": price,
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "hold_days": hold_days,
                    "remaining_cash": round(self.cash, 2),
                }
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """获取组合摘要"""
        total_cost = sum(p["cost"] for p in self.positions.values())

        # 尝试获取当前市值
        from agents.tools.data_tools import data_tools
        codes = list(self.positions.keys())
        quotes = data_tools.get_realtime_quote(codes) if codes else {}

        current_value = 0
        for code, pos in self.positions.items():
            if code in quotes:
                price = quotes[code].get("price", pos["entry_price"])
            else:
                price = pos["entry_price"]
            current_value += price * pos["shares"]

        return {
            "cash": round(self.cash, 2),
            "positions_count": len(self.positions),
            "total_cost": round(total_cost, 2),
            "current_value": round(current_value, 2),
            "total_value": round(self.cash + current_value, 2),
            "total_pnl": round(self.cash + current_value - self.initial_capital, 2),
            "total_pnl_pct": round((self.cash + current_value) / self.initial_capital - 1, 4) * 100,
            "positions": [
                {
                    "code": p["code"],
                    "name": p["name"],
                    "entry_price": p["entry_price"],
                    "shares": p["shares"],
                    "current_price": quotes.get(p["code"], {}).get("price", p["entry_price"]),
                    "strategy": p.get("strategy_id", ""),
                }
                for p in self.positions.values()
            ],
        }

    def _load_positions(self):
        """从SQLite恢复持仓状态"""
        try:
            from data.storage.sqlite_storage import storage
            today = date.today().strftime("%Y-%m-%d")
            conn = storage.get_conn()
            rows = conn.execute(
                "SELECT * FROM position_snapshots WHERE date=?",
                (today,)
            ).fetchall()
            conn.close()

            for row in rows:
                r = dict(row)
                code = r["stock_code"]
                self.positions[code] = {
                    "code": code,
                    "name": r.get("stock_name", ""),
                    "entry_date": r["date"],
                    "entry_price": r["entry_price"],
                    "shares": r["shares"],
                    "cost": r["entry_price"] * r["shares"],
                    "strategy_id": r.get("strategy_id", ""),
                    "reason": "",
                }
                self.cash -= r["entry_price"] * r["shares"] * (1 + self.commission)

            if self.positions:
                logger.info(f"[TradingTools] 从数据库恢复 {len(self.positions)} 个持仓, 现金: ¥{self.cash:,.0f}")
        except Exception as e:
            logger.debug(f"[TradingTools] 恢复持仓跳过: {e}")

    def _save_positions(self):
        """持久化持仓到SQLite"""
        try:
            from data.storage.sqlite_storage import storage
            today = date.today().strftime("%Y-%m-%d")
            conn = storage.get_conn()

            # 删除今日旧快照
            conn.execute("DELETE FROM position_snapshots WHERE date=?", (today,))

            # 保存当前持仓
            for code, pos in self.positions.items():
                conn.execute("""
                    INSERT INTO position_snapshots
                    (date, stock_code, stock_name, shares, entry_price, current_price,
                     pnl, pnl_pct, strategy_id, is_sim)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    today, code, pos.get("name", ""), pos["shares"],
                    pos["entry_price"], pos["entry_price"],  # current_price will be updated later
                    0, 0, pos.get("strategy_id", ""),
                ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[TradingTools] 持仓保存失败: {e}")

    def _log_trade(self, code: str, name: str, direction: str, price: float,
                   shares: int, strategy_id: str, reason: str,
                   pnl: float = None, pnl_pct: float = None, hold_days: int = None):
        """记录交易到数据库"""
        try:
            from data.storage.sqlite_storage import storage
            storage.save_trade({
                "stock_code": code,
                "stock_name": name,
                "direction": direction,
                "entry_date": date.today().strftime("%Y-%m-%d") if direction == "buy" else None,
                "entry_price": price if direction == "buy" else None,
                "exit_date": date.today().strftime("%Y-%m-%d") if direction == "sell" else None,
                "exit_price": price if direction == "sell" else None,
                "shares": shares,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "hold_days": hold_days,
                "strategy_id": strategy_id,
                "exit_reason": reason,
                "is_sim": 1,
            })
        except Exception as e:
            logger.warning(f"[TradingTools] 交易日志失败: {e}")


# 工具函数schema
TRADING_TOOLS_SCHEMA = [
    {
        "name": "execute_buy",
        "description": "执行模拟买入",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码"},
                "name": {"type": "string", "description": "股票名称"},
                "price": {"type": "number", "description": "买入价格(0=市价)"},
                "amount": {"type": "number", "description": "买入金额"},
                "shares": {"type": "integer", "description": "买入股数(优先于amount)"},
                "strategy_id": {"type": "string", "description": "策略ID"},
                "reason": {"type": "string", "description": "买入理由"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "execute_sell",
        "description": "执行模拟卖出",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码"},
                "price": {"type": "number", "description": "卖出价格(0=市价)"},
                "reason": {"type": "string", "description": "卖出理由"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "get_portfolio_summary",
        "description": "获取当前模拟盘组合摘要",
        "parameters": {"type": "object", "properties": {}},
    },
]

# 全局实例
trading_tools = TradingTools()
