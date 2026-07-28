"""
GA Engine — 遗传算法核心循环
种群初始化 → 适应度评估 → 选择 → 繁殖 → 迭代
集成LLM Co-Pilot三阶段介入
"""
from typing import Dict, List, Any, Optional
import json
import time
import numpy as np
from loguru import logger

from optimizer.genome import Genome, genome
from optimizer.population import Population, Individual
from optimizer.operators import (
    tournament_select, breed_generation,
)
from optimizer.generation_runner import GenerationRunner
from optimizer.llm_co_pilot import LLMCoPilot
from optimizer.experiment_tracker import ExperimentTracker


class GAEngine:
    """
    遗传算法优化引擎
    完整的GA迭代循环 + LLM辅助 + 实验追踪
    """

    def __init__(self,
                 population_size: int = 50,
                 max_generations: int = 20,
                 crossover_rate: float = 0.7,
                 mutation_rate: float = 0.1,
                 elite_count: int = 2,
                 early_stop_generations: int = 10,
                 parallel_workers: int = 4,
                 genome_obj: Genome = None):
        self.population_size = population_size
        self.max_generations = max_generations
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.elite_count = elite_count
        self.early_stop_generations = early_stop_generations
        self.parallel_workers = parallel_workers

        self.genome = genome_obj or genome
        self.population = Population(population_size, self.genome)
        self.runner = GenerationRunner(self.genome, parallel_workers)
        self.co_pilot = LLMCoPilot()
        self.tracker = ExperimentTracker()

    def evolve(self, seed_params: Dict = None,
               review_findings: Dict = None,
               backtest_config: Dict = None) -> Dict[str, Any]:
        """
        运行完整GA优化
        Args:
            seed_params: 初始策略参数 (当前最优)
            review_findings: 复盘Agent的改进假设
            backtest_config: 回测配置
        Returns:
            {"best_params":..., "best_fitness":..., "improvement":..., "generations":...}
        """
        t_start = time.time()

        # Phase A: LLM生成优化假设
        llm_hypotheses = []
        if review_findings:
            llm_hypotheses = self.co_pilot.generate_hypotheses(
                review_findings, seed_params or {}
            )
            logger.info(f"[GA] Phase A: {len(llm_hypotheses)} LLM假设已生成")

        # 实验追踪
        exp_id = self.tracker.start_experiment({
            "population_size": self.population_size,
            "max_generations": self.max_generations,
            "crossover_rate": self.crossover_rate,
            "mutation_rate": self.mutation_rate,
            "seed_params": seed_params,
            "llm_hypotheses_count": len(llm_hypotheses),
        })

        # Step 1: 初始化种群
        self.population.generation = 0
        self.population.initialize(
            seed_params=seed_params,
            llm_suggestions=llm_hypotheses,
        )

        # Step 2: 评估初始种群
        self.runner.evaluate_population(self.population, backtest_config)
        gen_stats = self.population.compute_stats()
        self.tracker.log_generation(gen_stats)
        logger.info(f"[GA] G0: best={gen_stats['best_fitness']:.4f}, "
                   f"avg={gen_stats['avg_fitness']:.4f}")

        best_fitness_overall = gen_stats["best_fitness"]
        best_params_overall = None
        stagnation_counter = 0

        # Step 3: 迭代进化
        for gen in range(1, self.max_generations + 1):
            self.population.generation = gen

            # 3a. 选择父代
            parents = tournament_select(
                self.population.individuals,
                k=min(5, len(self.population.individuals)),
            )

            # 3b. 繁殖子代
            offspring = breed_generation(
                parents,
                pop_size=self.population_size - self.elite_count,
                genome=self.genome,
                generation=gen,
                max_generations=self.max_generations,
                diversity=gen_stats.get("diversity", 0.5),
                crossover_rate=self.crossover_rate,
                mutation_rate=self.mutation_rate,
            )

            # 3c. 精英保留
            elites = self.population.get_elites(self.elite_count)
            self.population.create_next_generation(offspring, elites)

            # 3d. 评估新一代
            self.runner.evaluate_population(self.population, backtest_config)
            gen_stats = self.population.compute_stats()
            self.tracker.log_generation(gen_stats)

            if gen % 5 == 0 or gen == 1:
                logger.info(f"[GA] G{gen}: best={gen_stats['best_fitness']:.4f}, "
                           f"avg={gen_stats['avg_fitness']:.4f}, "
                           f"div={gen_stats['diversity']:.4f}")

            # 3e. 更新全局最优
            if gen_stats["best_fitness"] > best_fitness_overall:
                best_fitness_overall = gen_stats["best_fitness"]
                best_params_overall = gen_stats.get("best_individual")
                stagnation_counter = 0
            else:
                stagnation_counter += 1

            # 3f. Phase B: 每5代LLM分析
            if gen % 5 == 0:
                self.co_pilot.analyze_generation(self.population)

            # 3g. 早停检查
            if stagnation_counter >= self.early_stop_generations:
                logger.info(f"[GA] 早停: {self.early_stop_generations}代无改善")
                break

            # 多样性过低 → 注入随机个体
            if gen_stats.get("diversity", 0) < 0.1:
                logger.info(f"[GA] 多样性过低, 注入随机个体")
                self._inject_diversity(5)

        # Step 4: Phase C — 最终分析
        final_analysis = self.co_pilot.final_analysis(
            self.population,
            {"max_generations": gen, "population_size": self.population_size},
        )

        # Step 5: 完成实验
        self.tracker.complete_experiment(final_analysis)

        elapsed = time.time() - t_start
        best = self.population.get_best()

        result = {
            "experiment_id": exp_id,
            "generations_completed": gen,
            "best_fitness": best_fitness_overall,
            "best_params": best.params if best else {},
            "initial_fitness": self.population.best_fitness_history[0]
                               if self.population.best_fitness_history else 0,
            "improvement_pct": round(
                (best_fitness_overall / self.population.best_fitness_history[0] - 1) * 100
                if self.population.best_fitness_history and self.population.best_fitness_history[0] > 0
                else 0, 2
            ),
            "fitness_curve": self.tracker.get_fitness_curve(),
            "recommendation": final_analysis.get("recommendation", "conditional"),
            "llm_analysis": final_analysis.get("llm_analysis", {}),
            "elapsed_seconds": round(elapsed, 1),
        }

        logger.info(f"[GA] 优化完成 ({elapsed:.0f}s): "
                   f"best_fitness={best_fitness_overall:.4f}, "
                   f"improve={result['improvement_pct']:.1f}%, "
                   f"recommend={result['recommendation']}")

        return result

    def _inject_diversity(self, n_random: int = 5):
        """注入随机个体增加多样性"""
        for i in range(n_random):
            arr = self.genome.random_genome()
            ind = Individual(arr, self.genome)
            ind.id = f"diversity_inject_{i}_gen{self.population.generation}"
            ind.created_by = "diversity_injection"

            # 替换最差个体
            if self.population.individuals:
                evaluated = [x for x in self.population.individuals if x.is_evaluated]
                if evaluated:
                    worst = min(evaluated, key=lambda x: x.fitness)
                    idx = self.population.individuals.index(worst)
                    self.population.individuals[idx] = ind

    def quick_evolve(self, seed_params: Dict = None,
                     generations: int = 5,
                     population_size: int = 20) -> Dict:
        """
        快速优化 (每日小种群)
        """
        old_max = self.max_generations
        old_pop = self.population_size
        self.max_generations = generations
        self.population_size = population_size
        self.population = Population(population_size, self.genome)

        result = self.evolve(seed_params=seed_params)

        self.max_generations = old_max
        self.population_size = old_pop
        return result

    def promote_best(self, experiment_id: str = None) -> bool:
        """
        将最优基因组提升为活跃策略
        保存到数据库, 标记is_active=True
        """
        try:
            best = self.population.get_best()
            if not best or not best.params:
                logger.warning("[GA] 无最优个体可提升")
                return False

            from data.storage.sqlite_storage import storage

            # 取消当前活跃
            conn = storage.get_conn()
            conn.execute("UPDATE strategy_dna SET is_active=0 WHERE is_active=1")
            conn.commit()

            # 保存新最优
            storage.save_genome({
                "id": f"dna_promoted_{int(time.time())}",
                "generation": self.population.generation,
                "genome": json.dumps(best.params, default=str),  # 转为JSON避免bool问题
                "fitness_score": float(best.fitness),
                "created_by": "ga_promoted",
                "is_active": 1,
                "notes": f"GA优化产物: G{self.population.generation}, "
                        f"fitness={best.fitness:.4f}",
            })

            logger.info(f"[GA] 基因组已提升为活跃策略: fitness={best.fitness:.4f}")
            return True

        except Exception as e:
            logger.error(f"[GA] 提升失败: {e}")
            return False


# 全局实例
ga_engine = GAEngine()
