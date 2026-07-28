"""
LLM配置 — DeepSeek API调用管理
"""
import hashlib
import json
import time
from typing import Optional, Dict, Any
from openai import OpenAI
from loguru import logger

from config.settings import (
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
)

# === LLM 客户端 ===
_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """获取或初始化LLM客户端 (DeepSeek兼容OpenAI SDK)"""
    global _client
    if _client is None:
        if not LLM_API_KEY:
            raise ValueError("LLM_API_KEY 未配置! 请在 .env 中填入 DeepSeek API Key")
        _client = OpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
        )
        logger.info(f"LLM客户端初始化: provider={LLM_PROVIDER}, model={LLM_MODEL}")
    return _client


# === Prompt 模板 ===
PROMPT_TEMPLATES = {
    "market_research": """你是一位资深A股市场分析师。请基于以下新闻和市场数据，完成市场研判:

## 今日重要新闻
{news_summary}

## 昨日市场概况
{market_summary}

请输出JSON格式(不要输出其他内容):
{{
    "market_sentiment": <float, -1到1, -1极度悲观, 1极度乐观>,
    "top_sectors": ["<板块1>", "<板块2>", ...],  // TOP5热点板块
    "risk_alerts": ["<风险1>", "<风险2>", ...],
    "market_regime": "<trending_up | trending_down | range_bound | volatile>",
    "brief": "<100字以内市场研判>"
}}""",

    "stock_selection": """你是一位量化选股专家。请综合以下多策略信号，给出最终推荐:

## 市场背景
{market_context}

## 各策略候选信号
{strategy_signals}

## 用户偏好
- 风险偏好: {risk_preference}
- 持仓周期: {holding_period}

请输出JSON格式:
{{
    "picks": [
        {{
            "code": "000001",
            "name": "股票名",
            "strategy": "竞价/趋势/反转/事件",
            "confidence": <float, 0-1>,
            "horizon": "短线/中线/长线",
            "entry_price": <float>,
            "stop_loss": <float>,
            "take_profit": <float>,
            "rationale": "<推荐理由,50字>"
        }}
    ],
    "market_view": "<100字市场观点>"
}}""",

    "monitor_alert": """你是一位实时交易监控员。当前触发了一个告警，请判断是否需要操作:

## 告警详情
- 股票: {stock_code} {stock_name}
- 告警类型: {alert_type}
- 当前价格: {current_price}
- 持仓成本: {entry_price}
- 当前盈亏: {pnl_pct}%
- 触发条件: {trigger_condition}

## 实时盘口
{market_depth}

## 技术指标
{technical_indicators}

请输出JSON:
{{
    "action": "sell | buy | hold | reduce | add",
    "urgency": "immediate | soon | watch",
    "confidence": <float, 0-1>,
    "reason": "<操作理由, 50字>",
    "target_price": <float or null>,
    "is_noise": <bool, 是否为噪声信号>
}}""",

    "review": """你是一位交易复盘教练。请分析以下交易并提取经验:

## 当日交易记录
{trade_records}

## 策略表现
{strategy_performance}

## 市场走势
{market_movement}

请输出JSON:
{{
    "day_rating": "<A | B | C | D | F>",
    "key_lessons": ["<经验1>", "<经验2>", ...],
    "mistakes": ["<错误1>", ...],
    "improvement_hypotheses": [
        {{
            "target": "<参数名或规则>",
            "current_value": "<当前值>",
            "suggested_direction": "<increase | decrease | toggle>",
            "rationale": "<调整理由>"
        }}
    ],
    "tomorrow_focus": ["<明日关注1>", ...],
    "summary": "<200字以内复盘总结>"
}}""",

    "ga_analysis": """你是一位量化策略优化专家。分析以下GA种群进化情况:

## 当前代数: {generation}
## 适应度趋势
{fitness_trend}

## Top 5 基因组
{top_genomes}

## Bottom 5 基因组
{bottom_genomes}

请输出JSON:
{{
    "convergence_status": "converging | improving | stagnating",
    "key_insights": ["<洞察1>", ...],
    "mutation_suggestions": [
        {{
            "parameter": "<参数名>",
            "direction": "increase | decrease | explore",
            "strength": "<low | medium | high>",
            "reason": "<建议理由>"
        }}
    ],
    "overfitting_risk": "<low | medium | high>",
    "promotion_recommendation": "yes | no | conditional",
    "summary": "<150字分析总结>"
}}""",
}


def get_prompt(template_name: str, **kwargs) -> str:
    """获取并填充prompt模板"""
    template = PROMPT_TEMPLATES.get(template_name)
    if not template:
        raise ValueError(f"未知prompt模板: {template_name}")
    return template.format(**kwargs)


# === LLM 缓存 ===
class LLMCache:
    """LLM查询缓存 — 相同输入直接返回缓存, 降低API成本"""

    def __init__(self, cache_db_path: str = None):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._db_path = cache_db_path

    def _hash(self, messages: list, model: str) -> str:
        content = json.dumps(messages, sort_keys=True, ensure_ascii=False) + model
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, messages: list, model: str) -> Optional[str]:
        key = self._hash(messages, model)
        if key in self._cache:
            logger.debug(f"LLM缓存命中: {key[:16]}...")
            return self._cache[key]["response"]
        return None

    def set(self, messages: list, model: str, response: str, tokens: int = 0):
        key = self._hash(messages, model)
        self._cache[key] = {
            "response": response,
            "tokens": tokens,
            "timestamp": time.time(),
        }
        # 限制内存缓存大小
        if len(self._cache) > 1000:
            oldest = min(self._cache, key=lambda k: self._cache[k]["timestamp"])
            del self._cache[oldest]


# 全局缓存实例
llm_cache = LLMCache()


# === 便捷调用 ===
def chat(
    messages: list,
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    use_cache: bool = True,
) -> str:
    """
    发送消息到LLM, 返回文本响应
    自动处理缓存、重试、错误
    """
    model = model or LLM_MODEL
    temperature = temperature if temperature is not None else LLM_TEMPERATURE
    max_tokens = max_tokens or LLM_MAX_TOKENS

    # 检查缓存
    if use_cache:
        cached = llm_cache.get(messages, model)
        if cached:
            return cached

    client = get_client()
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content
            tokens = resp.usage.total_tokens if resp.usage else 0

            if use_cache:
                llm_cache.set(messages, model, text, tokens)

            return text
        except Exception as e:
            logger.warning(f"LLM调用失败 (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise


def chat_json(
    messages: list,
    model: str = None,
    temperature: float = 0.1,
    use_cache: bool = False,
) -> dict:
    """
    发送消息到LLM, 返回解析后的JSON对象
    自动追加JSON格式要求, 清理markdown标记
    """
    # 追加JSON格式要求
    if not any("JSON" in str(m.get("content", "")) for m in messages):
        messages = messages + [{
            "role": "system",
            "content": "请仅输出JSON, 不要包含任何markdown标记或解释。"
        }]

    text = chat(messages, model=model, temperature=temperature, use_cache=use_cache)

    # 清理可能的markdown标记
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    return json.loads(text)
