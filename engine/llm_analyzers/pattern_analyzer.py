"""
Pattern Analyzer — LLM驱动的K线形态识别
识别经典技术形态: 突破、双底、头肩、杯柄等
"""
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
from loguru import logger


class PatternAnalyzer:
    """
    K线形态识别器 (规则引擎 + LLM辅助)
    先用规则引擎识别候选形态, 再用LLM确认
    """

    # 经典形态检测规则
    PATTERNS = {
        "bullish_engulfing": "看涨吞没",
        "hammer": "锤子线",
        "morning_star": "晨星",
        "double_bottom": "双底",
        "ascending_triangle": "上升三角形",
        "ma_breakout": "均线突破",
        "volume_breakout": "放量突破",
    }

    def detect(self, kline_data: List[Dict]) -> Dict[str, Any]:
        """
        检测K线形态
        Args:
            kline_data: K线数据列表 (最近60个交易日)
        Returns:
            {"patterns": [...], "trend": "...", "support_resistance": {...}}
        """
        if not kline_data or len(kline_data) < 5:
            return {"patterns": [], "trend": "unknown"}

        df = pd.DataFrame(kline_data)
        close = df["close"].astype(float)
        open_ = df["open"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        volume = df["volume"].astype(float)

        patterns_found = []

        # 1. 看涨吞没
        if len(df) >= 2:
            last = len(df) - 1
            if (close.iloc[last] > open_.iloc[last] and       # 今日阳线
                close.iloc[last-1] < open_.iloc[last-1] and    # 昨日阴线
                close.iloc[last] > open_.iloc[last-1] and      # 收盘>昨开
                open_.iloc[last] < close.iloc[last-1]):        # 开盘<昨收
                patterns_found.append({
                    "name": "bullish_engulfing",
                    "label": "看涨吞没",
                    "confidence": 0.7,
                    "position": last,
                })

        # 2. 锤子线
        if len(df) >= 1:
            last = len(df) - 1
            body = abs(close.iloc[last] - open_.iloc[last])
            lower_shadow = min(open_.iloc[last], close.iloc[last]) - low.iloc[last]
            upper_shadow = high.iloc[last] - max(open_.iloc[last], close.iloc[last])
            total_range = high.iloc[last] - low.iloc[last]

            if (total_range > 0 and
                lower_shadow > body * 2 and
                upper_shadow < body * 0.5):
                patterns_found.append({
                    "name": "hammer",
                    "label": "锤子线",
                    "confidence": 0.6,
                    "position": last,
                })

        # 3. 双底
        if len(df) >= 20:
            recent_lows = low.tail(20)
            min_idx1 = recent_lows.idxmin()
            min_val1 = recent_lows.min()

            # 找第一个底之外的最低点
            rest = recent_lows.drop(min_idx1)
            if len(rest) > 5:
                min_val2 = rest.min()
                gap_pct = abs(min_val1 - min_val2) / min_val1 * 100

                if gap_pct < 3:  # 两底相近
                    # 中间有反弹
                    middle = recent_lows.loc[min(min_idx1, rest.idxmin()):max(min_idx1, rest.idxmin())]
                    if middle.max() > min(min_val1, min_val2) * 1.03:
                        patterns_found.append({
                            "name": "double_bottom",
                            "label": "双底",
                            "confidence": 0.65,
                        })

        # 4. 均线突破 (价格站上MA20)
        ma20 = close.rolling(20).mean()
        if len(df) >= 20:
            last = len(df) - 1
            if (close.iloc[last] > ma20.iloc[last] and
                close.iloc[last-1] <= ma20.iloc[last-1]):
                patterns_found.append({
                    "name": "ma_breakout",
                    "label": "均线突破",
                    "confidence": 0.55,
                })

        # 5. 放量突破 (成交量>5日均量2倍 + 阳线)
        if len(df) >= 5:
            last = len(df) - 1
            vol_ma5 = volume.tail(6).head(5).mean()
            if (volume.iloc[last] > vol_ma5 * 2 and
                close.iloc[last] > open_.iloc[last]):
                patterns_found.append({
                    "name": "volume_breakout",
                    "label": "放量突破",
                    "confidence": 0.6,
                })

        # 趋势判断
        trend = self._detect_trend(close)

        # 支撑阻力
        sr_levels = self._find_support_resistance(high, low, close)

        return {
            "patterns": patterns_found,
            "trend": trend,
            "support_resistance": sr_levels,
            "pattern_count": len(patterns_found),
        }

    def _detect_trend(self, close: pd.Series) -> str:
        """判断短期趋势"""
        if len(close) < 10:
            return "unknown"

        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()

        last = len(close) - 1

        # 趋势方向
        if ma5.iloc[last] > ma20.iloc[last] and close.iloc[last] > ma5.iloc[last]:
            return "uptrend"
        elif ma5.iloc[last] < ma20.iloc[last] and close.iloc[last] < ma5.iloc[last]:
            return "downtrend"
        else:
            # 通过连续高低点判断
            higher_highs = close.iloc[-10:].is_monotonic_increasing
            lower_lows = close.iloc[-10:].is_monotonic_decreasing
            if higher_highs:
                return "uptrend"
            elif lower_lows:
                return "downtrend"
            else:
                return "sideways"

    def _find_support_resistance(self, high: pd.Series, low: pd.Series,
                                  close: pd.Series) -> Dict:
        """找最近支撑和阻力位"""
        last = len(close) - 1
        recent = min(20, len(close))

        support = low.tail(recent).min()
        resistance = high.tail(recent).max()
        current = close.iloc[last]

        return {
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "current": round(current, 2),
            "distance_to_support_pct": round((current / support - 1) * 100, 2),
            "distance_to_resistance_pct": round((resistance / current - 1) * 100, 2),
        }

    def analyze_with_llm(self, kline_data: List[Dict],
                         stock_name: str = "") -> Dict[str, Any]:
        """
        使用LLM深度分析K线形态
        先在规则引擎中检测, 再用LLM进行综合判断
        """
        # 先用规则引擎
        rule_result = self.detect(kline_data)

        try:
            from config.llm_config import chat_json

            # 构造K线摘要 (最近10天)
            recent = kline_data[-10:] if len(kline_data) > 10 else kline_data
            kline_text = "\n".join([
                f"日期{d.get('date','')}: O{d.get('open',0):.2f} H{d.get('high',0):.2f} "
                f"L{d.get('low',0):.2f} C{d.get('close',0):.2f} V{d.get('volume',0)}"
                for d in recent
            ])

            prompt = f"""分析以下{stock_name}的K线数据, 识别技术形态:

{kline_text}

规则引擎已检测到: {[p['label'] for p in rule_result['patterns']]}
趋势: {rule_result['trend']}

请输出JSON:
{{
    "confirmed_patterns": ["<形态1>", ...],
    "trend_analysis": "<趋势分析, 50字>",
    "quality_score": <float, 0-1, 形态质量>,
    "trading_suggestion": "<操作建议, 30字>",
    "risk_note": "<风险提示, 30字>"
}}"""

            messages = [
                {"role": "system", "content": "你是技术分析专家, 精通K线形态识别。"},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, temperature=0.2, use_cache=True)
            result["rule_patterns"] = rule_result["patterns"]
            result["rule_trend"] = rule_result["trend"]
            return result

        except Exception as e:
            logger.warning(f"[PatternAnalyzer] LLM分析失败: {e}")
            return {"error": str(e), **rule_result}


# 全局实例
pattern_analyzer = PatternAnalyzer()
