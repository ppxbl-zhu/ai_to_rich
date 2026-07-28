#!/usr/bin/env python3
"""竞价后选股 + 自动建仓 — systemd 09:25触发"""
import sys; sys.path.insert(0, '/mnt/d/AI/quant-agent')

# Step 0: 数据源自检
print("=== 数据源自检 ===")
from scripts.auction_check import check
check()

# Step 1: 选股
print("\n=== 多策略选股 ===")
from core.agent_runner import agent_runner, agent_registry
from agents.select_agent import SelectAgent
agent_registry.register(SelectAgent())
r = agent_runner.run_agent('select_agent')
print(f'Select: {r.status} picks={r.output.get("recommended",0)}')

# Step 2: 自动建仓
print("\n=== 自动建仓 ===")
from scripts.auto_trader import run
run()
