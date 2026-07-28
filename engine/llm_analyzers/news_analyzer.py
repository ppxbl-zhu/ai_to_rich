"""
News Analyzer — LLM新闻情绪与影响分析
分析单条新闻或新闻集合对具体股票/板块的影响
"""
from typing import Dict, List, Any, Optional
from loguru import logger


class NewsAnalyzer:
    """
    新闻分析器
    分析新闻情绪(-1到1), 识别受益标的, 评估影响力
    """

    # 情绪关键词库 (快速规则判断)
    POSITIVE_WORDS = [
        "增长", "盈利", "突破", "利好", "签约", "中标", "回购", "增持",
        "业绩预增", "政策支持", "补贴", "涨价", "扩产", "获批",
        "涨停", "大涨", "新高", "超预期", "扭亏",
    ]
    NEGATIVE_WORDS = [
        "亏损", "下降", "减持", "利空", "处罚", "调查", "退市",
        "业绩预减", "违约", "爆雷", "停产", "限产",
        "跌停", "大跌", "新低", "不及预期", "监管",
    ]

    def analyze_batch(self, news_list: List[Dict]) -> Dict[str, Any]:
        """
        批量新闻分析
        Args:
            news_list: [{"title":..., "content":..., "source":...}, ...]
        Returns:
            {"sentiment":..., "key_events":..., "affected_sectors":..., "affected_stocks":...}
        """
        if not news_list:
            return {"sentiment": 0, "key_events": [], "affected_sectors": [], "affected_stocks": []}

        # Step 1: 快速规则判断
        sentiments = []
        key_events = []

        for news in news_list:
            title = news.get("title", "")
            content = news.get("content", "")

            # 情绪评分
            score = self._quick_sentiment(title + content)
            sentiments.append(score)

            # 识别重要事件 (高情绪绝对值)
            if abs(score) > 0.5:
                key_events.append({
                    "title": title,
                    "sentiment": score,
                    "source": news.get("source", ""),
                })

        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0

        # Step 2: 识别受影响的概念/板块
        affected_sectors = self._map_to_sectors(news_list)

        return {
            "sentiment": round(avg_sentiment, 4),
            "sentiment_distribution": {
                "positive": sum(1 for s in sentiments if s > 0.2),
                "neutral": sum(1 for s in sentiments if -0.2 <= s <= 0.2),
                "negative": sum(1 for s in sentiments if s < -0.2),
            },
            "key_events": key_events[:10],
            "affected_sectors": affected_sectors,
        }

    def _quick_sentiment(self, text: str) -> float:
        """快速情绪评分 (基于关键词计数)"""
        pos_count = sum(1 for w in self.POSITIVE_WORDS if w in text)
        neg_count = sum(1 for w in self.NEGATIVE_WORDS if w in text)

        total = pos_count + neg_count
        if total == 0:
            return 0.0

        return (pos_count - neg_count) / total

    def _map_to_sectors(self, news_list: List[Dict]) -> List[Dict]:
        """新闻 → 概念板块映射"""
        from strategies.event_strategy.runner import ConceptMapper
        mapper = ConceptMapper()
        concept_heat = mapper.map_news_to_concepts(news_list)

        return [
            {"sector": k, "heat": v}
            for k, v in list(concept_heat.items())[:10]
        ]

    def analyze_with_llm(self, news_list: List[Dict],
                         focus_stocks: List[str] = None) -> Dict[str, Any]:
        """
        LLM深度新闻分析
        """
        try:
            from config.llm_config import chat_json

            news_text = "\n\n".join([
                f"【{n.get('source','')}】{n.get('title','')}\n{n.get('content','')[:200]}"
                for n in news_list[:15]
            ])

            focus_text = ""
            if focus_stocks:
                focus_text = f"\n关注股票: {', '.join(focus_stocks)}"

            prompt = f"""分析以下财经新闻, 评估对A股市场的影响:

{news_text}
{focus_text}

请输出JSON:
{{
    "overall_sentiment": <float, -1到1>,
    "market_impact": "<low | medium | high>",
    "key_themes": ["<主题1>", ...],
    "sector_impacts": [
        {{"sector": "<板块>", "impact": "<positive | negative | neutral>", "magnitude": "<low | medium | high>"}}
    ],
    "stock_impacts": [
        {{"code": "<代码>", "name": "<名称>", "impact": "<positive | negative>", "reason": "<30字>"}}
    ],
    "summary": "<100字综合分析>"
}}"""

            messages = [
                {"role": "system", "content": "你是财经新闻分析师, 擅长从新闻中挖掘投资线索。"},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, temperature=0.3, use_cache=True)
            # 补充规则分析结果
            quick = self.analyze_batch(news_list)
            result["quick_sentiment"] = quick["sentiment"]
            return result

        except Exception as e:
            logger.warning(f"[NewsAnalyzer] LLM分析失败: {e}")
            return self.analyze_batch(news_list)


# 全局实例
news_analyzer = NewsAnalyzer()
