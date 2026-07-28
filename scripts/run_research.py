#!/usr/bin/env python3
"""盘前市场调研 — systemd 触发"""
import sys; sys.path.insert(0, '/mnt/d/AI/quant-agent')
from core.agent_runner import agent_runner, agent_registry
from agents.research_agent import ResearchAgent
agent_registry.register(ResearchAgent())
r = agent_runner.run_agent('research_agent')
print(f'Research: {r.status} sentiment={r.output.get("sentiment")} sectors={r.output.get("top_sectors",[])[:3]}')
