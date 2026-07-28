"""
Genome — 策略基因编解码器
将策略参数编码为数值数组(GA操作), 解码回参数字典(策略使用)
"""
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from loguru import logger

from config.genome_config import (
    GENOME_SCHEMA, GenomeParam, ParamType,
    get_default_genome_dict, get_genome_count, get_genome_bounds,
)


class Genome:
    """
    策略基因组
    封装编解码逻辑和约束处理
    """

    def __init__(self, schema: List[GenomeParam] = None):
        self.schema = schema or GENOME_SCHEMA
        self.n_params = len(self.schema)
        self.bounds = get_genome_bounds()

        # 建立索引映射
        self._param_index = {p.name: i for i, p in enumerate(self.schema)}

    # === 编码: 字典 → 数值数组 ===

    def encode(self, params: Dict[str, Any]) -> np.ndarray:
        """
        将参数字典编码为归一化数值数组 [0, 1]^n
        """
        arr = np.zeros(self.n_params, dtype=np.float64)

        for i, param in enumerate(self.schema):
            value = params.get(param.name, param.default)

            if param.type == ParamType.CONTINUOUS:
                # 归一化到 [0, 1]
                lo, hi = param.min_value, param.max_value
                if hi > lo:
                    arr[i] = (value - lo) / (hi - lo)
                else:
                    arr[i] = 0.5

            elif param.type == ParamType.DISCRETE:
                lo, hi = param.min_value, param.max_value
                if hi > lo:
                    arr[i] = (value - lo) / (hi - lo)
                else:
                    arr[i] = 0.5

            elif param.type == ParamType.BOOLEAN:
                arr[i] = 1.0 if value else 0.0

            elif param.type == ParamType.CATEGORICAL:
                if param.choices and value in param.choices:
                    arr[i] = param.choices.index(value) / (len(param.choices) - 1)
                else:
                    arr[i] = 0.5

        return np.clip(arr, 0, 1)

    # === 解码: 数值数组 → 字典 ===

    def decode(self, arr: np.ndarray) -> Dict[str, Any]:
        """
        将归一化数值数组解码为参数字典
        自动处理约束 (权重归一化等)
        """
        arr = np.clip(arr, 0, 1)
        params = {}

        for i, param in enumerate(self.schema):
            val = arr[i]

            if param.type == ParamType.CONTINUOUS:
                lo, hi = param.min_value, param.max_value
                value = lo + val * (hi - lo)
                # 四舍五入到step精度
                if param.step:
                    value = round(value / param.step) * param.step
                params[param.name] = value

            elif param.type == ParamType.DISCRETE:
                lo, hi = param.min_value, param.max_value
                raw = lo + val * (hi - lo)
                value = int(round(raw / (param.step or 1)) * (param.step or 1))
                params[param.name] = value

            elif param.type == ParamType.BOOLEAN:
                params[param.name] = bool(val > 0.5)  # 确保Python bool, 非numpy.bool_

            elif param.type == ParamType.CATEGORICAL:
                if param.choices:
                    idx = int(round(val * (len(param.choices) - 1)))
                    idx = max(0, min(idx, len(param.choices) - 1))
                    params[param.name] = param.choices[idx]
                else:
                    params[param.name] = param.default

        # 后处理: 归一化权重
        self._normalize_weights(params)

        return params

    def _normalize_weights(self, params: Dict[str, Any]):
        """归一化因子权重, 确保总和=1"""
        weight_keys = [
            "auction_weight", "sector_weight", "technical_weight",
            "fundamental_weight", "capital_weight",
        ]
        weights = [params.get(k, 0.2) for k in weight_keys]
        total = sum(weights)
        if total > 0:
            for i, k in enumerate(weight_keys):
                params[k] = weights[i] / total

    # === GA操作辅助 ===

    def random_genome(self) -> np.ndarray:
        """生成随机基因组"""
        arr = np.random.uniform(0, 1, self.n_params)
        # 对布尔参数做二值化
        for i, param in enumerate(self.schema):
            if param.type == ParamType.BOOLEAN:
                arr[i] = 1.0 if np.random.random() > 0.5 else 0.0
        return arr

    def seed_genome(self, base_params: Dict[str, Any],
                    noise_std: float = 0.05) -> np.ndarray:
        """
        基于已有参数生成种子基因组 (加小噪声)
        """
        base_arr = self.encode(base_params)
        noise = np.random.normal(0, noise_std, self.n_params)
        return np.clip(base_arr + noise, 0, 1)

    def mutate_gaussian(self, arr: np.ndarray, std: float = 0.1,
                        prob: float = 0.1) -> np.ndarray:
        """
        高斯变异: 以prob概率对每个基因位施加N(0, std)扰动
        """
        mask = np.random.random(self.n_params) < prob
        noise = np.random.normal(0, std, self.n_params)
        result = arr.copy()
        result[mask] += noise[mask]
        return np.clip(result, 0, 1)

    def crossover_uniform(self, arr1: np.ndarray, arr2: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        均匀交叉: 每个基因位以0.5概率交换
        """
        mask = np.random.random(self.n_params) < 0.5
        child1 = np.where(mask, arr1, arr2)
        child2 = np.where(mask, arr2, arr1)
        return child1, child2

    def distance(self, arr1: np.ndarray, arr2: np.ndarray) -> float:
        """计算两个基因组之间的欧氏距离 (多样性度量)"""
        return float(np.linalg.norm(arr1 - arr2))

    def to_dict(self) -> Dict[str, Any]:
        """导出基因组schema和bounds信息"""
        return {
            "n_params": self.n_params,
            "param_names": [p.name for p in self.schema],
            "bounds": self.bounds,
            "categories": [p.category for p in self.schema],
        }

    def summary(self, arr: np.ndarray) -> Dict[str, Any]:
        """基因组摘要 (用于日志)"""
        params = self.decode(arr)
        return {
            "weights": {
                k: round(params[k], 3)
                for k in ["auction_weight", "technical_weight", "fundamental_weight",
                          "capital_weight", "sector_weight"] if k in params
            },
            "thresholds": {
                k: params[k]
                for k in ["min_auction_change", "max_auction_change", "min_volume_ratio"]
                if k in params
            },
            "stops": {
                k: round(params[k], 4)
                for k in ["stop_loss_pct", "take_profit_min", "take_profit_max"]
                if k in params
            },
            "flags": {
                k: params[k]
                for k in ["use_hot_sector_filter", "use_trend_strategy",
                          "use_reversal_strategy", "use_event_strategy"]
                if k in params
            },
        }


# 全局实例
genome = Genome()
