"""
Skills — 可复用的数据能力模块
每个Skill独立调用、自带错误处理、可被LLM Agent动态发现

已注册Skills (16个):
  数据采集: market_index, concept_ranking, industry_ranking, news, kline, kline_brief
  技术分析: compute_indicators, detect_patterns, classify_regime, assess_risk
  交易执行: sim_buy, sim_sell, portfolio, scan_strategy
"""
from skills.base import BaseSkill, SkillRegistry, skill_registry

# 数据采集 Skills
from skills.market_index import market_index_skill
from skills.concept_ranking import concept_ranking_skill
from skills.industry_ranking import industry_ranking_skill
from skills.news import news_skill
from skills.kline import kline_skill, kline_brief_skill

# 技术分析 Skills
from skills.analysis import (  # noqa: F401 - 触发注册
    ComputeIndicatorsSkill, DetectPatternsSkill,
    ClassifyRegimeSkill, AssessRiskSkill,
)

# 交易执行 Skills
from skills.trading import (  # noqa: F401 - 触发注册
    SimBuySkill, SimSellSkill, PortfolioSkill, ScanStrategySkill,
)

# 盘中实时 Skills (东方财富 → 新浪 fallback)
from skills.intraday import (  # noqa: F401 - 触发注册
    IntradayConceptSkill, IntradayIndustrySkill, IntradayScanSkill,
)


def get_all_skills():
    """获取所有已注册Skill"""
    return skill_registry.list_all()


def get_tool_definitions():
    """获取所有Skill的LLM工具定义 (用于function calling)"""
    return skill_registry.get_tool_defs()


def execute_skill(name: str, **kwargs):
    """执行指定Skill"""
    return skill_registry.execute(name, **kwargs)
