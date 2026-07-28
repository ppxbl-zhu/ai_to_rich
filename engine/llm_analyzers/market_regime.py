"""
Market Regime Classifier — 市场状态分类器
识别当前市场所处的状态: 趋势/震荡/高波动/低波动
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from loguru import logger


class MarketRegimeClassifier:
    """
    市场状态分类器
    使用量价特征判断市场处于哪种状态
    """

    REGIMES = {
        "trending_up": "上升趋势 — 适合趋势跟踪策略",
        "trending_down": "下降趋势 — 适合反转/防御策略",
        "range_bound": "区间震荡 — 适合高抛低吸",
        "high_volatility": "高波动 — 需严格控制仓位",
        "low_volatility": "低波动 — 可适度放大仓位",
        "bull_market": "牛市 — 积极参与",
        "bear_market": "熊市 — 防守为主",
    }

    def classify(self, market_data: Dict = None,
                 kline_data: List[Dict] = None) -> Dict[str, Any]:
        """
        分类市场状态
        Args:
            market_data: 大盘数据 (上证指数等)
            kline_data: 标的K线数据 (用于分析个股微环境)
        Returns:
            {"regime":..., "confidence":..., "characteristics":...}
        """
        features = self._extract_features(market_data, kline_data)
        regime = self._classify_from_features(features)

        return {
            "regime": regime,
            "regime_label": self.REGIMES.get(regime, "未知"),
            "confidence": features.get("confidence", 0.5),
            "features": features,
            "suggestion": self._get_suggestion(regime),
        }

    def _extract_features(self, market_data: Dict = None,
                          kline_data: List[Dict] = None) -> Dict[str, float]:
        """提取市场特征"""
        features = {
            "trend_strength": 0.0,
            "volatility": 0.0,
            "volume_trend": 0.0,
            "confidence": 0.3,
            "ma_spread": 0.0,
        }

        if kline_data and len(kline_data) >= 20:
            df = pd.DataFrame(kline_data)
            close = df["close"].astype(float)
            volume = df["volume"].astype(float)

            # 趋势强度: MA5/MA20斜率
            ma5 = close.rolling(5).mean()
            ma20 = close.rolling(20).mean()
            features["ma_spread"] = (ma5.iloc[-1] / ma20.iloc[-1] - 1) * 100

            # 收益率斜率 (线性回归)
            if len(close) >= 20:
                x = np.arange(20)
                y = close.iloc[-20:].values
                slope = np.polyfit(x, y, 1)[0]
                features["trend_strength"] = slope / close.iloc[-1] * 100  # 标准化

            # 波动率: 20日年化
            returns = close.pct_change().dropna()
            features["volatility"] = returns.tail(20).std() * np.sqrt(252)

            # 成交量趋势
            vol_ma5 = volume.rolling(5).mean()
            vol_ma20 = volume.rolling(20).mean()
            features["volume_trend"] = (vol_ma5.iloc[-1] / vol_ma20.iloc[-1] - 1) * 100

            features["confidence"] = min(0.9, len(kline_data) / 60 * 0.5 + 0.3)

        # 从大盘数据补充
        if market_data:
            for name, idx in market_data.items():
                if isinstance(idx, dict):
                    change = idx.get("change", 0)
                    if abs(change) > 3:
                        features["volatility"] = max(features.get("volatility", 0), 0.35)

        return features

    def _classify_from_features(self, features: Dict) -> str:
        """基于特征判断状态"""
        trend = features.get("trend_strength", 0)
        vol = features.get("volatility", 0)
        vol_trend = features.get("volume_trend", 0)
        ma_spread = features.get("ma_spread", 0)

        # 高波动
        if vol > 0.35:
            return "high_volatility"

        # 低波动
        if vol < 0.10:
            return "low_volatility"

        # 强上升趋势
        if trend > 0.5 and ma_spread > 1 and vol_trend > 0:
            return "trending_up"

        # 强下降趋势
        if trend < -0.5 and ma_spread < -1:
            return "trending_down"

        # 牛/熊市 (更长期的判断, 需要更多数据)
        if trend > 1.0 and ma_spread > 3:
            return "bull_market"
        if trend < -1.0 and ma_spread < -3:
            return "bear_market"

        # 默认: 震荡
        return "range_bound"

    def _get_suggestion(self, regime: str) -> Dict[str, Any]:
        """根据市场状态给出操作建议"""
        suggestions = {
            "trending_up": {
                "position_pct": 0.70,
                "preferred_strategies": ["trend", "auction"],
                "risk_level": "medium",
                "advice": "上升趋势确认, 可积极操作, 关注回调加仓机会",
            },
            "trending_down": {
                "position_pct": 0.20,
                "preferred_strategies": ["reversal"],
                "risk_level": "high",
                "advice": "下降趋势, 轻仓操作, 仅参与超跌反弹",
            },
            "range_bound": {
                "position_pct": 0.50,
                "preferred_strategies": ["auction", "event"],
                "risk_level": "medium",
                "advice": "区间震荡, 高抛低吸, 注意上下边界",
            },
            "high_volatility": {
                "position_pct": 0.25,
                "preferred_strategies": ["auction"],
                "risk_level": "extreme",
                "advice": "高波动环境, 严格控制仓位, 缩短持仓周期",
            },
            "low_volatility": {
                "position_pct": 0.60,
                "preferred_strategies": ["trend", "auction", "event"],
                "risk_level": "low",
                "advice": "低波动环境, 可适度放大仓位, 耐心持有",
            },
            "bull_market": {
                "position_pct": 0.85,
                "preferred_strategies": ["trend", "auction", "event", "reversal"],
                "risk_level": "low",
                "advice": "牛市环境, 积极参与, 注意板块轮动",
            },
            "bear_market": {
                "position_pct": 0.10,
                "preferred_strategies": [],
                "risk_level": "extreme",
                "advice": "熊市环境, 以空仓为主, 仅参与确定性高的超跌反弹",
            },
        }
        return suggestions.get(regime, suggestions["range_bound"])

    def classify_with_llm(self, market_data: Dict = None,
                          kline_features: Dict = None) -> Dict[str, Any]:
        """LLM辅助市场状态分类"""
        rule_result = self.classify(market_data)

        try:
            from config.llm_config import chat_json

            features_text = "\n".join([
                f"- {k}: {v}" for k, v in rule_result["features"].items()
            ])

            prompt = f"""基于以下市场特征, 判断当前A股市场状态:

定量特征:
{features_text}

规则引擎判断: {rule_result['regime']} ({rule_result['regime_label']})

请输出JSON:
{{
    "regime": "<trending_up | trending_down | range_bound | high_volatility | low_volatility | bull_market | bear_market>",
    "confidence": <float, 0-1>,
    "analysis": "<100字市场分析>",
    "key_indicators": ["<关键指标1>", ...],
    "position_advice": "<仓位建议>",
    "risk_events": ["<风险事件1>", ...]
}}"""

            messages = [
                {"role": "system", "content": "你是宏观策略分析师, 擅长判断市场状态和资产配置。"},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, temperature=0.2, use_cache=True)
            result["rule_regime"] = rule_result["regime"]
            result["features"] = rule_result["features"]
            result["suggestion"] = self._get_suggestion(
                result.get("regime", rule_result["regime"])
            )
            return result

        except Exception as e:
            logger.warning(f"[MarketRegime] LLM分析失败: {e}")
            return rule_result


# 全局实例
market_regime_classifier = MarketRegimeClassifier()
