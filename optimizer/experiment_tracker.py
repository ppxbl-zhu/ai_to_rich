"""
Experiment Tracker — 实验追踪系统
记录GA实验的完整生命周期, 支持恢复和对比
"""
from typing import Dict, List, Any, Optional
import json
import time
from datetime import datetime
from pathlib import Path
from loguru import logger


class ExperimentTracker:
    """
    实验追踪器
    记录实验配置、每代结果、最优基因组
    支持checkpoint恢复
    """

    def __init__(self, storage_path: str = None):
        self.storage_path = Path(storage_path or "data/experiments")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.current_experiment: Optional[Dict] = None
        self.generations_log: List[Dict] = []

    def start_experiment(self, config: Dict) -> str:
        """
        开始新实验
        Returns:
            experiment_id
        """
        exp_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.current_experiment = {
            "id": exp_id,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "config": config,
            "total_generations": 0,
            "best_fitness": None,
            "best_params": None,
            "fitness_history": [],
        }

        self.generations_log = []

        # 持久化初始状态
        self._save_checkpoint()

        logger.info(f"[Experiment] {exp_id} 开始: "
                    f"pop={config.get('population_size')}, "
                    f"gens={config.get('max_generations')}")
        return exp_id

    def log_generation(self, gen_stats: Dict, population_summary: Dict = None):
        """记录一代结果"""
        gen_entry = {
            "generation": gen_stats.get("generation", 0),
            "timestamp": datetime.now().isoformat(),
            "best_fitness": gen_stats.get("best_fitness"),
            "avg_fitness": gen_stats.get("avg_fitness"),
            "median_fitness": gen_stats.get("median_fitness"),
            "diversity": gen_stats.get("diversity"),
            "evaluated": gen_stats.get("evaluated", 0),
        }

        self.generations_log.append(gen_entry)

        if self.current_experiment:
            self.current_experiment["total_generations"] = len(self.generations_log)
            self.current_experiment["fitness_history"].append(gen_entry["best_fitness"])

            if gen_entry["best_fitness"] and (
                self.current_experiment["best_fitness"] is None or
                gen_entry["best_fitness"] > self.current_experiment["best_fitness"]
            ):
                self.current_experiment["best_fitness"] = gen_entry["best_fitness"]
                if gen_stats.get("best_individual"):
                    best_ind = gen_stats["best_individual"]
                    self.current_experiment["best_params"] = best_ind.params

        # 每5代保存checkpoint
        if gen_entry["generation"] % 5 == 0:
            self._save_checkpoint()

    def complete_experiment(self, final_result: Dict = None):
        """完成实验"""
        if self.current_experiment:
            self.current_experiment["status"] = "completed"
            self.current_experiment["completed_at"] = datetime.now().isoformat()
            if final_result:
                self.current_experiment["final_result"] = final_result

            self._save_checkpoint()
            self._save_final_result()

            logger.info(f"[Experiment] {self.current_experiment['id']} 完成: "
                       f"best_fitness={self.current_experiment['best_fitness']}")

    def fail_experiment(self, error: str):
        """标记实验失败"""
        if self.current_experiment:
            self.current_experiment["status"] = "failed"
            self.current_experiment["error"] = error
            self._save_checkpoint()

    def _save_checkpoint(self):
        """保存checkpoint"""
        if not self.current_experiment:
            return

        exp_id = self.current_experiment["id"]
        checkpoint_path = self.storage_path / f"{exp_id}_checkpoint.json"

        data = {
            **self.current_experiment,
            "generations": self.generations_log,
            "saved_at": datetime.now().isoformat(),
        }

        with open(checkpoint_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def _save_final_result(self):
        """保存最终结果到数据库"""
        try:
            from data.storage.sqlite_storage import storage

            exp = self.current_experiment
            if not exp:
                return

            storage.get_conn().execute("""
                INSERT OR REPLACE INTO ga_experiments
                (id, strategy_id, status, population_size, max_generations,
                 started_at, completed_at, config_json, summary_json,
                 best_genome_json, best_fitness, total_generations)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exp["id"],
                exp.get("config", {}).get("strategy_id", "default"),
                exp["status"],
                exp.get("config", {}).get("population_size"),
                exp.get("config", {}).get("max_generations"),
                exp.get("started_at"),
                exp.get("completed_at"),
                json.dumps(exp.get("config", {})),
                json.dumps({"best_fitness": exp.get("best_fitness")}),
                json.dumps(exp.get("best_params", {}), default=str),
                exp.get("best_fitness"),
                exp.get("total_generations"),
            ))
            storage.get_conn().commit()
            storage.get_conn().close()
        except Exception as e:
            logger.warning(f"[Experiment] DB存档失败: {e}")

    def load_experiment(self, exp_id: str) -> Optional[Dict]:
        """从checkpoint恢复实验"""
        checkpoint_path = self.storage_path / f"{exp_id}_checkpoint.json"
        if not checkpoint_path.exists():
            logger.warning(f"[Experiment] checkpoint未找到: {exp_id}")
            return None

        with open(checkpoint_path) as f:
            data = json.load(f)

        self.current_experiment = {
            k: v for k, v in data.items() if k not in ("generations", "saved_at")
        }
        self.generations_log = data.get("generations", [])

        logger.info(f"[Experiment] {exp_id} 已恢复: "
                    f"gens={len(self.generations_log)}")
        return data

    def list_experiments(self, limit: int = 20) -> List[Dict]:
        """列出历史实验"""
        experiments = []
        for f in sorted(self.storage_path.glob("*_checkpoint.json"),
                       key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                experiments.append({
                    "id": data.get("id"),
                    "status": data.get("status"),
                    "best_fitness": data.get("best_fitness"),
                    "total_generations": data.get("total_generations"),
                    "started_at": data.get("started_at"),
                })
            except Exception:
                pass
        return experiments[:limit]

    def get_fitness_curve(self, exp_id: str = None) -> Dict[str, List[float]]:
        """获取适应度曲线"""
        if exp_id:
            self.load_experiment(exp_id)

        if not self.generations_log:
            return {"generations": [], "best_fitness": [], "avg_fitness": []}

        return {
            "generations": [g["generation"] for g in self.generations_log],
            "best_fitness": [g["best_fitness"] for g in self.generations_log],
            "avg_fitness": [g["avg_fitness"] for g in self.generations_log],
            "diversity": [g.get("diversity", 0) for g in self.generations_log],
        }


# 全局实例
experiment_tracker = ExperimentTracker()
