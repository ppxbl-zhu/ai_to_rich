"""
Kline Skill — K线数据查询
数据源: SQLite K线缓存 (666万行, 5726只股票, 2021-2026)
"""
from typing import Dict, Any, List
from pathlib import Path
import sqlite3
from loguru import logger

from skills.base import BaseSkill, skill_registry


class KlineSkill(BaseSkill):
    name = "get_kline"
    description = "获取A股个股历史K线数据(OHLCV), 支持指定股票代码和天数。用于技术分析。"
    schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "股票代码, 6位数字, 如 000001",
            },
            "days": {
                "type": "integer",
                "description": "最近N个交易日, 默认60",
            },
        },
        "required": ["code"],
    }

    # K线数据库路径
    DB_PATHS = [
        Path("data/cache/kline_cache.db"),
        Path("/mnt/d/AI/auction-stock-picker/data/cache/kline_cache.db"),
    ]

    def execute(self, code: str, days: int = 60, **kwargs) -> Dict[str, Any]:
        """获取个股K线"""

        db_path = self._find_db()
        if not db_path:
            return {"error": "K线数据库未找到", "code": code, "data": []}

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            rows = conn.execute(
                "SELECT date, open, high, low, close, volume "
                "FROM kline_daily WHERE code=? ORDER BY date DESC LIMIT ?",
                (code, days)
            ).fetchall()
            conn.close()

            if not rows:
                return {"code": code, "data": [], "count": 0,
                        "message": f"未找到{code}的K线数据"}

            data = [
                {
                    "date": r["date"],
                    "open": round(float(r["open"]), 2),
                    "high": round(float(r["high"]), 2),
                    "low": round(float(r["low"]), 2),
                    "close": round(float(r["close"]), 2),
                    "volume": int(r["volume"]),
                }
                for r in reversed(rows)
            ]

            # 计算简单统计
            closes = [d["close"] for d in data]
            latest = data[-1]["close"] if data else 0
            ma5 = sum(closes[-5:]) / min(5, len(closes)) if closes else 0

            return {
                "source": "kline_cache",
                "code": code,
                "count": len(data),
                "latest_date": data[-1]["date"] if data else None,
                "latest_close": latest,
                "ma5": round(ma5, 2),
                "data": data,
            }
        except Exception as e:
            logger.error(f"[Kline] 查询失败: {e}")
            return {"error": str(e), "code": code, "data": []}

    def _find_db(self) -> Path:
        for p in self.DB_PATHS:
            if p.exists():
                return p
        return None


class KlineBriefSkill(BaseSkill):
    """K线摘要 — Research Agent用, 快速了解大盘走势"""

    name = "get_kline_brief"
    description = "获取指数或个股近期走势摘要, 包含趋势判断和关键点位。用于快速了解技术面。"
    schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "指数代码(000001=上证) 或 个股代码, 默认000001",
            },
        },
        "required": [],
    }

    def execute(self, code: str = "000001", **kwargs) -> Dict[str, Any]:
        """获取K线摘要"""
        kline = KlineSkill()
        result = kline.execute(code=code, days=30)

        if result.get("error"):
            return result

        data = result.get("data", [])
        if len(data) < 5:
            return {"code": code, "message": "数据不足", **result}

        closes = [d["close"] for d in data]

        # 趋势判断
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else ma5
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else ma5

        if ma5 > ma10 > ma20:
            trend = "上升趋势"
        elif ma5 < ma10 < ma20:
            trend = "下降趋势"
        else:
            trend = "震荡"

        # 涨跌统计
        chg_5d = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else 0

        return {
            "code": code,
            "trend": trend,
            "latest": closes[-1] if closes else 0,
            "ma5": round(ma5, 2),
            "ma20": round(ma20, 2) if len(closes) >= 20 else None,
            "change_5d_pct": round(chg_5d, 2),
            "data_count": len(data),
        }


# 注册
kline_skill = KlineSkill()
kline_brief_skill = KlineBriefSkill()
skill_registry.register(kline_skill)
skill_registry.register(kline_brief_skill)
