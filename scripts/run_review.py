#!/usr/bin/env python3
"""盘后复盘 — systemd 触发"""
import sys; sys.path.insert(0, '/mnt/d/AI/quant-agent')
from core.agent_runner import agent_runner, agent_registry
from agents.review_agent import ReviewAgent
agent_registry.register(ReviewAgent())
r = agent_runner.run_agent('review_agent')
print(f'Review: {r.status} rating={r.output.get("review",{}).get("day_rating","?")}')
