"""
LLM Co-Pilot — LLM辅助GA优化
三阶段介入: 假设生成 → 中间解读 → 最终决策
"""
from typing import Dict, List, Any, Optional
import json
from loguru import logger

from optimizer.population import Individual, Population


class LLMCoPilot:
    """
    LLM辅助优化器
    Phase A: 基于复盘结果生成优化假设 → 种子注入GA
    Phase B: 每5代分析种群 → 偏置变异方向
    Phase C: GA结束后分析 → 推荐部署决策
    """

    def __init__(self):
        self.analyses: List[Dict] = []

    # === Phase A: 假设生成 ===

    def generate_hypotheses(self, review_findings: Dict,
                            current_params: Dict) -> List[Dict]:
        """
        Phase A — 基于复盘发现生成优化假设
        Args:
            review_findings: Review Agent的输出
            current_params: 当前策略参数
        Returns:
            假设列表 [{"target":..., "direction":..., "rationale":...}, ...]
        """
        # 如果LLM可用, 使用LLM生成
        llm_hypotheses = self._llm_generate_hypotheses(review_findings, current_params)
        if llm_hypotheses:
            return llm_hypotheses

        # 否则使用启发式规则
        return self._heuristic_hypotheses(review_findings, current_params)

    def _llm_generate_hypotheses(self, review: Dict, params: Dict) -> Optional[List[Dict]]:
        """LLM生成假设"""
        try:
            from config.llm_config import get_prompt, chat_json
            from config.settings import LLM_API_KEY
            if not LLM_API_KEY:
                return None

            lessons = review.get("key_lessons", [])
            mistakes = review.get("mistakes", [])
            current = json.dumps(params, indent=2, ensure_ascii=False)

            prompt = f"""你是量化策略优化专家。基于以下复盘结果, 提出具体的参数优化方向:

复盘发现:
- 关键教训: {', '.join(lessons) if lessons else '无'}
- 错误: {', '.join(mistakes) if mistakes else '无'}

当前策略参数:
{current}

请输出JSON数组 (5个以内的优化建议):
[
  {{
    "target": "<参数名>",
    "current_value": "<当前值>",
    "suggested_direction": "increase | decrease | toggle",
    "magnitude": "<small | medium | large>",
    "rationale": "<调整理由, 30字>"
  }}
]"""

            messages = [
                {"role": "system", "content": "你是量化策略优化专家, 擅长参数调优。"},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, temperature=0.5, use_cache=False)
            if isinstance(result, dict):
                result = result.get("hypotheses", result.get("suggestions", []))
            return result if isinstance(result, list) else []

        except Exception as e:
            logger.warning(f"[LLM CoPilot] Phase A 失败: {e}")
            return None

    def _heuristic_hypotheses(self, review: Dict, params: Dict) -> List[Dict]:
        """启发式生成假设"""
        hypotheses = []

        day_rating = review.get("day_rating", "B")
        if day_rating in ("C", "D", "F"):
            hypotheses.append({
                "target": "min_auction_change",
                "current_value": params.get("min_auction_change", 1.0),
                "suggested_direction": "increase",
                "magnitude": "small",
                "rationale": f"近期评级{day_rating}, 建议提高选股门槛",
            })

        mistakes = review.get("mistakes", [])
        if any("止损" in m for m in mistakes):
            hypotheses.append({
                "target": "stop_loss_pct",
                "current_value": params.get("stop_loss_pct", -0.03),
                "suggested_direction": "increase",  # 收紧止损 (绝对值减小)
                "magnitude": "small",
                "rationale": "止损执行偏差, 建议收紧",
            })

        return hypotheses

    # === Phase B: 中间解读 ===

    def analyze_generation(self, population: Population) -> Dict[str, Any]:
        """
        Phase B — 分析当前代种群状态
        每5代调用一次
        """
        stats = population.compute_stats()
        if stats.get("evaluated", 0) < 5:
            return {"message": "评估个体不足, 跳过分析", **stats}

        # 尝试LLM分析
        llm_result = self._llm_analyze_generation(stats, population)
        if llm_result:
            self.analyses.append({"phase": "B", **llm_result})
            return {**stats, "llm_analysis": llm_result}

        return stats

    def _llm_analyze_generation(self, stats: Dict, population: Population) -> Optional[Dict]:
        """LLM分析当前代"""
        try:
            from config.llm_config import get_prompt, chat_json
            from config.settings import LLM_API_KEY
            if not LLM_API_KEY:
                return None

            # Top/Bottom个体
            elites = population.get_elites(5)
            worst = population.get_elites(1)  # 用get_elites获取排名, 再反转

            top_summary = []
            for e in elites:
                params = e.params or {}
                top_summary.append({
                    "fitness": e.fitness,
                    "params_snippet": {
                        k: params.get(k) for k in
                        ["auction_weight", "technical_weight", "stop_loss_pct", "take_profit_min"]
                        if k in params
                    },
                })

            # 构建适应度趋势
            trend = population.best_fitness_history[-10:] if population.best_fitness_history else []

            prompt = get_prompt("ga_analysis",
                generation=stats.get("generation", 0),
                fitness_trend=json.dumps({
                    "current_best": stats.get("best_fitness"),
                    "current_avg": stats.get("avg_fitness"),
                    "diversity": stats.get("diversity"),
                    "recent_trend": trend,
                }),
                top_genomes=json.dumps(top_summary, indent=2),
                bottom_genomes="[]",  # 简化
            )

            messages = [
                {"role": "system", "content": "你是遗传算法优化专家。"},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, temperature=0.3, use_cache=False)
            return result

        except Exception as e:
            logger.warning(f"[LLM CoPilot] Phase B 失败: {e}")
            return None

    # === Phase C: 最终决策 ===

    def final_analysis(self, population: Population,
                       experiment_config: Dict) -> Dict[str, Any]:
        """
        Phase C — GA结束后分析最优个体, 推荐是否部署
        """
        stats = population.compute_stats()
        best = population.get_best()

        if best is None:
            return {"recommendation": "no", "reason": "无有效个体"}

        # 尝试LLM分析
        llm_result = self._llm_final_analysis(best, stats, population)
        if llm_result:
            self.analyses.append({"phase": "C", **llm_result})
            return {
                "recommendation": llm_result.get("promotion_recommendation", "conditional"),
                "best_fitness": best.fitness,
                "best_params": best.params,
                "fitness_improvement": self._compute_improvement(population),
                "llm_analysis": llm_result,
            }

        # 启发式决策
        improvement = self._compute_improvement(population)
        recommendation = "yes" if improvement > 0.05 else "conditional" if improvement > 0.01 else "no"

        return {
            "recommendation": recommendation,
            "best_fitness": best.fitness,
            "best_params": best.params,
            "fitness_improvement": improvement,
            "reason": f"适应度提升 {improvement:.2%}" if improvement > 0 else "无显著提升",
        }

    def _llm_final_analysis(self, best: Individual, stats: Dict,
                            population: Population) -> Optional[Dict]:
        """LLM最终分析"""
        try:
            from config.llm_config import chat_json
            from config.settings import LLM_API_KEY
            if not LLM_API_KEY:
                return None

            improved_pct = self._compute_improvement(population) * 100

            prompt = f"""GA优化完成。请评估最优个体是否应该部署:

最优适应度: {best.fitness}
适应度提升: {improved_pct:.1f}%
代数: {stats.get('generation', 0)}
多样性: {stats.get('diversity', 0):.4f}

最优参数: {json.dumps(best.params, indent=2, ensure_ascii=False)}

请输出JSON:
{{
    "promotion_recommendation": "yes | no | conditional",
    "rationale": "<100字决策理由>",
    "risks": ["<风险1>", ...],
    "next_steps": ["<下一步1>", ...],
    "overfitting_assessment": "<low | medium | high>"
}}"""

            messages = [
                {"role": "system", "content": "你是量化策略部署决策专家。"},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, temperature=0.2, use_cache=False)
            return result

        except Exception as e:
            logger.warning(f"[LLM CoPilot] Phase C 失败: {e}")
            return None

    def _compute_improvement(self, population: Population) -> float:
        """计算适应度提升"""
        if len(population.best_fitness_history) < 2:
            return 0.0

        initial = population.best_fitness_history[0]
        final = population.best_fitness_history[-1]

        if initial == 0:
            return 0.0
        return (final - initial) / abs(initial)


# 全局实例
llm_co_pilot = LLMCoPilot()
