"""
Agent Analysis Tools — 分析工具集
Agent可调用这些函数进行技术分析、风险评估、策略回测
"""
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
from loguru import logger


class AnalysisTools:
    """分析工具集"""

    # === 技术指标 ===

    def compute_indicators(self, kline_data: List[Dict]) -> Dict[str, Any]:
        """
        计算技术指标
        Args:
            kline_data: K线列表 [{"date":..., "close":..., "high":..., "low":..., "volume":...}, ...]
        Returns:
            {"ma":..., "macd":..., "rsi":..., "bollinger":..., "volume_ratio":...}
        """
        if not kline_data or len(kline_data) < 20:
            return {"error": "数据不足，需要至少20个交易日"}

        df = pd.DataFrame(kline_data)
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        volume = df["volume"].astype(float)

        last = len(df) - 1

        indicators = {
            "ma": {
                "ma5": round(close.rolling(5).mean().iloc[last], 2),
                "ma10": round(close.rolling(10).mean().iloc[last], 2),
                "ma20": round(close.rolling(20).mean().iloc[last], 2),
                "ma60": round(close.rolling(60).mean().iloc[last], 2) if len(df) >= 60 else None,
                "alignment": self._ma_alignment(close),  # "bullish" | "bearish" | "mixed"
            },
            "macd": self._compute_macd(close),
            "rsi": {
                "rsi6": round(self._compute_rsi(close, 6), 1),
                "rsi14": round(self._compute_rsi(close, 14), 1),
                "rsi24": round(self._compute_rsi(close, 24), 1),
            },
            "bollinger": self._compute_bollinger(close),
            "volume": {
                "vol_ratio_5": round(volume.iloc[last] / volume.iloc[-6:-1].mean(), 2) if len(df) > 5 else 1,
                "vol_ratio_20": round(volume.iloc[last] / volume.tail(20).mean(), 2),
            },
            "price_position": {
                "vs_ma20": round((close.iloc[last] / close.rolling(20).mean().iloc[last] - 1) * 100, 1),
                "high_20d": round(high.tail(20).max(), 2),
                "low_20d": round(low.tail(20).min(), 2),
                "drawdown_20d": round((close.iloc[last] / high.tail(20).max() - 1) * 100, 1),
            },
        }

        return indicators

    def _ma_alignment(self, close: pd.Series) -> str:
        """判断均线排列"""
        ma5 = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else ma20

        if ma5 > ma20 > ma60:
            return "bullish"
        elif ma5 < ma20 < ma60:
            return "bearish"
        else:
            return "mixed"

    def _compute_macd(self, close: pd.Series) -> Dict:
        """计算MACD"""
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        bar = 2 * (dif - dea)

        last = len(close) - 1
        return {
            "dif": round(dif.iloc[last], 4),
            "dea": round(dea.iloc[last], 4),
            "bar": round(bar.iloc[last], 4),
            "signal": "golden_cross" if dif.iloc[last] > dea.iloc[last] and dif.iloc[last-1] <= dea.iloc[last-1]
                      else "dead_cross" if dif.iloc[last] < dea.iloc[last] and dif.iloc[last-1] >= dea.iloc[last-1]
                      else "bullish" if dif.iloc[last] > dea.iloc[last]
                      else "bearish",
        }

    def _compute_rsi(self, close: pd.Series, period: int = 14) -> float:
        """计算RSI"""
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, 1)
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]

    def _compute_bollinger(self, close: pd.Series, period: int = 20, std: int = 2) -> Dict:
        """计算布林带"""
        ma = close.rolling(period).mean()
        std_val = close.rolling(period).std()
        upper = ma + std * std_val
        lower = ma - std * std_val

        last = len(close) - 1
        price = close.iloc[last]
        bandwidth = (upper.iloc[last] - lower.iloc[last]) / ma.iloc[last]

        return {
            "upper": round(upper.iloc[last], 2),
            "middle": round(ma.iloc[last], 2),
            "lower": round(lower.iloc[last], 2),
            "bandwidth": round(bandwidth * 100, 2),
            "position": "upper_break" if price > upper.iloc[last]
                        else "lower_break" if price < lower.iloc[last]
                        else "inside",
        }

    # === 风险评估 ===

    def assess_risk(self, positions: List[Dict], market_data: Dict = None) -> Dict[str, Any]:
        """
        持仓风险评估
        Args:
            positions: [{"code":..., "entry_price":..., "current_price":..., "shares":..., "pnl_pct":...}, ...]
            market_data: 大盘数据
        Returns:
            {"total_risk":..., "concentration_risk":..., "var":..., "recommendations":[...]}
        """
        if not positions:
            return {"total_risk": "none", "message": "无持仓"}

        total_value = sum(p.get("current_price", p.get("entry_price", 0)) * p.get("shares", 0)
                         for p in positions)
        total_pnl = sum(p.get("pnl_pct", 0) or 0 for p in positions)

        risks = []
        total_risk_score = 0

        # 1. 集中度风险
        if len(positions) <= 2:
            total_risk_score += 2
            risks.append("持仓过于集中(≤2只), 分散度不足")
        elif len(positions) > 8:
            total_risk_score += 1
            risks.append("持仓数量过多(>8只), 难以管理")

        # 2. 回撤风险
        max_loss = min((p.get("pnl_pct", 0) or 0 for p in positions), default=0)
        if max_loss < -5:
            total_risk_score += 2
            risks.append(f"最大单票亏损{max_loss:.1f}%, 建议考虑止损")

        # 3. 总体盈亏
        if total_pnl < -3:
            total_risk_score += 1
            risks.append(f"总盈亏{total_pnl:.1f}%, 需关注")

        risk_level = "low"
        if total_risk_score >= 4:
            risk_level = "high"
        elif total_risk_score >= 2:
            risk_level = "medium"

        return {
            "total_risk": risk_level,
            "risk_score": total_risk_score,
            "total_value": round(total_value, 2),
            "total_pnl_pct": round(total_pnl, 2),
            "concerns": risks,
            "recommendations": self._generate_risk_recommendations(positions, total_risk_score),
        }

    def _generate_risk_recommendations(self, positions: List[Dict], risk_score: int) -> List[str]:
        """生成风险建议"""
        recs = []
        if risk_score >= 3:
            recs.append("建议减仓至更安全水平")

        for p in positions:
            pnl = p.get("pnl_pct", 0) or 0
            if pnl < -5:
                recs.append(f"{p.get('code','')}亏损{pnl:.1f}%, 建议止损")
            elif pnl > 10:
                recs.append(f"{p.get('code','')}盈利{pnl:.1f}%, 考虑移动止盈")

        return recs or ["当前无特别风险建议"]

    # === 绩效归因 ===

    def performance_attribution(self, trades: List[Dict]) -> Dict[str, Any]:
        """
        交易绩效归因分析
        Args:
            trades: [{"pnl":..., "strategy_id":..., "hold_days":..., "exit_reason":...}, ...]
        Returns:
            {"by_strategy":..., "by_exit_reason":..., "win_rate_by_hold_days":...}
        """
        if not trades:
            return {"message": "无交易记录"}

        df = pd.DataFrame(trades)

        attribution = {
            "total_trades": len(df),
            "total_pnl": round(df["pnl"].sum(), 2),
            "win_rate": round((df["pnl"] > 0).sum() / len(df) * 100, 1),
        }

        # 按策略归因
        if "strategy_id" in df.columns:
            by_strategy = df.groupby("strategy_id").agg(
                trades=("pnl", "count"),
                total_pnl=("pnl", "sum"),
                win_rate=("pnl", lambda x: (x > 0).sum() / len(x) * 100),
                avg_return=("pnl", "mean"),
            ).round(2)
            attribution["by_strategy"] = by_strategy.to_dict()

        # 按出场原因归因
        if "exit_reason" in df.columns:
            by_reason = df.groupby("exit_reason").agg(
                count=("pnl", "count"),
                avg_pnl=("pnl", "mean"),
            ).round(2)
            attribution["by_exit_reason"] = by_reason.to_dict()

        return attribution


# 工具函数schema
ANALYSIS_TOOLS_SCHEMA = [
    {
        "name": "compute_indicators",
        "description": "计算技术指标(MA/MACD/RSI/布林带/量比/位置)",
        "parameters": {
            "type": "object",
            "properties": {
                "kline_data": {"type": "array", "description": "K线数据列表, 每项含close/high/low/volume"},
            },
            "required": ["kline_data"],
        },
    },
    {
        "name": "assess_risk",
        "description": "评估持仓风险(集中度/回撤/VaR)",
        "parameters": {
            "type": "object",
            "properties": {
                "positions": {"type": "array", "description": "持仓列表"},
                "market_data": {"type": "object", "description": "大盘数据(可选)"},
            },
            "required": ["positions"],
        },
    },
    {
        "name": "performance_attribution",
        "description": "交易绩效归因分析(按策略/出场原因等)",
        "parameters": {
            "type": "object",
            "properties": {
                "trades": {"type": "array", "description": "交易记录列表"},
            },
            "required": ["trades"],
        },
    },
]

# 全局实例
analysis_tools = AnalysisTools()
