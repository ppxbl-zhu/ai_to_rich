"""
Event Strategy — 事件驱动策略 (增强版)
基于新闻事件 + LLM分析 + 概念映射的选股策略
"""
import sys
from pathlib import Path
from typing import List, Optional, Any, Dict
from loguru import logger

from strategies.base_strategy import BaseStrategy, StrategySignal

EXISTING_SYSTEM = Path("/mnt/d/AI/auction-stock-picker")
if str(EXISTING_SYSTEM) not in sys.path:
    sys.path.append(str(EXISTING_SYSTEM))


class NewsGatherer:
    """新闻采集器 — 聚合多源财经新闻"""

    def __init__(self):
        self.sources = [
            "eastmoney",    # 东方财富
            "cninfo",       # 巨潮资讯
        ]

    def fetch_today_news(self, limit: int = 50) -> List[Dict]:
        """
        抓取今日重要新闻
        返回: [{"title":..., "content":..., "source":..., "url":..., "tags":[...]}, ...]
        """
        news = []

        # 尝试从东方财富获取
        try:
            import requests
            # 东方财富新闻API (免费)
            url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
            resp = requests.get(url, params={"page_size": limit}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # 解析新闻列表 (简化处理)
                logger.info(f"[新闻采集] 东方财富: 获取成功")
        except Exception as e:
            logger.debug(f"[新闻采集] 东方财富: {e}")

        # 尝试从AKShare获取
        try:
            import akshare as ak
            news_df = ak.stock_news_em()  # 东方财富新闻
            if news_df is not None and len(news_df) > 0:
                for _, row in news_df.head(limit).iterrows():
                    news.append({
                        "title": str(row.get("标题", "")),
                        "content": str(row.get("内容", "")),
                        "source": "eastmoney",
                        "url": str(row.get("新闻链接", "")),
                        "tags": [],
                    })
                logger.info(f"[新闻采集] AKShare: {len(news)} 条新闻")
        except Exception as e:
            logger.debug(f"[新闻采集] AKShare: {e}")

        return news


class ConceptMapper:
    """概念映射器 — 将新闻关键词映射到A股概念板块"""

    # 关键词 → 概念板块映射表
    KEYWORD_CONCEPT_MAP = {
        "人工智能": ["人工智能", "AI", "ChatGPT", "大模型", "算力"],
        "新能源汽车": ["新能源汽车", "锂电池", "宁德时代", "比亚迪"],
        "半导体": ["半导体", "芯片", "光刻机", "集成电路"],
        "光伏": ["光伏", "太阳能", "硅料", "逆变器"],
        "军工": ["军工", "国防", "航天", "武器装备"],
        "医药": ["医药", "创新药", "医疗器械", "生物制药"],
        "消费": ["消费", "白酒", "食品", "家电"],
        "机器人": ["机器人", "人形机器人", "工业机器人"],
        "数据要素": ["数据要素", "数据确权", "数据交易所"],
        "低空经济": ["低空经济", "无人机", "飞行汽车", "eVTOL"],
    }

    def map_news_to_concepts(self, news_list: List[Dict]) -> Dict[str, int]:
        """
        将新闻列表映射到概念板块热度
        返回: {concept_name: heat_score}
        """
        concept_heat: Dict[str, int] = {}

        for news in news_list:
            title = news.get("title", "")
            content = news.get("content", "")

            for concept, keywords in self.KEYWORD_CONCEPT_MAP.items():
                for kw in keywords:
                    if kw in title or kw in content:
                        concept_heat[concept] = concept_heat.get(concept, 0) + 1
                        break

        # 按热度排序
        return dict(sorted(concept_heat.items(), key=lambda x: x[1], reverse=True))


class EventStrategy(BaseStrategy):
    """
    事件驱动策略 (LLM增强)
    1. 采集新闻 → 概念映射
    2. LLM分析事件影响
    3. 从热点概念中筛选受益个股
    """

    strategy_name = "event"
    strategy_description = "事件驱动策略 — 新闻采集 + LLM分析 + 概念映射选股"

    def __init__(self, config: dict = None):
        super().__init__(config or {})
        self.default_config = {
            "top_concepts": 5,
            "top_stocks_per_concept": 3,
            "use_llm_analysis": True,
        }
        for k, v in self.default_config.items():
            self.config.setdefault(k, v)
        self.news_gatherer = NewsGatherer()
        self.concept_mapper = ConceptMapper()

    def generate_signals(self, context: Any = None) -> List[StrategySignal]:
        logger.info("[事件策略] 开始分析...")
        signals = []

        try:
            # Step 1: 采集新闻
            news = self.news_gatherer.fetch_today_news()
            if not news:
                logger.warning("[事件策略] 无新闻数据")
                return signals

            # Step 2: 概念映射
            concept_heat = self.concept_mapper.map_news_to_concepts(news)
            if not concept_heat:
                logger.info("[事件策略] 未识别到热点概念")
                return signals

            top_concepts = list(concept_heat.keys())[:self.config["top_concepts"]]
            logger.info(f"[事件策略] TOP概念: {top_concepts}")

            # Step 3: LLM分析 (如果启用)
            llm_analysis = {}
            if self.config["use_llm_analysis"]:
                llm_analysis = self._llm_analyze(news, top_concepts, context)

            # Step 4: 从热点概念获取成分股 → 生成信号
            signals = self._generate_from_concepts(top_concepts, llm_analysis)

            logger.info(f"[事件策略] 生成 {len(signals)} 个信号")

        except Exception as e:
            logger.error(f"[事件策略] 执行失败: {e}")

        self.signals_today = signals
        return signals

    def _llm_analyze(self, news: List[Dict], concepts: List[str],
                     context: Any = None) -> Dict[str, Any]:
        """LLM分析事件影响"""
        try:
            from config.llm_config import get_prompt, chat_json

            # 构造新闻摘要
            news_titles = "\n".join([f"- {n.get('title', '')}" for n in news[:10]])
            concepts_str = ", ".join(concepts)

            prompt = get_prompt("market_research",
                news_summary=news_titles,
                market_summary=f"当前热点概念: {concepts_str}",
            )

            messages = [
                {"role": "system", "content": "你是A股事件驱动分析师"},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, use_cache=True)
            return result
        except Exception as e:
            logger.warning(f"[事件策略] LLM分析失败, 使用规则引擎: {e}")
            return {}

    def _generate_from_concepts(self, concepts: List[str],
                                 llm_analysis: Dict) -> List[StrategySignal]:
        """从概念板块获取成分股"""
        signals = []

        try:
            # 尝试从现有概念缓存获取成分股
            import json
            concept_members_path = Path(
                "/mnt/d/AI/auction-stock-picker/data/ak_concept_members.json"
            )
            if concept_members_path.exists():
                with open(concept_members_path) as f:
                    concept_members = json.load(f)

                for concept in concepts[:self.config["top_concepts"]]:
                    members = concept_members.get(concept, [])
                    if not members:
                        # 尝试模糊匹配
                        for k in concept_members:
                            if concept in k or k in concept:
                                members = concept_members[k]
                                break

                    # 取前N只成分股
                    for stock in members[:self.config["top_stocks_per_concept"]]:
                        code = str(stock.get("code", "")).zfill(6)
                        name = stock.get("name", "")

                        signal = StrategySignal(
                            code=code,
                            name=name,
                            direction="buy",
                            confidence=0.55,  # 事件策略置信度偏保守
                            price=0,          # 需要进一步获取实时价格
                            stop_loss=0,
                            take_profit=0,
                            horizon="短线",
                            reason=f"事件驱动: {concept}热点, {name}为成分股",
                            strategy_name=self.strategy_name,
                            factors={
                                "concept": concept,
                                "concept_rank": concepts.index(concept) + 1,
                            },
                        )
                        signals.append(signal)

        except Exception as e:
            logger.warning(f"[事件策略] 概念成分股获取失败: {e}")

        return signals

    def get_parameters(self) -> dict:
        return {k: self.config.get(k, v) for k, v in self.default_config.items()}

    def set_parameters(self, params: dict):
        self.config.update(params)
