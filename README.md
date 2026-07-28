# QuantAgent — AI驱动的A股量化交易系统 v1.0

基于 LLM + 遗传算法的自动化量化交易系统，实现选股-调研-监控-复盘全链路AI驱动。

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│  Agent Pipeline:  Research → Select → Monitor → Review       │
│                    ↑                    ↓                     │
│              LLM Co-Pilot ←── GA Engine ←── 复盘假设         │
├──────────────────────────────────────────────────────────────┤
│  Strategies:  Auction(86.6%) | Trend | Reversal | Event      │
│  Factors:     Auction | Technical | Fundamental | Capital    │
│              + Sentiment(LLM) | Macro                        │
├──────────────────────────────────────────────────────────────┤
│  Data:  AKShare | Sina | Eastmoney | Tushare                 │
│  Store: SQLite (local) | TimescaleDB (cloud)                 │
├──────────────────────────────────────────────────────────────┤
│  Notify: Telegram | WeChat | Web Dashboard(:5001)            │
└──────────────────────────────────────────────────────────────┘
```

## 快速开始

```bash
# 初始化
cd /mnt/d/AI/quant-agent
cp .env.example .env     # 编辑填入API Key
./scripts/start.sh init

# 启动所有服务
./scripts/start.sh start     # Dashboard: http://localhost:5001

# 手动运行Agent
./scripts/start.sh agent research    # 市场调研
./scripts/start.sh agent select      # 选股推荐
./scripts/start.sh agent review      # 复盘诊断

# 健康检查
./scripts/start.sh health
```

## 目录结构

```
quant-agent/
├── config/           # 配置层
│   ├── settings.py   # 全局配置 (因子权重/阈值/止损)
│   ├── llm_config.py # DeepSeek API + Prompt模板 + 缓存
│   ├── genome_config.py  # GA基因组 (31参数)
│   ├── alerts.yaml   # 告警规则 (13条)
│   └── trading_calendar.py
├── core/             # 核心框架
│   ├── event_bus.py  # 发布/订阅 (16种事件)
│   ├── context_manager.py  # 共享交易上下文
│   ├── state_machine.py    # 交易日状态机
│   └── agent_runner.py     # Agent注册/调度/执行
├── data/             # 数据层
│   └── storage/sqlite_storage.py  # 13表SQLite
├── engine/           # 分析引擎
│   ├── factors/      # 7类因子 (5传统+2LLM)
│   └── llm_analyzers/  # 形态/新闻/市场状态分析
├── agents/           # LLM Agent (4)
│   ├── research_agent.py  # 市场调研
│   ├── select_agent.py    # 多策略选股
│   ├── monitor_agent.py   # 实时监控
│   ├── review_agent.py    # 复盘诊断
│   └── tools/        # 16个可调用函数
├── strategies/       # 交易策略 (4)
│   ├── auction_strategy/  # 竞价 (86.6%胜率)
│   ├── trend_strategy/    # 趋势跟踪
│   ├── reversal_strategy/ # 超跌反弹
│   ├── event_strategy/    # 事件驱动
│   └── composite/    # 信号合并+资金分配
├── backtest/         # 回测引擎
│   ├── engine.py     # 多策略回测
│   └── ga_fitness.py # 8维适应度函数
├── optimizer/        # GA优化引擎
│   ├── ga_engine.py  # GA核心循环
│   ├── genome.py     # DNA编解码
│   ├── population.py # 种群管理
│   ├── operators.py  # 选择/交叉/变异
│   ├── llm_co_pilot.py  # LLM三阶段介入
│   └── experiment_tracker.py
├── monitor/          # 实时监控
│   ├── price_monitor.py   # 行情轮询
│   ├── alert_engine.py    # 告警规则(11条)
│   └── position_tracker.py # 持仓追踪
├── notification/     # 通知推送
├── web/              # Web仪表盘
│   └── app.py        # FastAPI (13端点+WS)
├── scheduler/        # 定时任务
│   ├── runner.py     # APScheduler
│   └── services/     # systemd服务文件
├── scripts/          # CLI+运维
│   ├── cli.py        # 统一CLI
│   ├── start.sh      # 启停脚本
│   └── health_check.py
└── docker-compose.yml # 云端部署
```

## 每日自动化

| 时间 | 任务 | Agent/模块 | 通知 |
|------|------|-----------|------|
| 00:05 | K线+数据增量刷新 | data/pipeline | — |
| 02:00 | 每日GA微调 (20×5代) | optimizer | — |
| 08:00 | 盘前市场调研 | research_agent | 微信+TG |
| 09:14 | 集合竞价选股 | select_agent | 微信+TG |
| 09:30-15:00 | 实时监控 | monitor | 告警推送 |
| 14:30 | 尾盘扫描 | trend/reversal | — |
| 15:30 | 盘后复盘 | review_agent | 微信+TG |
| 16:00 | 选股报告+事件报告 | select+event | TG |
| 周末 | GA大种群优化 (50×20) | optimizer | TG |

## 策略体系

### 竞价策略 (Auction) — 核心策略, 86.6%胜率
- 条件: 竞价涨幅2-5% + 量比3-10x + 多因子打分
- 持有: T+1短线
- 复用现有 auction-stock-picker 引擎

### 趋势策略 (Trend) — 中线3-10天
- 条件: MA多头排列 + 放量突破 + MACD零轴上
- 扫描: 全市场日K线技术指标

### 反转策略 (Reversal) — 短线1-3天
- 条件: RSI超卖 + 20日深度回撤 + 放量反弹
- 风险: 较高, 严格止损

### 事件策略 (Event) — 短线
- 条件: 新闻→概念映射→成分股筛选
- LLM: 分析事件影响力

## GA自我迭代

```
基因组: 31个参数 (权重/阈值/止损/技术指标/策略开关/资金管理)
适应度: 8维多目标 (Sharpe×0.30 + 收益×0.20 + 胜率×0.15 + ...)
节奏:
  每日: 20个体 × 5代 (微调)
  周末: 50个体 × 20代 (优化)
  月度: 100个体 × 50代 (大升级)
安全闸: LLM三阶段介入 → 人工确认 → 模拟盘验证 → 实盘部署
```

## 核心命令

```bash
# CLI
quant-agent init        # 初始化数据库
quant-agent status      # 系统状态
quant-agent run research  # 运行Agent
quant-agent backtest --start 2021-01-01 --end 2026-06-30
quant-agent optimize --population 50 --generations 20
quant-agent web --port 5001

# 运维
./scripts/start.sh start|stop|restart|status|health
./scripts/start.sh agent research|select|review
python3 scripts/health_check.py
```

## 配置要点

1. 复制 `.env.example` → `.env`, 填入:
   - `LLM_API_KEY` (DeepSeek) — 必需, LLM功能核心
   - `TELEGRAM_BOT_TOKEN` — 通知推送
   - `SCT_SEND_KEYS` — 微信推送
   - `TUSHARE_TOKEN` — 基本面数据

2. K线数据库: 系统自动查找以下路径:
   - `/mnt/d/AI/auction-stock-picker/data/kline_cache.db` (复用现有)
   - `data/cache/kline_cache.db` (本地)

3. 告警规则: 编辑 `config/alerts.yaml` 自定义

## 数据保护

1. 历史数据永不覆盖 — 增量合并
2. GA checkpoint每5代自动存档
3. 模拟盘交易自动记录到SQLite
4. 禁止: 修改T+1/删除覆盖历史数据
5. 允许: 修路径/补数据/调参数(记录原因)

## 自修复规则

1. 策略无信号 → 检查K线DB路径 + 交易日历
2. LLM调用失败 → 自动回退到启发式规则
3. Dashboard无响应 → `journalctl -u dashboard.service -n 30`
4. GA优化失败 → 从checkpoint恢复: `experiment_tracker.load_experiment(id)`
5. 数据落后 → 手动运行: `python3 -c "from data.pipeline.data_refresh import run; run()"`

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| LLM_API_KEY | DeepSeek API Key | 必需 |
| LLM_MODEL | 模型名 | deepseek-chat |
| TELEGRAM_BOT_TOKEN | Telegram Bot | — |
| SCT_SEND_KEYS | Server酱Key | — |
| TUSHARE_TOKEN | Tushare Token | — |
| GA_POPULATION_SIZE_DAILY | 每日GA种群 | 20 |
| GA_MAX_GENERATIONS_DAILY | 每日GA代数 | 5 |
| SIM_INITIAL_CAPITAL | 模拟盘资金 | 100000 |
