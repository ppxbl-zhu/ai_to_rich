#!/bin/bash
# ============================================================
# QuantAgent 启动/停止脚本
# 管理所有服务的一键启停
# ============================================================
set -e

PROJECT_ROOT="/mnt/d/AI/quant-agent"
cd "$PROJECT_ROOT"

export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================================
# 命令处理
# ============================================================

case "${1:-}" in
    start)
        log "启动 QuantAgent..."

        # 1. 初始化数据库
        log "初始化数据库..."
        python3 -c "from data.storage.sqlite_storage import storage; storage.init_db()"

        # 2. 启动调度器 (后台)
        log "启动调度器..."
        nohup python3 -m scripts.cli schedule > logs/scheduler.log 2>&1 &
        echo $! > /tmp/quantagent_scheduler.pid
        log "  调度器 PID: $(cat /tmp/quantagent_scheduler.pid)"

        # 3. 启动Web Dashboard (后台)
        if [ "${DASHBOARD:-1}" = "1" ]; then
            log "启动Web Dashboard (端口5001)..."
            nohup python3 -c "from web.app import start_dashboard; start_dashboard(port=5001)" > logs/dashboard.log 2>&1 &
            echo $! > /tmp/quantagent_dashboard.pid
            log "  Dashboard PID: $(cat /tmp/quantagent_dashboard.pid)"
        fi

        # 4. 非交易时间也可以手动运行Agent
        log ""
        log "✅ QuantAgent 启动完成"
        log "   Dashboard: http://localhost:5001"
        log "   日志: tail -f logs/scheduler.log"
        log "   停止: $0 stop"

        # 前台保持 (Ctrl+C退出)
        if [ "${DAEMON:-0}" != "1" ]; then
            log "按 Ctrl+C 停止所有服务..."
            trap "$0 stop" INT TERM
            while true; do sleep 10; done
        fi
        ;;

    stop)
        log "停止 QuantAgent..."
        for pidfile in /tmp/quantagent_scheduler.pid /tmp/quantagent_dashboard.pid; do
            if [ -f "$pidfile" ]; then
                pid=$(cat "$pidfile")
                if kill -0 "$pid" 2>/dev/null; then
                    kill "$pid" && log "  停止 PID $pid ($(basename $pidfile))"
                fi
                rm -f "$pidfile"
            fi
        done
        log "✅ 所有服务已停止"
        ;;

    restart)
        $0 stop
        sleep 2
        $0 start
        ;;

    status)
        echo -e "${BLUE}=== QuantAgent 服务状态 ===${NC}"
        for pidfile in /tmp/quantagent_scheduler.pid /tmp/quantagent_dashboard.pid; do
            if [ -f "$pidfile" ]; then
                pid=$(cat "$pidfile")
                if kill -0 "$pid" 2>/dev/null; then
                    echo -e "  $(basename $pidfile .pid): ${GREEN}运行中${NC} (PID $pid)"
                else
                    echo -e "  $(basename $pidfile .pid): ${RED}已停止${NC}"
                fi
            fi
        done

        # 系统状态
        echo ""
        python3 -c "
from core.state_machine import state_machine
state_machine.update()
print(f'  交易日状态: {state_machine.state_label}')
print(f'  是否交易时段: {state_machine.is_trading}')
" 2>/dev/null || true
        ;;

    agent)
        # 手动运行Agent: ./start.sh agent research
        agent_name="${2:-research}"
        log "运行Agent: $agent_name"
        python3 -c "
from core.agent_runner import agent_runner, setup_default_agents
setup_default_agents()
result = agent_runner.run_agent('${agent_name}_agent')
print(f'Result: {result}')
"
        ;;

    init)
        log "初始化..."
        python3 -c "
from data.storage.sqlite_storage import storage
storage.init_db()
print('数据库初始化完成')
"
        # 创建日志目录
        mkdir -p logs data/experiments data/cache data/output
        log "✅ 初始化完成"
        ;;

    health)
        log "健康检查..."
        python3 -c "
import sys
errors = []

# 1. 数据库
try:
    from data.storage.sqlite_storage import storage
    stats = storage.get_trade_stats(7)
    print(f'  ✅ 数据库正常 (7日交易: {stats.get(\"total\",0)}笔)')
except Exception as e:
    print(f'  ❌ 数据库: {e}')
    errors.append('db')

# 2. 配置
try:
    from config.settings import LLM_API_KEY, PROJECT_ROOT
    print(f'  ✅ 配置加载 (项目: {PROJECT_ROOT})')
    has_llm = bool(LLM_API_KEY)
    print(f'  {\"✅\" if has_llm else \"⚠️\"} LLM API: {\"已配置\" if has_llm else \"未配置\"}')
except Exception as e:
    print(f'  ❌ 配置: {e}')
    errors.append('config')

# 3. 数据源
try:
    from agents.tools.data_tools import data_tools
    market = data_tools.get_market_index()
    if 'error' not in market:
        print(f'  ✅ 新浪行情可用')
    else:
        print(f'  ⚠️ 新浪行情: {market[\"error\"]}')
except Exception as e:
    print(f'  ⚠️ 行情: {e}')

# 4. K线数据库
from pathlib import Path
for p in [Path('/mnt/d/AI/auction-stock-picker/data/kline_cache.db'), Path('data/cache/kline_cache.db')]:
    if p.exists():
        import os
        size_mb = os.path.getsize(p) / 1024 / 1024
        print(f'  ✅ K线数据库: {p} ({size_mb:.0f}MB)')
        break
else:
    print(f'  ⚠️ K线数据库未找到')

sys.exit(1 if errors else 0)
"
        ;;

    *)
        echo "QuantAgent 管理脚本"
        echo ""
        echo "用法: $0 {start|stop|restart|status|agent|init|health}"
        echo ""
        echo "  start    启动所有服务 (调度器+Dashboard)"
        echo "  stop     停止所有服务"
        echo "  restart  重启所有服务"
        echo "  status   查看服务状态"
        echo "  agent    手动运行Agent (e.g. $0 agent research)"
        echo "  init     初始化数据库和目录"
        echo "  health   系统健康检查"
        echo ""
        echo "环境变量:"
        echo "  DASHBOARD=0  $0 start    # 不启动Dashboard"
        echo "  DAEMON=1     $0 start    # 后台模式"
        exit 1
        ;;
esac
