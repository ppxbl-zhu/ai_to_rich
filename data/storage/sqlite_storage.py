"""
SQLite存储 — 元数据、配置、信号日志、交易记录
"""
import sqlite3
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger


SCHEMA_SQL = """
-- 策略DNA存储
CREATE TABLE IF NOT EXISTS strategy_dna (
    id TEXT PRIMARY KEY,
    generation INTEGER NOT NULL DEFAULT 0,
    parent_ids TEXT,              -- JSON数组
    genome TEXT NOT NULL,         -- JSON: 完整基因参数
    fitness_score REAL,
    sharpe_ratio REAL,
    win_rate REAL,
    annual_return REAL,
    max_drawdown REAL,
    calmar_ratio REAL,
    profit_factor REAL,
    backtest_start TEXT,
    backtest_end TEXT,
    is_active INTEGER DEFAULT 0,
    created_by TEXT DEFAULT 'human',  -- 'ga' | 'llm' | 'human'
    created_at TEXT DEFAULT (datetime('now')),
    notes TEXT
);

-- 策略信号日志
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    strategy_id TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    signal_type TEXT NOT NULL,    -- 'buy' | 'sell' | 'alert'
    direction TEXT,
    confidence REAL,
    price REAL,
    stop_loss REAL,
    take_profit REAL,
    horizon TEXT DEFAULT '短线',
    reason TEXT,
    dna_snapshot TEXT,            -- JSON: 产生信号时的策略参数快照
    llm_review TEXT,              -- LLM复核意见
    status TEXT DEFAULT 'pending' -- pending | confirmed | rejected | executed | expired
);

-- 交易记录
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER REFERENCES signals(id),
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    direction TEXT NOT NULL,      -- 'buy' | 'sell'
    entry_date TEXT,
    entry_price REAL,
    exit_date TEXT,
    exit_price REAL,
    shares INTEGER DEFAULT 100,
    pnl REAL,
    pnl_pct REAL,
    hold_days INTEGER,
    strategy_id TEXT,
    exit_reason TEXT,
    is_sim INTEGER DEFAULT 1,    -- 1=模拟盘, 0=实盘
    tags TEXT,                    -- JSON数组
    created_at TEXT DEFAULT (datetime('now'))
);

-- 市场研究笔记
CREATE TABLE IF NOT EXISTS research_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category TEXT,                -- 'macro' | 'sector' | 'event' | 'risk'
    title TEXT,
    content TEXT,                 -- LLM生成的研究内容(Markdown)
    sentiment REAL,               -- -1 to 1
    key_sectors TEXT,             -- JSON数组
    risk_alerts TEXT,             -- JSON数组
    source_urls TEXT,             -- JSON数组
    created_at TEXT DEFAULT (datetime('now'))
);

-- 复盘记录
CREATE TABLE IF NOT EXISTS review_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    trade_ids TEXT,               -- JSON: 关联的交易ID列表
    day_rating TEXT,              -- A/B/C/D/F
    key_lessons TEXT,             -- JSON数组
    mistakes TEXT,                -- JSON数组
    improvement_hypotheses TEXT,  -- JSON: [{"target":..., "direction":..., "rationale":...}]
    action_items TEXT,            -- JSON数组
    tomorrow_focus TEXT,          -- JSON数组
    summary TEXT,                 -- 复盘总结
    market_regime TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Agent执行日志
CREATE TABLE IF NOT EXISTS agent_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    agent_name TEXT NOT NULL,
    trigger TEXT,                 -- 'scheduled' | 'event' | 'manual'
    status TEXT,                  -- 'completed' | 'failed' | 'timeout'
    duration_ms REAL,
    tokens_used INTEGER DEFAULT 0,
    input_summary TEXT,
    output_summary TEXT,
    error TEXT
);

-- GA实验记录
CREATE TABLE IF NOT EXISTS ga_experiments (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',  -- queued | running | completed | failed
    population_size INTEGER,
    max_generations INTEGER,
    started_at TEXT,
    completed_at TEXT,
    config_json TEXT,             -- GA超参数
    summary_json TEXT,            -- 最终结果摘要
    best_genome_json TEXT,        -- 最优基因组
    best_fitness REAL,
    total_generations INTEGER,
    notes TEXT
);

-- GA代际记录
CREATE TABLE IF NOT EXISTS ga_generations (
    experiment_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    best_fitness REAL,
    avg_fitness REAL,
    median_fitness REAL,
    diversity REAL,
    top_genome_json TEXT,
    llm_analysis TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (experiment_id, generation)
);

-- LLM调用缓存 (持久化)
CREATE TABLE IF NOT EXISTS llm_cache (
    query_hash TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    prompt_preview TEXT,
    response TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 通知日志
CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    channel TEXT NOT NULL,        -- 'telegram' | 'wechat' | 'email'
    priority TEXT NOT NULL,       -- 'urgent' | 'high' | 'normal' | 'low'
    title TEXT,
    body TEXT,
    status TEXT DEFAULT 'sent',   -- 'sent' | 'failed' | 'delivered'
    error TEXT
);

-- 持仓快照 (每日)
CREATE TABLE IF NOT EXISTS position_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    shares INTEGER,
    entry_price REAL,
    current_price REAL,
    pnl REAL,
    pnl_pct REAL,
    strategy_id TEXT,
    is_sim INTEGER DEFAULT 1
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_code ON signals(stock_code);
CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy_id);
CREATE INDEX IF NOT EXISTS idx_trades_code ON trades(stock_code);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(entry_date);
CREATE INDEX IF NOT EXISTS idx_research_date ON research_notes(date);
CREATE INDEX IF NOT EXISTS idx_review_date ON review_notes(date);
CREATE INDEX IF NOT EXISTS idx_agent_log_agent ON agent_log(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_log_time ON agent_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_position_snap_date ON position_snapshots(date);
CREATE INDEX IF NOT EXISTS idx_ga_exp_status ON ga_experiments(status);
"""


class SQLiteStorage:
    """SQLite存储管理器"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.getenv("SQLITE_PATH", "data/quantagent.db")
        self.db_path = str(db_path)

        # 确保父目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            logger.info(f"数据库初始化完成: {self.db_path}")
        finally:
            conn.close()

    def get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # === 策略DNA ===

    def save_genome(self, genome_data: Dict[str, Any]) -> str:
        """保存基因组"""
        conn = self.get_conn()
        try:
            genome_id = genome_data.get("id", f"dna_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            conn.execute("""
                INSERT OR REPLACE INTO strategy_dna
                (id, generation, parent_ids, genome, fitness_score, sharpe_ratio,
                 win_rate, annual_return, max_drawdown, calmar_ratio, profit_factor,
                 backtest_start, backtest_end, is_active, created_by, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                genome_id,
                genome_data.get("generation", 0),
                json.dumps(genome_data.get("parent_ids", [])),
                json.dumps(genome_data.get("genome", {})),
                genome_data.get("fitness_score"),
                genome_data.get("sharpe_ratio"),
                genome_data.get("win_rate"),
                genome_data.get("annual_return"),
                genome_data.get("max_drawdown"),
                genome_data.get("calmar_ratio"),
                genome_data.get("profit_factor"),
                genome_data.get("backtest_start"),
                genome_data.get("backtest_end"),
                genome_data.get("is_active", 0),
                genome_data.get("created_by", "human"),
                genome_data.get("notes", ""),
            ))
            conn.commit()
            return genome_id
        finally:
            conn.close()

    def get_active_genome(self) -> Optional[Dict]:
        """获取当前激活的基因组"""
        conn = self.get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM strategy_dna WHERE is_active=1 ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row:
                d = dict(row)
                d["genome"] = json.loads(d["genome"])
                d["parent_ids"] = json.loads(d.get("parent_ids", "[]"))
                return d
            return None
        finally:
            conn.close()

    def get_genome_history(self, limit: int = 50) -> List[Dict]:
        """获取基因组进化历史"""
        conn = self.get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM strategy_dna ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # === 信号 ===

    def save_signal(self, signal_data: Dict[str, Any]) -> int:
        """保存策略信号"""
        conn = self.get_conn()
        try:
            cur = conn.execute("""
                INSERT INTO signals
                (strategy_id, stock_code, stock_name, signal_type, direction,
                 confidence, price, stop_loss, take_profit, horizon, reason,
                 dna_snapshot, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_data.get("strategy_id", ""),
                signal_data.get("stock_code", ""),
                signal_data.get("stock_name", ""),
                signal_data.get("signal_type", "buy"),
                signal_data.get("direction", "buy"),
                signal_data.get("confidence", 0),
                signal_data.get("price", 0),
                signal_data.get("stop_loss", 0),
                signal_data.get("take_profit", 0),
                signal_data.get("horizon", "短线"),
                signal_data.get("reason", ""),
                json.dumps(signal_data.get("dna_snapshot", {})),
                signal_data.get("status", "pending"),
            ))
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_signals_today(self) -> List[Dict]:
        """获取今日信号"""
        today = datetime.now().strftime("%Y-%m-%d")
        conn = self.get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM signals WHERE date(timestamp)=? ORDER BY timestamp DESC",
                (today,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # === 交易 ===

    def save_trade(self, trade_data: Dict[str, Any]) -> int:
        """保存交易记录"""
        conn = self.get_conn()
        try:
            cur = conn.execute("""
                INSERT INTO trades
                (signal_id, stock_code, stock_name, direction, entry_date,
                 entry_price, exit_date, exit_price, shares, pnl, pnl_pct,
                 hold_days, strategy_id, exit_reason, is_sim, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_data.get("signal_id"),
                trade_data.get("stock_code", ""),
                trade_data.get("stock_name", ""),
                trade_data.get("direction", "buy"),
                trade_data.get("entry_date"),
                trade_data.get("entry_price", 0),
                trade_data.get("exit_date"),
                trade_data.get("exit_price"),
                trade_data.get("shares", 100),
                trade_data.get("pnl"),
                trade_data.get("pnl_pct"),
                trade_data.get("hold_days"),
                trade_data.get("strategy_id", ""),
                trade_data.get("exit_reason", ""),
                trade_data.get("is_sim", 1),
                json.dumps(trade_data.get("tags", [])),
            ))
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_trade_stats(self, days: int = 30) -> Dict:
        """获取交易统计"""
        conn = self.get_conn()
        try:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(pnl_pct) as avg_return,
                    SUM(pnl) as total_pnl
                FROM trades
                WHERE entry_date >= date('now', ?)
            """, (f"-{days} days",)).fetchone()
            d = dict(row)
            d["win_rate"] = d["wins"] / d["total"] * 100 if d["total"] > 0 else 0
            return d
        finally:
            conn.close()

    # === 日志 ===

    def log_agent_run(self, log_data: Dict[str, Any]):
        """记录Agent运行日志"""
        conn = self.get_conn()
        try:
            conn.execute("""
                INSERT INTO agent_log
                (agent_name, trigger, status, duration_ms, tokens_used,
                 input_summary, output_summary, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_data.get("agent_name", ""),
                log_data.get("trigger", "manual"),
                log_data.get("status", "completed"),
                log_data.get("duration_ms", 0),
                log_data.get("tokens_used", 0),
                log_data.get("input_summary", ""),
                log_data.get("output_summary", ""),
                log_data.get("error"),
            ))
            conn.commit()
        finally:
            conn.close()

    def log_notification(self, log_data: Dict[str, Any]):
        """记录通知日志"""
        conn = self.get_conn()
        try:
            conn.execute("""
                INSERT INTO notification_log (channel, priority, title, body, status, error)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                log_data.get("channel", ""),
                log_data.get("priority", "normal"),
                log_data.get("title", ""),
                log_data.get("body", ""),
                log_data.get("status", "sent"),
                log_data.get("error"),
            ))
            conn.commit()
        finally:
            conn.close()


# 全局单例
storage = SQLiteStorage()
