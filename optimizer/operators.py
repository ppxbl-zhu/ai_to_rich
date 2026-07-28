"""
Genetic Operators — 选择/交叉/变异算子
"""
from typing import List, Tuple
import numpy as np
from loguru import logger

from optimizer.population import Individual
from optimizer.genome import Genome


# ============================================================
# 选择算子
# ============================================================

def tournament_select(population: List[Individual], k: int = 5,
                      n_select: int = None) -> List[Individual]:
    """
    锦标赛选择: 随机选k个个体, 取适应度最高的
    Args:
        population: 已评估个体列表
        k: 锦标赛大小
        n_select: 选择多少个 (默认=len(population)//2)
    Returns:
        选中个体列表 (作为父代)
    """
    if n_select is None:
        n_select = max(2, len(population) // 2)

    evaluated = [ind for ind in population if ind.is_evaluated]
    if len(evaluated) < k:
        return evaluated[:n_select]

    selected = []
    for _ in range(n_select):
        candidates = np.random.choice(evaluated, size=min(k, len(evaluated)), replace=False)
        winner = max(candidates, key=lambda x: x.fitness)
        selected.append(winner)

    return selected


def roulette_select(population: List[Individual], n_select: int = None) -> List[Individual]:
    """
    轮盘赌选择: 适应度越高, 被选中概率越大
    """
    if n_select is None:
        n_select = max(2, len(population) // 2)

    evaluated = [ind for ind in population if ind.is_evaluated]
    if not evaluated:
        return []

    fitnesses = np.array([ind.fitness for ind in evaluated])
    # 适应度平移使所有值为正
    min_f = fitnesses.min()
    if min_f < 0:
        fitnesses = fitnesses - min_f + 0.01

    total = fitnesses.sum()
    if total == 0:
        probs = np.ones(len(evaluated)) / len(evaluated)
    else:
        probs = fitnesses / total

    indices = np.random.choice(len(evaluated), size=min(n_select, len(evaluated)),
                               replace=False, p=probs)
    return [evaluated[i] for i in indices]


# ============================================================
# 交叉算子
# ============================================================

def uniform_crossover(parent1: Individual, parent2: Individual,
                      genome: Genome = None, crossover_rate: float = 0.7) -> Tuple[Individual, Individual]:
    """
    均匀交叉: 每个基因位独立决定从哪个父代继承
    """
    if genome is None:
        from optimizer.genome import genome as default_genome
        genome = default_genome

    if np.random.random() > crossover_rate:
        # 不交叉, 直接复制
        child1 = Individual(parent1.genome_arr.copy(), genome)
        child2 = Individual(parent2.genome_arr.copy(), genome)
    else:
        arr1, arr2 = genome.crossover_uniform(parent1.genome_arr, parent2.genome_arr)
        child1 = Individual(arr1, genome)
        child2 = Individual(arr2, genome)

    child1.parent_ids = [parent1.id, parent2.id]
    child2.parent_ids = [parent1.id, parent2.id]

    return child1, child2


def blend_crossover(parent1: Individual, parent2: Individual,
                    genome: Genome = None, alpha: float = 0.3,
                    crossover_rate: float = 0.7) -> Tuple[Individual, Individual]:
    """
    BLX-alpha交叉: 子代基因在父代扩展区间内随机取值
    适用于连续参数
    """
    if genome is None:
        from optimizer.genome import genome as default_genome
        genome = default_genome

    if np.random.random() > crossover_rate:
        child1 = Individual(parent1.genome_arr.copy(), genome)
        child2 = Individual(parent2.genome_arr.copy(), genome)
    else:
        arr1 = parent1.genome_arr
        arr2 = parent2.genome_arr
        d = np.abs(arr1 - arr2)
        lo = np.maximum(0, np.minimum(arr1, arr2) - alpha * d)
        hi = np.minimum(1, np.maximum(arr1, arr2) + alpha * d)
        child1_arr = np.random.uniform(lo, hi)
        child2_arr = np.random.uniform(lo, hi)
        child1 = Individual(np.clip(child1_arr, 0, 1), genome)
        child2 = Individual(np.clip(child2_arr, 0, 1), genome)

    child1.parent_ids = [parent1.id, parent2.id]
    child2.parent_ids = [parent1.id, parent2.id]

    return child1, child2


# ============================================================
# 变异算子
# ============================================================

def gaussian_mutation(individual: Individual, genome: Genome = None,
                      std: float = 0.1, mutation_rate: float = 0.1) -> Individual:
    """
    高斯变异: 每个基因有mutation_rate概率被N(0, std)扰动
    """
    if genome is None:
        from optimizer.genome import genome as default_genome
        genome = default_genome

    new_arr = genome.mutate_gaussian(individual.genome_arr, std, mutation_rate)
    mutant = Individual(new_arr, genome)
    mutant.parent_ids = [individual.id]
    mutant.created_by = "mutation"
    return mutant


def adaptive_mutation(individual: Individual, genome: Genome = None,
                      generation: int = 0, max_generations: int = 50,
                      diversity: float = 0.5) -> Individual:
    """
    自适应变异: 根据种群多样性自动调整变异强度
    多样性低 → 增大变异率, 帮助跳出局部最优
    多样性高 → 减小变异率, 精细搜索
    """
    if genome is None:
        from optimizer.genome import genome as default_genome
        genome = default_genome

    # 自适应变异率
    base_rate = 0.1
    diversity_factor = max(0.5, 1.0 - diversity)  # 1-diversity, 低多样性→高因子
    generation_factor = 1.0 - 0.5 * (generation / max_generations)  # 后期降低变异
    adapted_rate = base_rate * diversity_factor * generation_factor
    adapted_rate = np.clip(adapted_rate, 0.02, 0.3)

    # 自适应变异强度
    adapted_std = 0.1 * diversity_factor * generation_factor
    adapted_std = np.clip(adapted_std, 0.02, 0.2)

    return gaussian_mutation(individual, genome, std=adapted_std,
                            mutation_rate=adapted_rate)


# ============================================================
# 繁殖流水线
# ============================================================

def breed_generation(parents: List[Individual], pop_size: int,
                     genome: Genome = None, generation: int = 0,
                     max_generations: int = 50, diversity: float = 0.5,
                     crossover_rate: float = 0.7,
                     mutation_rate: float = 0.1) -> List[Individual]:
    """
    一代繁殖流水线: 选择 → 交叉 → 变异
    """
    if genome is None:
        from optimizer.genome import genome as default_genome
        genome = default_genome

    offspring = []

    # 配对繁殖 (生成 pop_size 个子代)
    n_pairs = (pop_size + 1) // 2
    for i in range(n_pairs):
        # 随机选两个父代
        p1_idx, p2_idx = np.random.choice(
            len(parents), size=2, replace=len(parents) < 2
        )
        p1, p2 = parents[p1_idx], parents[p2_idx]

        # 交叉
        c1, c2 = uniform_crossover(p1, p2, genome, crossover_rate)

        # 变异
        c1 = adaptive_mutation(c1, genome, generation, max_generations, diversity)
        c2 = adaptive_mutation(c2, genome, generation, max_generations, diversity)

        c1.generation = generation
        c2.generation = generation
        c1.id = f"offspring_{i*2}_gen{generation}"
        c2.id = f"offspring_{i*2+1}_gen{generation}"

        offspring.append(c1)
        offspring.append(c2)

    return offspring[:pop_size]
