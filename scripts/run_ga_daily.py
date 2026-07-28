#!/usr/bin/env python3
"""每日GA微调 — systemd 触发"""
import sys; sys.path.insert(0, '/mnt/d/AI/quant-agent')
from optimizer.ga_engine import ga_engine
from config.genome_config import get_default_genome_dict
r = ga_engine.quick_evolve(seed_params=get_default_genome_dict(), generations=5, population_size=20)
print(f'GA daily: fitness={r["best_fitness"]:.4f} improve={r["improvement_pct"]:.1f}%')
