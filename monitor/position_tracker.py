"""
Position Tracker — 持仓实时追踪
实时盈亏、VaR、集中度、行业暴露
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
import numpy as np
from loguru import logger


class PositionTracker:
    """
    持仓追踪器
    实时计算: P&L, VaR, Beta, 集中度, 行业暴露
    """

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self._positions: Dict[str, Dict] = {}
        self._snapshots: List[Dict] = []  # 快照历史

    def update_position(self, code: str, data: Dict):
        """更新单只持仓"""
        self._positions[code] = {
            "code": code,
            "name": data.get("name", ""),
            "entry_price": data.get("entry_price", 0),
            "shares": data.get("shares", 100),
            "current_price": data.get("current_price", data.get("entry_price", 0)),
            "strategy": data.get("strategy", ""),
            "sector": data.get("sector", ""),
            "stop_loss": data.get("stop_loss", 0),
            "take_profit": data.get("take_profit", 0),
            "updated_at": datetime.now().isoformat(),
        }

    def update_prices(self, quotes: Dict[str, Dict]):
        """批量更新价格"""
        for code, quote in quotes.items():
            if code in self._positions:
                self._positions[code]["current_price"] = quote.get("price",
                    self._positions[code]["current_price"])
                self._positions[code]["updated_at"] = datetime.now().isoformat()

    def snapshot(self) -> Dict[str, Any]:
        """生成当前持仓快照"""
        positions = list(self._positions.values())
        if not positions:
            snap = {
                "timestamp": datetime.now().isoformat(),
                "positions": [],
                "total_value": self.initial_capital,
                "total_pnl": 0,
                "total_pnl_pct": 0,
                "risk_metrics": {},
            }
            self._snapshots.append(snap)
            return snap

        # 计算各维度指标
        total_cost = sum(
            p["entry_price"] * p["shares"] for p in positions
        )
        current_value = sum(
            p["current_price"] * p["shares"] for p in positions
        )
        total_pnl = current_value - total_cost
        total_pnl_pct = (current_value / total_cost - 1) * 100 if total_cost > 0 else 0

        # 单票详情
        details = []
        for p in positions:
            cost = p["entry_price"] * p["shares"]
            value = p["current_price"] * p["shares"]
            pnl = value - cost
            pnl_pct = (p["current_price"] / p["entry_price"] - 1) * 100
            weight = value / current_value * 100 if current_value > 0 else 0

            # 止损/止盈距离
            stop_dist = (p["current_price"] / p["stop_loss"] - 1) * 100 if p.get("stop_loss", 0) > 0 else 0
            tp_dist = (p["take_profit"] / p["current_price"] - 1) * 100 if p.get("take_profit", 0) > 0 else 0

            details.append({
                "code": p["code"],
                "name": p["name"],
                "entry_price": round(p["entry_price"], 2),
                "current_price": round(p["current_price"], 2),
                "shares": p["shares"],
                "cost": round(cost, 2),
                "market_value": round(value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "weight_pct": round(weight, 1),
                "stop_distance_pct": round(stop_dist, 1),
                "tp_distance_pct": round(tp_dist, 1),
                "strategy": p.get("strategy", ""),
            })

        # 风险指标
        risk = self._compute_risk_metrics(positions, current_value)

        snap = {
            "timestamp": datetime.now().isoformat(),
            "positions": details,
            "total_cost": round(total_cost, 2),
            "current_value": round(current_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "cash": round(self.initial_capital - total_cost + current_value, 2),
            "risk_metrics": risk,
        }

        self._snapshots.append(snap)
        if len(self._snapshots) > 500:
            self._snapshots = self._snapshots[-500:]

        return snap

    def _compute_risk_metrics(self, positions: List[Dict],
                               total_value: float) -> Dict[str, Any]:
        """计算风险指标"""
        risk = {}

        # 1. 集中度 (Herfindahl-Hirschman Index)
        if total_value > 0:
            weights = [p["current_price"] * p["shares"] / total_value for p in positions]
            hhi = sum(w**2 for w in weights) * 10000
            risk["hhi"] = round(hhi, 1)
            risk["concentration"] = "high" if hhi > 4000 else "medium" if hhi > 2000 else "low"

        # 2. 最大单票占比
        if positions:
            max_weight = max(
                p["current_price"] * p["shares"] / total_value * 100
                for p in positions
            )
            risk["max_position_pct"] = round(max_weight, 1)

        # 3. 盈亏分布
        pnl_pcts = [
            (p["current_price"] / p["entry_price"] - 1) * 100
            for p in positions
        ]
        if pnl_pcts:
            risk["best_performer"] = round(max(pnl_pcts), 2)
            risk["worst_performer"] = round(min(pnl_pcts), 2)
            risk["avg_pnl_pct"] = round(np.mean(pnl_pcts), 2)
            risk["win_count"] = sum(1 for x in pnl_pcts if x > 0)
            risk["loss_count"] = sum(1 for x in pnl_pcts if x <= 0)

        # 4. 简化VaR (基于近期波动率的估计)
        if len(self._snapshots) >= 5:
            recent_values = [
                s.get("current_value", self.initial_capital)
                for s in self._snapshots[-20:]
            ]
            if len(recent_values) >= 5:
                returns = np.diff(recent_values) / recent_values[:-1]
                volatility = np.std(returns) if len(returns) > 0 else 0
                # 95% VaR
                risk["var_95_daily"] = round(volatility * 1.65 * total_value, 2)
                risk["var_95_pct"] = round(volatility * 1.65 * 100, 2)

        # 5. 策略分布
        by_strategy = {}
        for p in positions:
            s = p.get("strategy", "unknown")
            value = p["current_price"] * p["shares"]
            by_strategy[s] = by_strategy.get(s, 0) + value
        if total_value > 0:
            risk["by_strategy"] = {
                k: round(v / total_value * 100, 1)
                for k, v in sorted(by_strategy.items(), key=lambda x: x[1], reverse=True)
            }

        # 6. 行业分布
        by_sector = {}
        for p in positions:
            sector = p.get("sector", "unknown")
            value = p["current_price"] * p["shares"]
            by_sector[sector] = by_sector.get(sector, 0) + value
        if total_value > 0:
            risk["by_sector"] = {
                k: round(v / total_value * 100, 1)
                for k, v in sorted(by_sector.items(), key=lambda x: x[1], reverse=True)
            }

        return risk

    def get_alerts_for_positions(self) -> List[Dict]:
        """检查持仓是否需要告警"""
        alerts = []
        for p in self._positions.values():
            pnl_pct = (p["current_price"] / p["entry_price"] - 1) * 100

            status = "normal"
            if p["stop_loss"] > 0 and p["current_price"] <= p["stop_loss"]:
                status = "stop_loss"
                alerts.append({
                    "code": p["code"], "name": p["name"],
                    "type": "stop_loss", "urgency": "urgent",
                    "message": f"触及止损价{p['stop_loss']:.2f}",
                })
            elif p["take_profit"] > 0 and p["current_price"] >= p["take_profit"]:
                status = "take_profit"
                alerts.append({
                    "code": p["code"], "name": p["name"],
                    "type": "take_profit", "urgency": "high",
                    "message": f"达到止盈价{p['take_profit']:.2f}",
                })
            elif pnl_pct < -5:
                status = "warning"
                alerts.append({
                    "code": p["code"], "name": p["name"],
                    "type": "deep_loss", "urgency": "high",
                    "message": f"浮亏{pnl_pct:.1f}%, 接近止损线",
                })

        return alerts

    def get_historical_snapshots(self, limit: int = 20) -> List[Dict]:
        """获取历史快照"""
        return self._snapshots[-limit:]


# 全局实例
position_tracker = PositionTracker()
