"""
Generation Runner — 单代并行评估执行器
对种群每个个体运行回测, 计算适应度
"""
from typing import Dict, List, Any, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
from loguru import logger

from optimizer.population import Individual, Population
from optimizer.genome import Genome, genome


class GenerationRunner:
    """
    单代评估执行器
    支持并行回测 (多进程) 和串行回测
    """

    def __init__(self, genome_obj: Genome = None, parallel_workers: int = 4):
        self.genome = genome_obj or genome
        self.parallel_workers = parallel_workers

    def evaluate_population(self, population: Population,
                            backtest_config: Dict = None) -> Population:
        """
        评估种群中所有未评估个体
        Args:
            population: 种群对象
            backtest_config: 回测配置 (传递给每个worker)
        Returns:
            评估后的种群 (in-place)
        """
        to_evaluate = population.get_unevaluated()

        if not to_evaluate:
            logger.info("[GenRunner] 所有个体已评估")
            return population

        logger.info(f"[GenRunner] 开始评估 {len(to_evaluate)} 个个体 "
                    f"(workers={self.parallel_workers})")

        backtest_config = backtest_config or {
            "start_date": "2021-01-01",
            "end_date": "2026-06-30",
            "initial_capital": 100000,
        }

        if self.parallel_workers > 1:
            results = self._evaluate_parallel(to_evaluate, backtest_config)
        else:
            results = self._evaluate_sequential(to_evaluate, backtest_config)

        # 更新个体适应度
        for individual, fitness_result in zip(to_evaluate, results):
            if fitness_result:
                individual.evaluate(
                    fitness_result.get("fitness", 0),
                    fitness_result.get("breakdown", {}),
                )
                individual.params = self.genome.decode(individual.genome_arr)

        n_evaluated = sum(1 for ind in to_evaluate if ind.is_evaluated)
        logger.info(f"[GenRunner] 评估完成: {n_evaluated}/{len(to_evaluate)}")

        return population

    def _evaluate_parallel(self, individuals: List[Individual],
                           config: Dict) -> List[Optional[Dict]]:
        """并行评估 (多进程)"""
        results = [None] * len(individuals)

        try:
            with ProcessPoolExecutor(max_workers=self.parallel_workers) as executor:
                futures = {}
                for i, ind in enumerate(individuals):
                    params = self.genome.decode(ind.genome_arr)
                    future = executor.submit(
                        _evaluate_one_backtest, params, config
                    )
                    futures[future] = i

                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        result = future.result(timeout=120)
                        results[idx] = result
                    except Exception as e:
                        logger.warning(f"[GenRunner] 个体{idx}评估失败: {e}")
                        results[idx] = {"fitness": 0.0, "breakdown": {}}

        except Exception as e:
            logger.warning(f"[GenRunner] 并行评估失败, 回退到串行: {e}")
            results = self._evaluate_sequential(individuals, config)

        return results

    def _evaluate_sequential(self, individuals: List[Individual],
                             config: Dict) -> List[Optional[Dict]]:
        """串行评估"""
        results = []
        for i, ind in enumerate(individuals):
            try:
                params = self.genome.decode(ind.genome_arr)
                result = _evaluate_one_backtest(params, config)
                results.append(result)
            except Exception as e:
                logger.warning(f"[GenRunner] 个体{i}评估失败: {e}")
                results.append({"fitness": 0.0, "breakdown": {}})

            if (i + 1) % 10 == 0:
                logger.debug(f"[GenRunner] 串行进度: {i+1}/{len(individuals)}")

        return results


def _evaluate_one_backtest(params: Dict, config: Dict) -> Dict[str, Any]:
    """
    单个个体回测评估 (独立函数, 用于多进程)
    用真实K线数据 + run_with_params 评估基因组
    """
    try:
        from backtest.ga_fitness import ga_fitness
        from backtest.engine import BacktestEngine

        engine = BacktestEngine()
        stats = engine.run_with_params(
            params=params,
            start_date=config.get("start_date", "2022-01-01"),
            end_date=config.get("end_date", "2026-06-30"),
            initial_capital=config.get("initial_capital", 100000),
            strategy_names=config.get("strategy_names", ["trend", "reversal"]),
        )

        fitness_result = ga_fitness.compute(stats)
        return fitness_result
    except Exception as e:
        return {"fitness": 0.0, "breakdown": {}, "error": str(e)}
