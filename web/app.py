"""
Web Dashboard — FastAPI + WebSocket 实时仪表盘
提供策略状态、持仓、Agent活动、GA实验监控
"""
from typing import Dict, Any, List
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import json
import asyncio
from loguru import logger

app = FastAPI(title="QuantAgent Dashboard", version="0.1.0")

# WebSocket连接管理
_ws_clients: List[WebSocket] = []


# ============================================================
# REST API
# ============================================================

@app.get("/")
async def root():
    """Dashboard主页"""
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/api/status")
async def api_status():
    """系统状态"""
    try:
        from core.state_machine import state_machine
        from core.agent_runner import agent_registry

        state_machine.update()
        return {
            "timestamp": datetime.now().isoformat(),
            "trading_state": state_machine.state.value,
            "trading_state_label": state_machine.state_label,
            "is_trading": state_machine.is_trading,
            "agents": agent_registry.list_agents(),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/portfolio")
async def api_portfolio():
    """模拟盘状态"""
    try:
        from agents.tools.trading_tools import trading_tools
        return trading_tools.get_portfolio_summary()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/positions")
async def api_positions():
    """持仓详情"""
    try:
        from monitor.position_tracker import position_tracker
        return position_tracker.snapshot()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/signals")
async def api_signals():
    """今日信号"""
    try:
        from data.storage.sqlite_storage import storage
        return {"signals": storage.get_signals_today()}
    except Exception as e:
        return {"error": str(e), "signals": []}


@app.get("/api/alerts")
async def api_alerts():
    """告警历史"""
    try:
        from monitor.alert_engine import alert_engine
        return {"alerts": alert_engine.get_history(limit=50)}
    except Exception as e:
        return {"error": str(e), "alerts": []}


@app.get("/api/strategies")
async def api_strategies():
    """策略配置"""
    try:
        from strategies.auction_strategy.runner import AuctionStrategy
        from strategies.trend_strategy.runner import TrendStrategy
        from strategies.reversal_strategy.runner import ReversalStrategy
        from strategies.event_strategy.runner import EventStrategy

        strategies = {}
        for s in [AuctionStrategy(), TrendStrategy(), ReversalStrategy(), EventStrategy()]:
            strategies[s.strategy_name] = {
                "description": s.strategy_description,
                "parameters": s.get_parameters(),
                "enabled": s.enabled,
            }
        return {"strategies": strategies}
    except Exception as e:
        return {"error": str(e), "strategies": {}}


@app.get("/api/experiments")
async def api_experiments():
    """GA实验列表"""
    try:
        from optimizer.experiment_tracker import experiment_tracker
        return {"experiments": experiment_tracker.list_experiments(limit=20)}
    except Exception as e:
        return {"error": str(e), "experiments": []}


@app.get("/api/experiments/{exp_id}")
async def api_experiment_detail(exp_id: str):
    """GA实验详情 + 适应度曲线"""
    try:
        from optimizer.experiment_tracker import experiment_tracker
        curve = experiment_tracker.get_fitness_curve(exp_id)
        return {"experiment_id": exp_id, "fitness_curve": curve}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/market")
async def api_market():
    """大盘行情"""
    try:
        from agents.tools.data_tools import data_tools
        return data_tools.get_market_index()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/agent-history")
async def api_agent_history():
    """Agent执行历史"""
    try:
        from core.agent_runner import agent_runner
        history = agent_runner.get_history(limit=20)
        return {"history": [
            {
                "agent": r.agent_name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in history
        ]}
    except Exception as e:
        return {"error": str(e), "history": []}


@app.get("/api/daily-schedule")
async def api_daily_schedule():
    """每日自动化时间表"""
    from config.settings import (
        AUCTION_START, AUCTION_END, FINAL_SNAPSHOT_TIME,
    )
    return {
        "schedule": [
            {"time": "02:00", "task": "每日GA微调", "status": "scheduled"},
            {"time": "08:00", "task": "盘前市场调研", "status": "scheduled"},
            {"time": AUCTION_START, "task": "集合竞价开始", "status": "scheduled"},
            {"time": FINAL_SNAPSHOT_TIME, "task": "竞价最终快照", "status": "scheduled"},
            {"time": "09:30", "task": "连续交易+实时监控", "status": "scheduled"},
            {"time": "14:30", "task": "尾盘扫描", "status": "scheduled"},
            {"time": "15:00", "task": "收盘", "status": "scheduled"},
            {"time": "15:30", "task": "盘后复盘", "status": "scheduled"},
            {"time": "16:00", "task": "选股报告+事件报告", "status": "scheduled"},
        ],
        "current": datetime.now().strftime("%H:%M"),
    }


# ============================================================
# WebSocket (实时推送)
# ============================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    logger.info(f"[Dashboard] WebSocket连接: {len(_ws_clients)} clients")

    try:
        while True:
            # 等待客户端消息 (心跳)
            data = await websocket.receive_text()

            if data == "ping":
                # 发送实时状态
                status = await _get_realtime_status()
                await websocket.send_text(json.dumps(status))
    except WebSocketDisconnect:
        _ws_clients.remove(websocket)
        logger.info(f"[Dashboard] WebSocket断开: {len(_ws_clients)} clients")
    except Exception as e:
        _ws_clients.remove(websocket)


async def _get_realtime_status() -> Dict:
    """获取实时状态 (推送给WebSocket客户端)"""
    try:
        from core.state_machine import state_machine
        from agents.tools.trading_tools import trading_tools
        from monitor.alert_engine import alert_engine

        state_machine.update()
        portfolio = trading_tools.get_portfolio_summary()
        alerts = alert_engine.get_stats()

        return {
            "timestamp": datetime.now().isoformat(),
            "trading_state": state_machine.state_label,
            "portfolio_value": portfolio.get("total_value", 0),
            "portfolio_pnl": portfolio.get("total_pnl", 0),
            "positions_count": portfolio.get("positions_count", 0),
            "alerts_today": alerts.get("total_today", 0),
        }
    except Exception:
        return {"timestamp": datetime.now().isoformat(), "error": "fetch failed"}


async def broadcast_status():
    """向所有WebSocket客户端广播状态更新"""
    if not _ws_clients:
        return

    status = await _get_realtime_status()
    msg = json.dumps(status)

    disconnected = []
    for ws in _ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        _ws_clients.remove(ws)


# ============================================================
# Dashboard HTML
# ============================================================

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuantAgent Dashboard</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: -apple-system, 'Microsoft YaHei', sans-serif; background:#0f172a; color:#e2e8f0; min-height:100vh; }
        .header { background:#1e293b; padding:16px 24px; border-bottom:1px solid #334155; display:flex; justify-content:space-between; align-items:center; }
        .header h1 { font-size:20px; color:#38bdf8; }
        .status-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
        .status-dot.online { background:#22c55e; }
        .status-dot.offline { background:#ef4444; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(350px,1fr)); gap:16px; padding:16px; }
        .card { background:#1e293b; border-radius:8px; padding:20px; border:1px solid #334155; }
        .card h2 { font-size:16px; margin-bottom:12px; color:#94a3b8; border-bottom:1px solid #334155; padding-bottom:8px; }
        .metric { display:flex; justify-content:space-between; padding:6px 0; }
        .metric .label { color:#94a3b8; }
        .metric .value { font-weight:600; }
        .metric .positive { color:#22c55e; }
        .metric .negative { color:#ef4444; }
        table { width:100%; border-collapse:collapse; font-size:14px; }
        th, td { padding:8px 4px; text-align:left; border-bottom:1px solid #334155; }
        th { color:#94a3b8; font-weight:500; }
        .tag { padding:2px 8px; border-radius:4px; font-size:12px; }
        .tag-urgent { background:#dc2626; color:#fff; }
        .tag-high { background:#ea580c; color:#fff; }
        .tag-normal { background:#2563eb; color:#fff; }
        .tag-low { background:#4b5563; color:#fff; }
        .refresh { font-size:12px; color:#64748b; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 QuantAgent Dashboard</h1>
        <div>
            <span class="status-dot online" id="ws-status"></span>
            <span id="trading-state" style="margin-left:8px;">--</span>
            <span class="refresh" id="refresh-time" style="margin-left:16px;"></span>
        </div>
    </div>
    <div class="grid" id="dashboard">
        <div class="card"><h2>Loading...</h2></div>
    </div>
    <script>
        let ws;
        function connect() {
            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${location.host}/ws`);
            ws.onopen = () => {
                document.getElementById('ws-status').className = 'status-dot online';
                ws.send('ping');
            };
            ws.onmessage = (e) => {
                const data = JSON.parse(e.data);
                document.getElementById('trading-state').textContent = data.trading_state || '--';
                document.getElementById('refresh-time').textContent = new Date().toLocaleTimeString();
                updateCards(data);
            };
            ws.onclose = () => {
                document.getElementById('ws-status').className = 'status-dot offline';
                setTimeout(connect, 5000);
            };
        }
        function updateCards(data) {
            let html = `
                <div class="card">
                    <h2>💼 模拟盘</h2>
                    <div class="metric"><span class="label">总资产</span><span class="value">¥${(data.portfolio_value||0).toLocaleString()}</span></div>
                    <div class="metric"><span class="label">总盈亏</span><span class="value ${(data.portfolio_pnl||0)>=0?'positive':'negative'}">¥${(data.portfolio_pnl||0).toLocaleString()}</span></div>
                    <div class="metric"><span class="label">持仓数</span><span class="value">${data.positions_count||0} 只</span></div>
                    <div class="metric"><span class="label">今日告警</span><span class="value">${data.alerts_today||0} 条</span></div>
                </div>
                <div class="card">
                    <h2>🔗 API Links</h2>
                    <div><a href="/api/status" style="color:#38bdf8;">/api/status</a> — 系统状态</div>
                    <div><a href="/api/portfolio" style="color:#38bdf8;">/api/portfolio</a> — 模拟盘</div>
                    <div><a href="/api/positions" style="color:#38bdf8;">/api/positions</a> — 持仓详情</div>
                    <div><a href="/api/signals" style="color:#38bdf8;">/api/signals</a> — 今日信号</div>
                    <div><a href="/api/alerts" style="color:#38bdf8;">/api/alerts</a> — 告警历史</div>
                    <div><a href="/api/strategies" style="color:#38bdf8;">/api/strategies</a> — 策略配置</div>
                    <div><a href="/api/experiments" style="color:#38bdf8;">/api/experiments</a> — GA实验</div>
                    <div><a href="/api/daily-schedule" style="color:#38bdf8;">/api/daily-schedule</a> — 每日计划</div>
                </div>
            `;
            document.getElementById('dashboard').innerHTML = html;
        }
        // 初始加载
        fetch('/api/status').then(r=>r.json()).then(d=>{
            document.getElementById('trading-state').textContent = d.trading_state_label || '--';
        });
        connect();
    </script>
</body>
</html>"""


def start_dashboard(host: str = "0.0.0.0", port: int = 5001):
    """启动Dashboard"""
    import uvicorn
    logger.info(f"Dashboard: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
