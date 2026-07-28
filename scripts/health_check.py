#!/usr/bin/env python3
"""
QuantAgent 健康检查脚本
用于 Docker healthcheck / cron 监控
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

errors = []
warnings = []

def ok(msg): print(f"  ✅ {msg}")
def warn(msg): warnings.append(msg); print(f"  ⚠️ {msg}")
def fail(msg): errors.append(msg); print(f"  ❌ {msg}")

print("=== QuantAgent Health Check ===")
print()

# 1. 数据库连接
print("1. Database")
try:
    from data.storage.sqlite_storage import storage
    stats = storage.get_trade_stats(7)
    ok(f"SQLite: {stats.get('total',0)} trades in 7 days")
except Exception as e:
    fail(f"Database: {e}")

# 2. 配置
print("2. Configuration")
try:
    from config.settings import PROJECT_ROOT, LLM_API_KEY
    ok(f"Project: {PROJECT_ROOT}")
    if LLM_API_KEY:
        ok("LLM API Key: configured")
    else:
        warn("LLM API Key: not configured (LLM features disabled)")
except Exception as e:
    fail(f"Config: {e}")

# 3. 策略可用性
print("3. Strategies")
try:
    from strategies.auction_strategy.runner import AuctionStrategy
    from strategies.trend_strategy.runner import TrendStrategy
    from strategies.reversal_strategy.runner import ReversalStrategy
    from strategies.event_strategy.runner import EventStrategy
    ok(f"4 strategies loadable")
except Exception as e:
    fail(f"Strategies: {e}")

# 4. K线数据库
print("4. K-line Database")
from pathlib import Path
kline_paths = [
    Path("/mnt/d/AI/auction-stock-picker/data/kline_cache.db"),
    Path("data/cache/kline_cache.db"),
]
found = False
for p in kline_paths:
    if p.exists():
        size_mb = os.path.getsize(p) / 1024 / 1024
        ok(f"K-line DB: {p} ({size_mb:.0f}MB)")
        found = True
        break
if not found:
    warn("K-line DB not found (strategies will return 0 signals)")

# 5. 外部API
print("5. External APIs")
try:
    from agents.tools.data_tools import data_tools
    market = data_tools.get_market_index()
    if 'error' not in market:
        ok(f"Market API: {len(market)} indices available")
    else:
        warn(f"Market API: {market['error']}")
except Exception as e:
    warn(f"Market API: {e}")

# 6. Agent 注册
print("6. Agents")
try:
    from core.agent_runner import agent_registry, setup_default_agents
    setup_default_agents()
    agents = agent_registry.list_agents()
    ok(f"{len(agents)} agents registered")
except Exception as e:
    fail(f"Agents: {e}")

# 7. 磁盘空间
print("7. Disk")
try:
    import shutil
    usage = shutil.disk_usage("/mnt/d/AI")
    free_gb = usage.free / 1024 / 1024 / 1024
    if free_gb > 5:
        ok(f"Free space: {free_gb:.1f}GB")
    else:
        warn(f"Low disk: {free_gb:.1f}GB free")
except Exception as e:
    warn(f"Disk check: {e}")

# Summary
print()
print("=" * 50)
if not errors:
    print(f"✅ HEALTHY ({len(warnings)} warnings)")
    sys.exit(0)
else:
    print(f"❌ UNHEALTHY: {len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1)
