"""
LLM Sentiment Factor — 基于LLM的市场情绪因子
分析新闻/社交媒体情绪, 量化市场风险偏好
"""
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
from loguru import logger


class SentimentFactor:
    """
    LLM情绪因子
    通过分析新闻标题和内容, 量化市场情绪
    输出: sentiment_score (-1到1, -1极度悲观, 1极度乐观)
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.use_llm = self.config.get("use_llm", True)
        self.cache_ttl = self.config.get("cache_ttl", 3600)  # 1小时

    def compute(self, news_list: List[Dict] = None,
                market_data: Dict = None) -> Dict[str, Any]:
        """
        计算市场情绪
        Args:
            news_list: 新闻列表 [{"title":..., "content":..., "source":...}, ...]
            market_data: 市场数据 {"index_change":..., "volume":..., "up_down_ratio":...}
        Returns:
            {"sentiment": float, "confidence": float, "key_themes": [...], "risk_level": str}
        """
        if self.use_llm and news_list:
            return self._compute_with_llm(news_list, market_data)
        else:
            return self._compute_heuristic(news_list, market_data)

    def _compute_with_llm(self, news_list: List[Dict],
                          market_data: Dict = None) -> Dict[str, Any]:
        """使用LLM分析情绪"""
        try:
            from config.llm_config import chat_json

            news_text = "\n".join([
                f"- [{n.get('source', '')}] {n.get('title', '')}"
                for n in news_list[:20]
            ])

            market_text = ""
            if market_data:
                market_text = f"""
市场数据:
- 指数涨跌: {market_data.get('index_change', 0)}%
- 涨跌比: {market_data.get('up_down_ratio', '未知')}
- 成交量变化: {market_data.get('volume_change', '未知')}%
"""

            prompt = f"""分析以下A股市场新闻和市场数据, 输出市场情绪评估:

{news_text}
{market_text}

请输出JSON:
{{
    "sentiment": <float, -1到1, -1极度悲观, 1极度乐观>,
    "confidence": <float, 0-1, 评估置信度>,
    "key_themes": ["<主题1>", "<主题2>", ...],
    "risk_level": "<low | medium | high | extreme>",
    "brief": "<50字情绪总结>"
}}"""

            messages = [
                {"role": "system", "content": "你是A股市场情绪分析师。请基于新闻客观评估市场情绪。"},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, temperature=0.2, use_cache=True)
            return result

        except Exception as e:
            logger.warning(f"[情绪因子] LLM分析失败: {e}, 使用启发式")
            return self._compute_heuristic(news_list, market_data)

    def _compute_heuristic(self, news_list: List[Dict] = None,
                           market_data: Dict = None) -> Dict[str, Any]:
        """启发式情绪计算 (不依赖LLM)"""
        sentiment = 0.0

        if market_data:
            # 指数涨跌映射
            change = market_data.get("index_change", 0)
            sentiment += np.clip(change / 3, -1, 1) * 0.5  # 3%涨跌→±0.5

            # 涨跌比映射
            up_down = market_data.get("up_down_ratio", 1.0)
            sentiment += np.clip((up_down - 1) * 0.5, -0.3, 0.3)

        if news_list:
            # 简单关键词匹配
            bullish_words = ["利好", "大涨", "突破", "增长", "盈利", "回购", "增持", "政策支持"]
            bearish_words = ["利空", "大跌", "亏损", "减持", "监管", "风险", "崩盘", "制裁"]

            bull_count = 0
            bear_count = 0
            for news in news_list[:30]:
                text = news.get("title", "") + news.get("content", "")
                bull_count += sum(1 for w in bullish_words if w in text)
                bear_count += sum(1 for w in bearish_words if w in text)

            if bull_count + bear_count > 0:
                sentiment += (bull_count - bear_count) / (bull_count + bear_count) * 0.3

        sentiment = float(np.clip(sentiment, -1, 1))

        risk_level = "low"
        if abs(sentiment) > 0.6:
            risk_level = "high"
        elif abs(sentiment) > 0.3:
            risk_level = "medium"

        return {
            "sentiment": round(sentiment, 4),
            "confidence": 0.5,
            "key_themes": [],
            "risk_level": risk_level,
            "brief": f"启发式情绪: {sentiment:.2f}",
        }


class MacroFactor:
    """
    宏观经济因子
    基于公开宏观数据 (利率/PMI/CPI/汇率等) 评分
    """

    def __init__(self):
        self.indicators = {}

    def fetch_macro_data(self) -> Dict[str, float]:
        """获取宏观经济指标"""
        try:
            import akshare as ak

            # 尝试获取最近的宏观经济数据
            indicators = {}

            # Shibor (银行间拆借利率)
            try:
                shibor = ak.rate_interbank(market="上海银行间同业拆放利率")
                if shibor is not None and len(shibor) > 0:
                    indicators["shibor_on"] = float(shibor.iloc[-1].get("ON", 1.5))
            except Exception:
                indicators["shibor_on"] = 1.5

            # 默认值
            indicators.setdefault("cpi", 0.5)
            indicators.setdefault("pmi", 50.0)
            indicators.setdefault("usdcny", 7.2)

            self.indicators = indicators
            return indicators

        except Exception as e:
            logger.warning(f"[宏观因子] 数据获取失败: {e}")
            return self.indicators

    def compute_score(self) -> Dict[str, Any]:
        """
        计算宏观环境评分 (0-1, 越高越有利)
        """
        if not self.indicators:
            self.fetch_macro_data()

        score = 0.5  # 基准中性

        # Shibor: 越低越宽松 (1.0-2.5 → 0~+0.2)
        shibor = self.indicators.get("shibor_on", 1.5)
        score += max(0, (2.5 - shibor) / 5) * 0.15

        # PMI: >50 扩张 (48-52 → -0.1~+0.1)
        pmi = self.indicators.get("pmi", 50.0)
        score += (pmi - 50) / 20 * 0.10

        # CPI: 1-3%最理想
        cpi = self.indicators.get("cpi", 0.5)
        if 1 <= cpi <= 3:
            score += 0.05
        elif cpi < 0:  # 通缩
            score -= 0.10

        # 汇率: 7以下为强
        usdcny = self.indicators.get("usdcny", 7.2)
        if usdcny < 6.8:
            score += 0.05
        elif usdcny > 7.3:
            score -= 0.05

        score = round(max(0, min(1, score)), 4)

        regime = "neutral"
        if score > 0.7:
            regime = "favorable"
        elif score < 0.3:
            regime = "unfavorable"

        return {
            "macro_score": score,
            "regime": regime,
            "indicators": self.indicators,
        }


# 全局实例
sentiment_factor = SentimentFactor()
macro_factor = MacroFactor()
