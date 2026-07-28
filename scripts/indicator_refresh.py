#!/usr/bin/env python3
"""
每日技术指标批量刷新
凌晨运行一次, 计算全市场5739只股票的技术指标并写入快照表
策略扫描时直接读快照表, 无需实时计算
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from loguru import logger

DB_PATHS = [
    Path("/mnt/d/AI/auction-stock-picker/data/cache/kline_cache.db"),
    Path("data/cache/kline_cache.db"),
]


def find_db() -> Path:
    for p in DB_PATHS:
        if p.exists():
            return p
    raise FileNotFoundError("K线数据库未找到")


def compute_indicators_for_stock(df: pd.DataFrame) -> dict:
    """对单只股票的K线计算全部技术指标 (向量化)"""
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    last = len(df) - 1

    result = {"code": df["code"].iloc[0], "date": df["date"].iloc[last]}

    # 基本数据
    result["close"] = round(float(close.iloc[last]), 2)
    result["open"] = round(float(df["open"].iloc[last]), 2)
    result["high"] = round(float(high.iloc[last]), 2)
    result["low"] = round(float(low.iloc[last]), 2)
    result["volume"] = int(volume.iloc[last])
    result["pre_close"] = round(float(close.iloc[last - 1]), 2) if last > 0 else 0

    # MA
    if len(close) >= 5:
        result["ma5"] = round(float(close.rolling(5).mean().iloc[last]), 2)
    if len(close) >= 20:
        result["ma20"] = round(float(close.rolling(20).mean().iloc[last]), 2)
    if len(close) >= 60:
        result["ma60"] = round(float(close.rolling(60).mean().iloc[last]), 2)

    # MACD
    if len(close) >= 26:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        result["macd_dif"] = round(float(dif.iloc[last]), 4)
        result["macd_dea"] = round(float(dea.iloc[last]), 4)
        result["macd_bar"] = round(float(2 * (dif.iloc[last] - dea.iloc[last])), 4)

    # RSI
    if len(close) >= 14:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        for p in [6, 14, 24]:
            if len(close) >= p:
                avg_g = gain.rolling(p).mean()
                avg_l = loss.rolling(p).mean()
                rs = avg_g / avg_l.replace(0, 1)
                result[f"rsi{p}"] = round(float((100 - (100 / (1 + rs))).iloc[last]), 1)

    # 量比
    if len(volume) >= 6:
        result["vol_ratio_5"] = round(float(volume.iloc[last] / volume.iloc[-6:-1].mean()), 2)
    if len(volume) >= 21:
        result["vol_ratio_20"] = round(float(volume.iloc[last] / volume.iloc[-21:-1].mean()), 2)

    # 位置指标
    if len(close) >= 20:
        result["drawdown_20d"] = round(float((close.iloc[last] / high.rolling(20).max().iloc[last] - 1) * 100), 2)
        result["high_20d"] = round(float(high.rolling(20).max().iloc[last]), 2)
        result["low_20d"] = round(float(low.rolling(20).min().iloc[last]), 2)

    return result


def refresh_all(db_path: Path):
    """全量刷新技术指标快照"""
    conn = sqlite3.connect(str(db_path))
    t0 = time.time()

    # 获取所有股票代码 + 名称 (从Tushare)
    codes_raw = conn.execute(
        "SELECT DISTINCT code FROM kline_daily WHERE date >= ?",
        ("2026-01-01",)
    ).fetchall()
    codes = [r[0] for r in codes_raw]

    # 从Tushare获取股票名称和状态
    import os
    from dotenv import load_dotenv
    load_dotenv()
    import tushare as ts
    ts.set_token(os.getenv('TUSHARE_TOKEN', ''))
    pro = ts.pro_api()
    try:
        stocks_info = pro.stock_basic(exchange='', list_status='L', fields='symbol,name')
        code2name = dict(zip(stocks_info['symbol'], stocks_info['name'])) if stocks_info is not None else {}
    except Exception:
        code2name = {}

    logger.info(f"开始刷新 {len(codes)} 只股票的技术指标... (名称覆盖: {len(code2name)})")

    updated = 0
    batch_size = 500  # 每500只提交一次

    for i, code in enumerate(codes):
        try:
            # 读取最近90天K线
            df = pd.read_sql_query(
                "SELECT code, date, open, high, low, close, volume "
                "FROM kline_daily WHERE code=? AND date >= ? "
                "ORDER BY date",
                conn, params=(code, "2026-01-01")
            )

            if len(df) < 20:  # 停牌或新股, 跳过
                continue

            indicators = compute_indicators_for_stock(df)
            # 补上名称
            indicators['name'] = code2name.get(code, '')
            cols = list(indicators.keys())
            placeholders = ",".join(["?"] * len(cols))
            conn.execute(
                f"INSERT OR REPLACE INTO daily_indicator_snapshot "
                f"({','.join(cols)}) VALUES ({placeholders})",
                [indicators[c] for c in cols]
            )

            updated += 1

        except Exception as e:
            logger.debug(f"  {code} 失败: {e}")

        # 批量提交
        if (i + 1) % batch_size == 0:
            conn.commit()
            elapsed = time.time() - t0
            logger.info(f"  进度: {i+1}/{len(codes)} ({updated} updated, {elapsed:.0f}s)")

    conn.commit()
    elapsed = time.time() - t0
    logger.info(f"刷新完成: {updated}/{len(codes)} 只, 耗时 {elapsed:.0f}s")

    # 验证
    count = conn.execute("SELECT COUNT(*) FROM daily_indicator_snapshot").fetchone()[0]
    logger.info(f"快照表: {count} 行")

    conn.close()
    return updated


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | {message}")

    db = find_db()
    logger.info(f"K线数据库: {db}")
    refresh_all(db)
