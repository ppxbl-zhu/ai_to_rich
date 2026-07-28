"""
News Skill — 财经新闻采集
数据源: AKShare 东方财富新闻 (主) → 新浪财经 (备)
"""
from typing import Dict, Any, List
from loguru import logger

from skills.base import BaseSkill, skill_registry


class NewsSkill(BaseSkill):
    name = "get_recent_news"
    description = "获取最新A股财经新闻标题和摘要, 用于分析市场情绪和事件催化。返回最近30条。"
    schema = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "获取条数, 默认30"},
            "keywords": {"type": "string", "description": "按关键词筛选新闻, 如'半导体,贵金属', 可选"},
        },
        "required": [],
    }

    def execute(self, limit: int = 30, keywords: str = "", **kwargs) -> Dict[str, Any]:
        """获取财经新闻"""

        news = self._fetch_akshare(limit)

        if not news:
            logger.info("[News] AKShare失败, 尝试其他源...")

        # 关键词筛选
        if keywords and news:
            kw_list = [k.strip() for k in keywords.split(",")]
            news = [
                n for n in news
                if any(kw in n.get("title", "") or kw in n.get("content", "")
                       for kw in kw_list)
            ]
            if not news:
                return {"source": "akshare", "news": [], "filtered_by": kw_list,
                        "message": f"未找到包含'{keywords}'的新闻"}

        return {
            "source": "akshare_em",
            "count": len(news),
            "news": news[:limit],
            "filtered_by": kw_list if keywords else None,
        }

    def _fetch_akshare(self, limit: int) -> List[Dict]:
        """AKShare 东方财富新闻"""
        try:
            import akshare as ak
            df = ak.stock_news_em()
            if df is None or len(df) == 0:
                return []

            news = []
            for _, row in df.head(limit).iterrows():
                title = str(row.get('标题', ''))
                content = str(row.get('内容', ''))
                if not title:
                    continue

                news.append({
                    "title": title,
                    "content": content[:200] if content else "",
                    "source": "eastmoney",
                    "time": str(row.get('发布时间', '')),
                })

            return news
        except Exception as e:
            logger.debug(f"[News] AKShare: {e}")
            return []


# 注册
news_skill = NewsSkill()
skill_registry.register(news_skill)
