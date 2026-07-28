"""
Research Agent — 盘前市场调研 (Skill-based v2)
通过 Skill Registry 动态调用数据能力, LLM 自主分析
"""
from datetime import date
from typing import Dict, Any, List
from loguru import logger

from core.agent_runner import BaseAgent, AgentRunResult
from core.context_manager import TradingContext, MarketBrief


class ResearchAgent(BaseAgent):
    """
    市场调研 Agent (Skill-based)
    每日盘前运行:
    1. 通过 SkillRegistry 调用各个数据 Skill
    2. LLM 综合分析所有数据
    3. 输出 MarketBrief + 推送晨报
    """

    agent_name = "research_agent"
    agent_description = "盘前市场调研: Skill数据采集 → LLM综合分析 → 推送晨报"

    # 默认使用的 Skills (按顺序执行)
    DEFAULT_SKILLS = [
        "get_market_index",
        "get_concept_ranking",
        "get_industry_ranking",
        "get_recent_news",
    ]

    def run(self, context: TradingContext = None, **kwargs) -> AgentRunResult:
        logger.info("[Research Agent] 开始市场调研...")
        t0 = __import__("time").time()

        try:
            # Phase 1: 调用 Skills 收集数据
            data = self._gather_data()

            # Phase 2: LLM 综合分析 (或 fallback)
            brief = self._analyze(data)

            # Phase 3: 写入上下文
            if context:
                context.market_brief = brief
                context.research_output = data

            # Phase 4: 推送
            self._send_brief(brief, data)

            duration_ms = (__import__("time").time() - t0) * 1000
            logger.info(f"[Research Agent] 完成 ({duration_ms:.0f}ms): "
                       f"情绪={brief.sentiment:.2f}, 热点={brief.top_sectors[:5]}")

            return AgentRunResult(
                agent_name=self.agent_name, status="completed",
                output={
                    "sentiment": brief.sentiment,
                    "top_sectors": brief.top_sectors,
                    "regime": brief.regime,
                    "skills_called": data.get("skills_called", []),
                },
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.error(f"[Research Agent] 失败: {e}")
            return AgentRunResult(self.agent_name, "failed", error=str(e))

    # ============================================================
    # Phase 1: Skill 数据采集
    # ============================================================

    def _gather_data(self) -> Dict[str, Any]:
        """通过 SkillRegistry 调用每个 Skill, 收集结果"""
        from skills import skill_registry

        data = {"skills_called": [], "skills_failed": []}

        for skill_name in self.DEFAULT_SKILLS:
            skill = skill_registry.get(skill_name)
            if not skill:
                data["skills_failed"].append(f"{skill_name}: 未注册")
                continue

            try:
                result = skill()
                if result.get("error"):
                    logger.warning(f"  [Skill] {skill_name}: {result['error']}")
                    data["skills_failed"].append(f"{skill_name}: {result['error']}")
                else:
                    data["skills_called"].append(skill_name)
                    logger.info(f"  [Skill] {skill_name}: OK")

                # 存储结果
                data_key = skill_name.replace("get_", "")
                data[data_key] = result

            except Exception as e:
                logger.warning(f"  [Skill] {skill_name} 异常: {e}")
                data["skills_failed"].append(f"{skill_name}: {str(e)}")

        return data

    # ============================================================
    # Phase 2: 分析
    # ============================================================

    def _analyze(self, data: Dict) -> MarketBrief:
        """LLM优先, fallback兜底"""
        brief = self._llm_analyze(data)
        if brief is not None:
            return brief
        return self._fallback_analyze(data)

    def _llm_analyze(self, data: Dict) -> MarketBrief:
        """LLM综合分析所有Skill数据"""
        try:
            from config.llm_config import chat_json
            from config.settings import LLM_API_KEY
            if not LLM_API_KEY:
                return None

            prompt = self._build_prompt(data)

            messages = [
                {"role": "system", "content": (
                    "你是资深A股分析师。请严格基于提供的实时数据进行分析, "
                    "不要编造不存在的数据。如果某项数据缺失, 在分析中注明。"
                )},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, temperature=0.3, use_cache=False)

            return MarketBrief(
                sentiment=float(result.get("market_sentiment", 0)),
                top_sectors=result.get("top_sectors", []),
                risk_alerts=result.get("risk_alerts", []),
                regime=result.get("market_regime", "range_bound"),
                brief=result.get("brief", ""),
            )
        except Exception as e:
            logger.warning(f"[Research] LLM失败: {e}")
            return None

    def _build_prompt(self, data: Dict) -> str:
        """构建分析prompt — 汇聚所有Skill的输出"""

        # 大盘
        market = data.get("market_index", {}).get("data", {})
        if market:
            lines = [f"- {n}: {d.get('current',0):.2f} ({d.get('change_pct',0):+.2f}%)"
                     for n, d in market.items() if isinstance(d, dict)]
            market_text = "\n".join(lines) if lines else "暂无数据"
        else:
            market_text = "暂无数据"

        # 概念排名
        concepts = data.get("concept_ranking", {}).get("concepts", [])
        concept_date = data.get("concept_ranking", {}).get("date", "?")
        if concepts:
            lines = [f"数据日期: {concept_date}"]
            lines += [f"{i+1}. {c['name']}: {c['change_pct']:+.2f}%"
                      for i, c in enumerate(concepts[:15])]
            concept_text = "\n".join(lines)
        else:
            concept_text = "暂无数据"

        # 行业
        industries = data.get("industry_ranking", {}).get("industries", [])
        if industries:
            industry_text = "\n".join(
                f"- {ind['name']}: {ind['change_pct']:+.2f}%"
                for ind in industries[:10]
            )
        else:
            industry_text = "暂无数据"

        # 新闻
        news_list = data.get("recent_news", {}).get("news", [])
        if news_list:
            news_text = "\n".join(
                f"- [{n.get('source','')}] {n.get('title','')}"
                for n in news_list[:15] if n.get('title')
            )
        else:
            news_text = "暂无新闻"

        # 统计信息
        concept_stats = data.get("concept_ranking", {})
        stats_text = ""
        if concept_stats.get("total"):
            stats_text = (
                f"板块总数: {concept_stats['total']}, "
                f"上涨: {concept_stats.get('up_count',0)}, "
                f"下跌: {concept_stats.get('down_count',0)}, "
                f"平均涨幅: {concept_stats.get('avg_change',0):+.2f}%"
            )

        return f"""请基于以下实时数据完成今日A股市场研判:

## 大盘指数 (实时)
{market_text}

## 概念板块涨幅排名
{stats_text}
{concept_text}

## 行业板块涨幅排名
{industry_text}

## 财经新闻
{news_text}

请输出严格JSON(不要markdown):
{{
    "market_sentiment": <float, -1到1>,
    "top_sectors": ["<板块1>", "<板块2>", ...],
    "risk_alerts": ["<风险1>", ...],
    "market_regime": "<trending_up | trending_down | range_bound | volatile>",
    "brief": "<150字今日操作建议>"
}}

重要: top_sectors必须基于上面概念板块排名的真实数据, 不要编造板块名称。"""

    def _fallback_analyze(self, data: Dict) -> MarketBrief:
        """无LLM时的fallback分析 (纯数据驱动)"""
        concepts = data.get("concept_ranking", {}).get("concepts", [])
        market = data.get("market_index", {}).get("data", {})

        # 热点: 直接取排名前8
        top_sectors = [c['name'] for c in concepts[:8]]

        # 情绪: 从大盘涨跌 + 板块涨跌比计算
        sentiment = 0.0
        for idx in (market or {}).values():
            if isinstance(idx, dict):
                sentiment += idx.get("change_pct", 0) / 3 * 0.3
        sentiment = max(-1, min(1, sentiment))

        # 状态
        regime = "range_bound"
        if sentiment > 0.4: regime = "trending_up"
        elif sentiment < -0.4: regime = "trending_down"

        concept_summary = "、".join(top_sectors[:5]) if top_sectors else "无数据"
        return MarketBrief(
            sentiment=round(sentiment, 2), top_sectors=top_sectors,
            risk_alerts=[], regime=regime,
            brief=f"热点: {concept_summary}\n情绪: {sentiment:.2f}",
        )

    # ============================================================
    # Phase 3: 推送
    # ============================================================

    def _send_brief(self, brief: MarketBrief, data: Dict):
        """晨报仅日志, 不推微信(省Server酱额度)"""
        logger.info(f"[Research] 晨报: 情绪={brief.sentiment:.2f} 热点={brief.top_sectors[:5]}")
