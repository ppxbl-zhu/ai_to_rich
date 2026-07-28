"""
Analysis Skills — 技术分析 + 市场状态 + 风险评估
每个Skill独立调用，自带错误处理
"""
from typing import Dict, Any, List
import pandas as pd
import numpy as np
from loguru import logger

from skills.base import BaseSkill, skill_registry


# ============================================================
# Skill 1: 技术指标计算
# ============================================================
class ComputeIndicatorsSkill(BaseSkill):
    name = "compute_indicators"
    description = "计算个股技术指标(MA/MACD/RSI/布林带/量比/位置), 用于技术面分析。输入K线数据(至少20日), 返回完整指标。"
    schema = {
        "type": "object",
        "properties": {
            "kline_data": {
                "type": "array",
                "description": "K线数据, 每项含 open/high/low/close/volume, 至少20条",
            },
        },
        "required": ["kline_data"],
    }

    def execute(self, kline_data: List[Dict] = None, **kwargs) -> Dict[str, Any]:
        if not kline_data or len(kline_data) < 5:
            return {"error": "K线数据不足", "message": "需要至少5个交易日数据"}

        try:
            df = pd.DataFrame(kline_data)
            close = df["close"].astype(float)
            high = df["high"].astype(float)
            low = df["low"].astype(float)
            volume = df["volume"].astype(float)
            last = len(df) - 1

            # 均线
            ma = {
                "ma5": round(close.rolling(5).mean().iloc[last], 2),
                "ma10": round(close.rolling(10).mean().iloc[last], 2),
                "ma20": round(close.rolling(20).mean().iloc[last], 2) if len(df) >= 20 else None,
                "ma60": round(close.rolling(60).mean().iloc[last], 2) if len(df) >= 60 else None,
                "alignment": self._ma_align(close),
            }

            # MACD
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            dif = ema12 - ema26
            dea = dif.ewm(span=9, adjust=False).mean()
            macd = {
                "dif": round(float(dif.iloc[last]), 4),
                "dea": round(float(dea.iloc[last]), 4),
                "bar": round(float(2 * (dif.iloc[last] - dea.iloc[last])), 4),
                "signal": "golden_cross" if dif.iloc[last] > dea.iloc[last] and dif.iloc[last-1] <= dea.iloc[last-1]
                          else "dead_cross" if dif.iloc[last] < dea.iloc[last] and dif.iloc[last-1] >= dea.iloc[last-1]
                          else "bullish" if dif.iloc[last] > dea.iloc[last]
                          else "bearish",
            }

            # RSI
            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            rsi = {}
            for p in [6, 14, 24]:
                avg_g = gain.rolling(p).mean()
                avg_l = loss.rolling(p).mean()
                rs = avg_g / avg_l.replace(0, 1)
                rsi[f"rsi{p}"] = round(float(100 - (100 / (1 + rs)).iloc[last]), 1)

            # 布林带
            ma20_b = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            boll = {
                "upper": round(float((ma20_b + 2*std20).iloc[last]), 2),
                "middle": round(float(ma20_b.iloc[last]), 2),
                "lower": round(float((ma20_b - 2*std20).iloc[last]), 2),
            } if len(df) >= 20 else {}

            # 量比 + 位置
            vol_ratio_5 = round(float(volume.iloc[last] / volume.iloc[-6:-1].mean()), 2) if len(df) > 5 else 1
            position_20d = {
                "vs_ma20_pct": round(float((close.iloc[last] / ma20_b.iloc[last] - 1) * 100), 1) if len(df) >= 20 else 0,
                "high_20d": round(float(high.tail(20).max()), 2) if len(df) >= 20 else 0,
                "low_20d": round(float(low.tail(20).min()), 2) if len(df) >= 20 else 0,
            }

            return {
                "ma": ma, "macd": macd, "rsi": rsi,
                "bollinger": boll,
                "volume_ratio_5d": vol_ratio_5,
                "position": position_20d,
            }
        except Exception as e:
            return {"error": str(e)}

    def _ma_align(self, close: pd.Series) -> str:
        ma5 = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else ma20
        return "bullish" if ma5 > ma20 > ma60 else "bearish" if ma5 < ma20 < ma60 else "mixed"


# ============================================================
# Skill 2: K线形态检测
# ============================================================
class DetectPatternsSkill(BaseSkill):
    name = "detect_patterns"
    description = "检测K线经典技术形态(看涨吞没/锤子线/双底/均线突破/放量突破), 返回检测到的形态列表。"
    schema = {
        "type": "object",
        "properties": {
            "kline_data": {
                "type": "array",
                "description": "K线数据, 至少10条",
            },
        },
        "required": ["kline_data"],
    }

    def execute(self, kline_data: List[Dict] = None, **kwargs) -> Dict[str, Any]:
        if not kline_data or len(kline_data) < 5:
            return {"error": "数据不足", "patterns": []}

        try:
            df = pd.DataFrame(kline_data)
            close = df["close"].astype(float)
            open_ = df["open"].astype(float)
            high = df["high"].astype(float)
            low = df["low"].astype(float)
            volume = df["volume"].astype(float)
            last = len(df) - 1
            patterns = []

            # 看涨吞没
            if last >= 1:
                if (close.iloc[last] > open_.iloc[last] and
                    close.iloc[last-1] < open_.iloc[last-1] and
                    close.iloc[last] > open_.iloc[last-1]):
                    patterns.append({"name": "bullish_engulfing", "label": "看涨吞没", "confidence": 0.70})

            # 锤子线
            body = abs(close.iloc[last] - open_.iloc[last])
            lower_shadow = min(open_.iloc[last], close.iloc[last]) - low.iloc[last]
            if body > 0 and lower_shadow > body * 2:
                patterns.append({"name": "hammer", "label": "锤子线", "confidence": 0.60})

            # 双底 (最近20日内)
            if len(df) >= 20:
                rec_lows = low.tail(20)
                min1_idx = rec_lows.idxmin()
                rest = rec_lows.drop(min1_idx)
                if len(rest) > 3:
                    gap = abs(rec_lows.min() - rest.min()) / rec_lows.min() * 100
                    if gap < 3:
                        patterns.append({"name": "double_bottom", "label": "双底", "confidence": 0.65})

            # 均线突破
            if len(df) >= 20:
                ma20 = close.rolling(20).mean()
                if close.iloc[last] > ma20.iloc[last] and close.iloc[last-1] <= ma20.iloc[last-1]:
                    patterns.append({"name": "ma_breakout", "label": "均线突破", "confidence": 0.55})

            # 放量突破
            if len(df) >= 5:
                vol_ma5 = volume.tail(6).head(5).mean()
                if volume.iloc[last] > vol_ma5 * 2 and close.iloc[last] > open_.iloc[last]:
                    patterns.append({"name": "volume_breakout", "label": "放量突破", "confidence": 0.60})

            # 趋势
            ma5 = close.rolling(5).mean().iloc[last]
            ma20 = close.rolling(20).mean().iloc[last] if len(df) >= 20 else ma5
            trend = "上升" if ma5 > ma20 and close.iloc[last] > ma5 else \
                    "下降" if ma5 < ma20 and close.iloc[last] < ma5 else "震荡"

            return {
                "patterns": patterns,
                "count": len(patterns),
                "trend": trend,
            }
        except Exception as e:
            return {"error": str(e), "patterns": []}


# ============================================================
# Skill 3: 市场状态分类
# ============================================================
class ClassifyRegimeSkill(BaseSkill):
    name = "classify_market_regime"
    description = "分类当前A股市场状态(上升/下降/震荡/高波动/低波动/牛市/熊市), 并给出仓位建议和适配策略。"
    schema = {
        "type": "object",
        "properties": {
            "kline_data": {
                "type": "array",
                "description": "指数K线数据(上证/深证), 至少20日",
            },
        },
        "required": ["kline_data"],
    }

    SUGGESTIONS = {
        "trending_up":    {"position": 0.70, "strategies": ["trend", "auction"], "advice": "上升趋势, 积极参与"},
        "trending_down":  {"position": 0.20, "strategies": ["reversal"], "advice": "下降趋势, 轻仓操作"},
        "range_bound":    {"position": 0.50, "strategies": ["auction", "event"], "advice": "震荡行情, 高抛低吸"},
        "high_volatility":{"position": 0.25, "strategies": ["auction"], "advice": "高波动, 严控仓位"},
        "low_volatility": {"position": 0.60, "strategies": ["trend", "auction"], "advice": "低波动, 可适度放大"},
        "bull_market":    {"position": 0.85, "strategies": ["trend", "auction", "event", "reversal"], "advice": "牛市, 积极参与"},
        "bear_market":    {"position": 0.10, "strategies": [], "advice": "熊市, 以空仓为主"},
    }

    def execute(self, kline_data: List[Dict] = None, **kwargs) -> Dict[str, Any]:
        if not kline_data or len(kline_data) < 20:
            return {"regime": "unknown", "message": "数据不足", "suggestion": self.SUGGESTIONS["range_bound"]}

        try:
            df = pd.DataFrame(kline_data)
            close = df["close"].astype(float)
            volume = df["volume"].astype(float)

            # 趋势强度 — 线性回归斜率
            x = np.arange(min(20, len(close)))
            y = close.iloc[-20:].values if len(close) >= 20 else close.values
            slope = np.polyfit(x, y, 1)[0]
            trend_strength = slope / close.iloc[-1] * 100

            # 波动率 — 20日年化
            returns = close.pct_change().dropna()
            volatility = float(returns.tail(20).std() * np.sqrt(252)) if len(returns) >= 20 else 0.3

            # 量能趋势
            vol_ma5 = volume.rolling(5).mean()
            vol_ma20 = volume.rolling(20).mean()
            vol_trend = (vol_ma5.iloc[-1] / vol_ma20.iloc[-1] - 1) * 100 if len(df) >= 20 else 0

            # MA偏离
            ma5 = close.rolling(5).mean().iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]
            ma_spread = (ma5 / ma20 - 1) * 100

            # 分类
            if volatility > 0.35:         regime = "high_volatility"
            elif volatility < 0.10:       regime = "low_volatility"
            elif trend_strength > 1.0 and ma_spread > 3:  regime = "bull_market"
            elif trend_strength < -1.0 and ma_spread < -3: regime = "bear_market"
            elif trend_strength > 0.3 and ma_spread > 0:   regime = "trending_up"
            elif trend_strength < -0.3 and ma_spread < 0:  regime = "trending_down"
            else:                         regime = "range_bound"

            suggestion = self.SUGGESTIONS.get(regime, self.SUGGESTIONS["range_bound"])

            return {
                "regime": regime,
                "confidence": min(0.9, len(kline_data) / 60 * 0.5 + 0.3),
                "features": {
                    "trend_strength_pct": round(float(trend_strength), 3),
                    "volatility_annual": round(volatility, 3),
                    "volume_trend_pct": round(float(vol_trend), 1),
                    "ma_spread_pct": round(float(ma_spread), 2),
                },
                "suggestion": suggestion,
            }
        except Exception as e:
            return {"regime": "unknown", "error": str(e), "suggestion": self.SUGGESTIONS["range_bound"]}


# ============================================================
# Skill 4: 风险评估
# ============================================================
class AssessRiskSkill(BaseSkill):
    name = "assess_risk"
    description = "评估当前持仓的风险指标(集中度/最大回撤/盈亏分布), 并给出风控建议。"
    schema = {
        "type": "object",
        "properties": {
            "positions": {
                "type": "array",
                "description": "持仓列表 [{code, entry_price, current_price, shares, pnl_pct}, ...]",
            },
        },
        "required": ["positions"],
    }

    def execute(self, positions: List[Dict] = None, **kwargs) -> Dict[str, Any]:
        if not positions:
            return {"risk_level": "none", "message": "无持仓"}

        try:
            total_value = sum(
                p.get("current_price", p.get("entry_price", 0)) * p.get("shares", 0)
                for p in positions
            )
            pnl_pcts = [
                (p.get("current_price", 0) / p.get("entry_price", 1) - 1) * 100
                for p in positions if p.get("entry_price", 0) > 0
            ]

            # 集中度
            weights = [
                p.get("current_price", 0) * p.get("shares", 0) / total_value * 100
                for p in positions
            ] if total_value > 0 else [0]

            max_weight = max(weights) if weights else 0
            hhi = sum(w**2 for w in weights) * 100 if weights else 0

            # 风险评分 (0-10)
            risk_score = 0
            concerns = []

            if len(positions) <= 2:
                risk_score += 2; concerns.append("持仓过于集中")
            if max_weight > 40:
                risk_score += 3; concerns.append(f"单票占比{max_weight:.0f}%过高")
            if pnl_pcts:
                worst = min(pnl_pcts)
                if worst < -5:
                    risk_score += 2; concerns.append(f"最大亏损{worst:.1f}%")
                if sum(1 for x in pnl_pcts if x > 0) < len(pnl_pcts) / 2:
                    risk_score += 1; concerns.append("多数持仓浮亏")

            level = "low" if risk_score <= 1 else "medium" if risk_score <= 3 else "high" if risk_score <= 5 else "extreme"

            return {
                "risk_level": level, "risk_score": risk_score,
                "total_value": round(total_value, 2),
                "positions": len(positions),
                "max_single_pct": round(max_weight, 1),
                "hhi": round(hhi, 1),
                "best_pnl_pct": round(max(pnl_pcts), 2) if pnl_pcts else 0,
                "worst_pnl_pct": round(min(pnl_pcts), 2) if pnl_pcts else 0,
                "concerns": concerns,
                "advice": "建议立即减仓" if level == "extreme" else
                          "建议关注风险" if level == "high" else
                          "可继续持有" if level == "low" else "注意监控",
            }
        except Exception as e:
            return {"error": str(e), "risk_level": "unknown"}


# 注册
skill_registry.register(ComputeIndicatorsSkill())
skill_registry.register(DetectPatternsSkill())
skill_registry.register(ClassifyRegimeSkill())
skill_registry.register(AssessRiskSkill())
