#!/usr/bin/env python3
"""
本地K线增量更新 — 替代云端数据同步
每天收盘后运行, 从 Tushare 拉取最新交易日K线
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from pathlib import Path
from datetime import date, timedelta
from dotenv import load_dotenv
load_dotenv()

import tushare as ts
from loguru import logger

DB_PATH = Path("/mnt/d/AI/auction-stock-picker/data/cache/kline_cache.db")


def get_latest_date(conn) -> str:
    row = conn.execute("SELECT MAX(date) FROM kline_daily").fetchone()
    return row[0] if row[0] else "20210101"


def update_kline():
    token = os.getenv("TUSHARE_TOKEN", "")
    if not token:
        logger.error("TUSHARE_TOKEN 未配置!")
        return

    ts.set_token(token)
    pro = ts.pro_api()

    conn = sqlite3.connect(str(DB_PATH))
    latest = get_latest_date(conn)
    today = date.today().strftime("%Y%m%d")

    # 找到需要更新的日期范围
    if latest >= today:
        logger.info(f"K线已是最新 ({latest}), 无需更新")
        conn.close()
        return

    logger.info(f"K线增量更新: {latest} → {today}")

    # 获取交易日历
    try:
        cal = pro.trade_cal(exchange="SSE", start_date=latest, end_date=today)
        trade_dates = cal[cal["is_open"] == 1]["cal_date"].tolist()
    except Exception:
        # fallback: 按日期推算
        trade_dates = []
        d = date.fromisoformat(latest[:4] + "-" + latest[4:6] + "-" + latest[6:8]) + timedelta(days=1)
        end = date.today()
        while d <= end:
            if d.weekday() < 5:
                trade_dates.append(d.strftime("%Y%m%d"))
            d += timedelta(days=1)

    new_dates = [d for d in trade_dates if d > latest]
    if not new_dates:
        logger.info("无新交易日")
        conn.close()
        return

    logger.info(f"需更新 {len(new_dates)} 个交易日: {new_dates[0]}~{new_dates[-1]}")

    # 获取全市场股票列表
    stocks = pro.stock_basic(exchange="", list_status="L", fields="ts_code")
    if stocks is None:
        logger.error("无法获取股票列表")
        conn.close()
        return

    codes = stocks["ts_code"].tolist()
    logger.info(f"全市场 {len(codes)} 只上市股票")

    updated = 0
    for trade_date in new_dates:
        date_str = trade_date
        logger.info(f"  拉取 {date_str}...")
        batch_count = 0

        try:
            df = pro.daily(trade_date=date_str)
            if df is None or len(df) == 0:
                logger.warning(f"  {date_str}: 无数据")
                continue

            for _, row in df.iterrows():
                ts_code = row["ts_code"]
                code = ts_code.split(".")[0]
                try:
                    conn.execute(
                        """INSERT OR REPLACE INTO kline_daily
                        (code, date, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (code, date_str,
                         float(row["open"]), float(row["high"]),
                         float(row["low"]), float(row["close"]),
                         float(row["vol"])),
                    )
                    batch_count += 1
                except Exception:
                    pass

            conn.commit()
            updated += batch_count
            logger.info(f"  {date_str}: {batch_count} 条")

        except Exception as e:
            logger.warning(f"  {date_str} 失败: {e}")
            continue

    conn.close()
    logger.info(f"K线更新完成: {updated} 条新纪录")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | {message}")
    update_kline()
