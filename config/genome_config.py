"""
GA基因组搜索空间定义
定义哪些参数可以被GA优化, 以及每个参数的取值范围和约束
"""
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ParamType(Enum):
    CONTINUOUS = "continuous"     # 连续值 (float range)
    DISCRETE = "discrete"         # 离散值 (int range / choice)
    BOOLEAN = "boolean"           # 布尔开关
    CATEGORICAL = "categorical"   # 类别选择


@dataclass
class GenomeParam:
    """单个可优化参数的定义"""
    name: str
    type: ParamType
    default: Any
    # 连续/离散参数
    min_value: float = None
    max_value: float = None
    step: float = None
    # 类别参数
    choices: List[Any] = None
    # 元信息
    description: str = ""
    category: str = ""            # 参数分组: "weights" | "thresholds" | "stops" | "technical" | "flags" | "capital"


# === 基因组搜索空间定义 ===
GENOME_SCHEMA: List[GenomeParam] = [
    # ---- 因子权重 (连续, 0-1, 归一化后使用) ----
    GenomeParam("auction_weight", ParamType.CONTINUOUS, 0.50, 0.0, 1.0, 0.01,
                description="竞价因子权重", category="weights"),
    GenomeParam("sector_weight", ParamType.CONTINUOUS, 0.0, 0.0, 0.3, 0.01,
                description="板块因子权重", category="weights"),
    GenomeParam("technical_weight", ParamType.CONTINUOUS, 0.30, 0.0, 0.5, 0.01,
                description="技术因子权重", category="weights"),
    GenomeParam("fundamental_weight", ParamType.CONTINUOUS, 0.05, 0.0, 0.3, 0.01,
                description="基本面因子权重", category="weights"),
    GenomeParam("capital_weight", ParamType.CONTINUOUS, 0.15, 0.0, 0.3, 0.01,
                description="资金因子权重", category="weights"),

    # ---- 筛选阈值 ----
    GenomeParam("min_market_cap", ParamType.CONTINUOUS, 20, 5, 100, 1,
                description="最小流通市值(亿)", category="thresholds"),
    GenomeParam("max_market_cap", ParamType.CONTINUOUS, 500, 100, 2000, 10,
                description="最大流通市值(亿)", category="thresholds"),
    GenomeParam("min_auction_change", ParamType.CONTINUOUS, 1.0, 0.5, 3.0, 0.1,
                description="最小竞价涨幅(%)", category="thresholds"),
    GenomeParam("max_auction_change", ParamType.CONTINUOUS, 6.0, 3.0, 9.0, 0.1,
                description="最大竞价涨幅(%)", category="thresholds"),
    GenomeParam("min_volume_ratio", ParamType.CONTINUOUS, 1.5, 0.5, 5.0, 0.1,
                description="最小量比", category="thresholds"),
    GenomeParam("min_auction_amount", ParamType.CONTINUOUS, 100, 30, 500, 10,
                description="最小竞价金额(万元)", category="thresholds"),
    GenomeParam("hot_sector_top_n", ParamType.DISCRETE, 20, 5, 50, 1,
                description="热点板块取前N", category="thresholds"),

    # ---- 止损止盈 ----
    GenomeParam("stop_loss_pct", ParamType.CONTINUOUS, -0.03, -0.08, -0.01, 0.001,
                description="止损线(%)", category="stops"),
    GenomeParam("take_profit_min", ParamType.CONTINUOUS, 0.05, 0.02, 0.15, 0.01,
                description="最小止盈(%)", category="stops"),
    GenomeParam("take_profit_max", ParamType.CONTINUOUS, 0.08, 0.03, 0.20, 0.01,
                description="最大止盈(%)", category="stops"),
    GenomeParam("trailing_stop_pct", ParamType.CONTINUOUS, 0.05, 0.02, 0.10, 0.01,
                description="移动止损回落(%)", category="stops"),

    # ---- 技术指标参数 ----
    GenomeParam("ma_short", ParamType.DISCRETE, 5, 3, 15, 1,
                description="短期均线周期", category="technical"),
    GenomeParam("ma_mid", ParamType.DISCRETE, 20, 10, 40, 1,
                description="中期均线周期", category="technical"),
    GenomeParam("ma_long", ParamType.DISCRETE, 60, 30, 120, 5,
                description="长期均线周期", category="technical"),
    GenomeParam("rsi_oversold", ParamType.DISCRETE, 30, 20, 40, 1,
                description="RSI超卖阈值", category="technical"),
    GenomeParam("rsi_overbought", ParamType.DISCRETE, 70, 60, 85, 1,
                description="RSI超买阈值", category="technical"),

    # ---- 策略开关 ----
    GenomeParam("use_hot_sector_filter", ParamType.BOOLEAN, True,
                description="热点板块过滤", category="flags"),
    GenomeParam("use_llm_review", ParamType.BOOLEAN, False,
                description="LLM复核信号", category="flags"),
    GenomeParam("use_trend_strategy", ParamType.BOOLEAN, True,
                description="启用趋势策略", category="flags"),
    GenomeParam("use_reversal_strategy", ParamType.BOOLEAN, True,
                description="启用反转策略", category="flags"),
    GenomeParam("use_event_strategy", ParamType.BOOLEAN, True,
                description="启用事件策略", category="flags"),

    # ---- 资金管理 ----
    GenomeParam("max_positions", ParamType.DISCRETE, 5, 2, 15, 1,
                description="最大持仓数", category="capital"),
    GenomeParam("max_per_sector", ParamType.DISCRETE, 2, 1, 5, 1,
                description="同板块最大持仓", category="capital"),
    GenomeParam("position_size_pct", ParamType.CONTINUOUS, 0.25, 0.10, 0.40, 0.01,
                description="单票最大仓位", category="capital"),
    GenomeParam("top_n_picks", ParamType.DISCRETE, 4, 1, 10, 1,
                description="每日推荐数", category="capital"),
    GenomeParam("holding_days", ParamType.DISCRETE, 5, 1, 20, 1,
                description="默认持有天数", category="capital"),
]


def get_param_by_name(name: str) -> GenomeParam:
    """按名称查找参数定义"""
    for p in GENOME_SCHEMA:
        if p.name == name:
            return p
    raise KeyError(f"未知参数: {name}")


def get_params_by_category(category: str) -> List[GenomeParam]:
    """按分类获取参数列表"""
    return [p for p in GENOME_SCHEMA if p.category == category]


def get_default_genome_dict() -> Dict[str, Any]:
    """获取默认基因组 (字典格式)"""
    return {p.name: p.default for p in GENOME_SCHEMA}


def get_genome_bounds() -> List[Tuple[float, float]]:
    """
    获取连续参数的 (min, max) 边界列表
    用于GA编解码 (离散和布尔参数也有数值表示)
    """
    bounds = []
    for p in GENOME_SCHEMA:
        if p.type == ParamType.CONTINUOUS:
            bounds.append((p.min_value, p.max_value))
        elif p.type == ParamType.DISCRETE:
            bounds.append((p.min_value, p.max_value))
        elif p.type == ParamType.BOOLEAN:
            bounds.append((0, 1))
        elif p.type == ParamType.CATEGORICAL:
            bounds.append((0, len(p.choices) - 1))
    return bounds


def get_genome_count() -> int:
    """基因组总参数数"""
    return len(GENOME_SCHEMA)


# === GA适应度权重 ===
FITNESS_WEIGHTS = {
    "sharpe_ratio": 0.30,
    "annual_return": 0.20,
    "win_rate": 0.15,
    "calmar_ratio": 0.10,
    "max_drawdown": 0.15,       # 最小化 — 在计算时取负
    "profit_factor": 0.05,
    "signal_quality": 0.03,
    "turnover_stability": 0.02,
}
