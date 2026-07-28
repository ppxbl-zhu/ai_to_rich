"""
Population — 种群管理器
初始化、多样性监测、适应度排序、精英保留
"""
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from loguru import logger

from optimizer.genome import Genome, genome


class Individual:
    """种群个体"""

    def __init__(self, arr: np.ndarray, genome_obj: Genome = None):
        self.genome_arr = arr          # 数值编码
        self.fitness: Optional[float] = None
        self.fitness_breakdown: Dict[str, float] = {}
        self.params: Dict[str, Any] = {}
        self.id: str = ""
        self.generation: int = 0
        self.parent_ids: List[str] = []
        self.is_elite: bool = False
        self.created_by: str = "ga"

    def evaluate(self, fitness_score: float, breakdown: Dict[str, float] = None):
        """设置适应度"""
        self.fitness = fitness_score
        self.fitness_breakdown = breakdown or {}

    @property
    def is_evaluated(self) -> bool:
        return self.fitness is not None


class Population:
    """
    种群管理器
    管理一代种群的完整生命周期
    """

    def __init__(self, size: int = 50, genome_obj: Genome = None):
        self.size = size
        self.genome = genome_obj or genome
        self.individuals: List[Individual] = []
        self.generation: int = 0
        self.best_fitness_history: List[float] = []
        self.avg_fitness_history: List[float] = []

    # === 初始化 ===

    def initialize(self, seed_params: Dict[str, Any] = None,
                   llm_suggestions: List[Dict] = None):
        """
        初始化种群
        Args:
            seed_params: 种子参数 (当前最佳策略, 作为个体之一)
            llm_suggestions: LLM建议的参数方向 (作为种子注入)
        """
        self.individuals = []

        # 1. 当前最佳策略作为种子
        if seed_params:
            seed_arr = self.genome.seed_genome(seed_params, noise_std=0.02)
            ind = Individual(seed_arr, self.genome)
            ind.created_by = "human"
            ind.id = f"seed_gen{self.generation}"
            self.individuals.append(ind)
            logger.debug(f"[Population] 种子个体 (human)")

        # 2. LLM建议的种子
        if llm_suggestions:
            for i, suggestion in enumerate(llm_suggestions[:5]):
                adjusted = seed_params.copy() if seed_params else self.genome.decode(
                    self.genome.random_genome()
                )
                target = suggestion.get("target", "")
                direction = suggestion.get("suggested_direction", "")
                if target and direction:
                    current = adjusted.get(target, 0.5)
                    if direction == "increase":
                        adjusted[target] = min(current * 1.3, 1.0)
                    elif direction == "decrease":
                        adjusted[target] = max(current * 0.7, 0.0)
                arr = self.genome.encode(adjusted)
                ind = Individual(arr, self.genome)
                ind.created_by = "llm"
                ind.id = f"llm_seed_{i}_gen{self.generation}"
                self.individuals.append(ind)
            logger.debug(f"[Population] {len(llm_suggestions[:5])} LLM种子已注入")

        # 3. 随机填充至种群大小
        while len(self.individuals) < self.size:
            arr = self.genome.random_genome()
            ind = Individual(arr, self.genome)
            ind.created_by = "ga_random"
            ind.id = f"random_{len(self.individuals)}_gen{self.generation}"
            self.individuals.append(ind)

        # 4. 解码参数 (方便查看)
        for ind in self.individuals:
            if not ind.params:
                ind.params = self.genome.decode(ind.genome_arr)

        logger.info(f"[Population] G{self.generation}: {len(self.individuals)} 个体已初始化 "
                    f"(seed={seed_params is not None}, llm={llm_suggestions is not None})")

    def create_next_generation(self, offspring: List[Individual],
                                elites_from_prev: List[Individual] = None):
        """
        从子代创建下一代种群
        """
        new_pop = []

        # 精英保留 (从父代直接继承)
        if elites_from_prev:
            for elite in elites_from_prev[:2]:  # top 2
                new_elite = Individual(elite.genome_arr.copy(), self.genome)
                new_elite.id = f"elite_{elite.id}_gen{self.generation}"
                new_elite.created_by = "elite"
                new_pop.append(new_elite)

        # 添加子代
        for child in offspring:
            new_pop.append(child)

        # 填充至种群大小
        while len(new_pop) < self.size:
            arr = self.genome.random_genome()
            ind = Individual(arr, self.genome)
            ind.id = f"fill_{len(new_pop)}_gen{self.generation}"
            ind.created_by = "ga_random"
            new_pop.append(ind)

        self.individuals = new_pop[:self.size]
        logger.info(f"[Population] G{self.generation}: 下一代 "
                    f"{len(new_pop)} 个体 (精英={len(elites_from_prev or [])})")

    # === 统计 ===

    def compute_stats(self) -> Dict[str, Any]:
        """计算种群统计"""
        evaluated = [ind for ind in self.individuals if ind.is_evaluated]
        if not evaluated:
            return {"evaluated": 0, "total": len(self.individuals)}

        fitnesses = [ind.fitness for ind in evaluated]
        best_idx = np.argmax(fitnesses)
        worst_idx = np.argmin(fitnesses)

        self.best_fitness_history.append(fitnesses[best_idx])
        self.avg_fitness_history.append(np.mean(fitnesses))

        return {
            "generation": self.generation,
            "evaluated": len(evaluated),
            "total": len(self.individuals),
            "best_fitness": round(fitnesses[best_idx], 4),
            "avg_fitness": round(np.mean(fitnesses), 4),
            "median_fitness": round(np.median(fitnesses), 4),
            "std_fitness": round(np.std(fitnesses), 4),
            "worst_fitness": round(fitnesses[worst_idx], 4),
            "best_individual": evaluated[best_idx],
            "diversity": self._compute_diversity(),
        }

    def get_best(self) -> Optional[Individual]:
        """获取最优个体"""
        evaluated = [ind for ind in self.individuals if ind.is_evaluated]
        if not evaluated:
            return None
        return max(evaluated, key=lambda x: x.fitness)

    def get_elites(self, n: int = 5) -> List[Individual]:
        """获取精英个体 (top N)"""
        evaluated = [ind for ind in self.individuals if ind.is_evaluated]
        if not evaluated:
            return []
        evaluated.sort(key=lambda x: x.fitness, reverse=True)
        return evaluated[:n]

    def get_unevaluated(self) -> List[Individual]:
        """获取未评估个体"""
        return [ind for ind in self.individuals if not ind.is_evaluated]

    def _compute_diversity(self) -> float:
        """计算种群多样性 (平均成对距离)"""
        evaluated = [ind for ind in self.individuals if ind.is_evaluated]
        if len(evaluated) < 2:
            return 0.0

        distances = []
        for i in range(min(len(evaluated), 20)):
            for j in range(i + 1, min(len(evaluated), 20)):
                d = self.genome.distance(
                    evaluated[i].genome_arr,
                    evaluated[j].genome_arr,
                )
                distances.append(d)

        return float(np.mean(distances)) if distances else 0.0

    def is_converged(self, patience: int = 10, tol: float = 0.001) -> bool:
        """检查是否收敛 (最近N代最佳适应度无显著改善)"""
        if len(self.best_fitness_history) < patience:
            return False

        recent = self.best_fitness_history[-patience:]
        improvement = recent[-1] - recent[0]
        return improvement < tol
