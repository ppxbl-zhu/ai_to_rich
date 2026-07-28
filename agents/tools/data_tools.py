"""
Agent Data Tools — 数据查询工具集
Agent可调用这些函数查询行情、K线、持仓等数据
"""
from typing import Dict, List, Optional, Any
from datetime import date, datetime, timedelta
import json
import sqlite3
from pathlib import Path
from loguru import logger


class DataTools:
    """
    数据查询工具 — 供LLM Agent调用
    每个方法返回结构化数据, 包含错误处理
    """

    def __init__(self):
        self._kline_paths = [
            Path("/mnt/d/AI/auction-stock-picker/data/kline_cache.db"),
            Path("data/cache/kline_cache.db"),
        ]

    # === K线数据 ===

    def get_kline(self, code: str, days: int = 60) -> Dict[str, Any]:
        """
        获取个股K线数据
        Args:
            code: 股票代码 (6位)
            days: 最近N个交易日
        Returns:
            {"code":..., "data": [{"date":..., "open":..., ...}, ...], "count": int}
        """
        try:
            db_path = self._find_kline_db()
            if not db_path:
                return {"error": "K线数据库未找到", "code": code, "data": []}

            conn = sqlite3.connect(str(db_path))
            rows = conn.execute(
                "SELECT date, open, high, low, close, volume FROM kline_daily "
                "WHERE code=? ORDER BY date DESC LIMIT ?",
                (code, days)
            ).fetchall()
            conn.close()

            data = [
                {
                    "date": r[0],
                    "open": r[1],
                    "high": r[2],
                    "low": r[3],
                    "close": r[4],
                    "volume": r[5],
                }
                for r in reversed(rows)
            ]
            return {"code": code, "data": data, "count": len(data)}
        except Exception as e:
            return {"error": str(e), "code": code, "data": []}

    def get_market_index(self) -> Dict[str, Any]:
        """
        获取大盘指数行情
        Returns:
            {"上证指数": {...}, "深证成指": {...}, "创业板指": {...}}
        """
        try:
            import requests
            # 新浪指数行情API (格式不同于股票)
            # 指数格式: [0]=名称 [1]=当前点位 [2]=涨跌额 [3]=涨跌幅% [4]=成交量 [5]=成交额
            indices = {
                "上证指数": "s_sh000001",
                "深证成指": "s_sz399001",
                "创业板指": "s_sz399006",
            }

            codes_str = ",".join(indices.values())
            url = f"https://hq.sinajs.cn/list={codes_str}"
            headers = {"Referer": "https://finance.sina.com.cn"}
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = "gbk"

            result = {}
            for name, sina_code in indices.items():
                for line in resp.text.strip().split("\n"):
                    if sina_code in line:
                        parts = line.split('"')[1].split(",")
                        if len(parts) >= 4:
                            # 指数格式: parts[1]=当前点位, parts[2]=涨跌额, parts[3]=涨跌幅%
                            result[name] = {
                                "name": parts[0],
                                "current": float(parts[1]),
                                "change_amount": float(parts[2]),
                                "change": float(parts[3]),
                                "volume": float(parts[4]) if len(parts) > 4 else 0,
                            }

            return result or {"error": "获取大盘数据失败"}
        except Exception as e:
            logger.warning(f"[DataTools] 大盘数据获取失败: {e}")
            return {"error": str(e)}

    def get_realtime_quote(self, codes: List[str]) -> Dict[str, Dict]:
        """
        获取实时行情
        Args:
            codes: 股票代码列表
        Returns:
            {code: {"name":..., "price":..., "change":..., "volume":...}}
        """
        if not codes:
            return {}

        try:
            import requests
            sina_codes = []
            for c in codes:
                prefix = "sh" if c.startswith(("6", "9")) else "sz"
                sina_codes.append(f"{prefix}{c}")

            url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
            headers = {"Referer": "https://finance.sina.com.cn"}
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = "gbk"

            result = {}
            for line in resp.text.strip().split("\n"):
                if '="' not in line:
                    continue
                try:
                    code_part = line.split("=")[0].split("_")[-1]
                    orig_code = code_part[2:]  # 去掉sh/sz前缀
                    parts = line.split('"')[1].split(",")
                    if len(parts) > 9:
                        result[orig_code] = {
                            "name": parts[0],
                            "open": float(parts[1]),
                            "price": float(parts[3]),
                            "high": float(parts[4]),
                            "low": float(parts[5]),
                            "volume": int(float(parts[8])),
                            "change_pct": round((float(parts[3]) / float(parts[2]) - 1) * 100, 2),
                        }
                except (ValueError, IndexError):
                    continue

            return result
        except Exception as e:
            logger.warning(f"[DataTools] 实时行情获取失败: {e}")
            return {"error": str(e)}

    # === 新闻数据 ===

    def get_news(self, limit: int = 30) -> List[Dict]:
        """获取最新财经新闻"""
        news = []
        try:
            import akshare as ak

            # 东方财富新闻
            df = ak.stock_news_em()
            if df is not None and len(df) > 0:
                for _, row in df.head(limit).iterrows():
                    news.append({
                        "title": str(row.get("标题", "")),
                        "content": str(row.get("内容", "")),
                        "source": "eastmoney",
                        "time": str(row.get("发布时间", "")),
                    })
        except Exception as e:
            logger.warning(f"[DataTools] 新闻获取失败: {e}")

        return news

    # === 概念/板块数据 ===

    def get_concept_stocks(self, concept_name: str) -> List[Dict]:
        """获取概念板块成分股"""
        try:
            cache_path = Path("/mnt/d/AI/auction-stock-picker/data/ak_concept_members.json")
            if cache_path.exists():
                with open(cache_path) as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if concept_name in k or k in concept_name:
                            return v[:20]
        except Exception as e:
            logger.warning(f"[DataTools] 概念数据获取失败: {e}")
        return []

    def get_concept_ranking(self, top_n: int = 20) -> Dict[str, Any]:
        """
        获取实时概念板块排名 (Tushare)
        返回当日(或最近交易日)概念涨幅排名
        """
        try:
            import os
            from dotenv import load_dotenv
            load_dotenv()
            token = os.getenv('TUSHARE_TOKEN', '')
            if not token:
                return {"error": "TUSHARE_TOKEN 未配置", "concepts": []}

            import tushare as ts
            ts.set_token(token)
            pro = ts.pro_api()

            # 获取最近交易日
            today = date.today().strftime('%Y%m%d')
            cal = pro.trade_cal(exchange='SSE', start_date=today, end_date=today)
            is_trade_day = cal is not None and len(cal) > 0 and cal.iloc[0].get('is_open', 0) == 1

            # 尝试今天, 如果没数据就用最近的
            trade_dates = []
            if is_trade_day:
                trade_dates.append(today)
            # 往前找最近交易日
            for d_offset in range(1, 5):
                d = (date.today() - __import__('datetime').timedelta(days=d_offset)).strftime('%Y%m%d')
                trade_dates.append(d)

            df = None
            used_date = None
            for td in trade_dates:
                try:
                    df = pro.ths_daily(trade_date=td)
                    if df is not None and len(df) > 0:
                        used_date = td
                        break
                except Exception:
                    continue

            if df is None or len(df) == 0:
                return {"error": "无法获取概念板块数据", "concepts": []}

            # 获取概念名称
            idx = pro.ths_index()
            code2name = dict(zip(idx['ts_code'], idx['name'])) if idx is not None else {}

            df['name'] = df['ts_code'].map(code2name)
            df = df.dropna(subset=['name'])
            df['pct_change'] = df['pct_change'].astype(float)

            top = df.sort_values('pct_change', ascending=False).head(top_n)
            concepts = []
            for _, row in top.iterrows():
                concepts.append({
                    "name": row['name'],
                    "code": row['ts_code'],
                    "change_pct": round(float(row['pct_change']), 2),
                    "volume": float(row.get('vol', 0)),
                })

            return {
                "date": used_date,
                "total_concepts": len(df),
                "concepts": concepts,
            }

        except Exception as e:
            logger.warning(f"[DataTools] 概念排名获取失败: {e}")
            return {"error": str(e), "concepts": []}

    def get_industry_ranking(self, top_n: int = 10) -> Dict[str, Any]:
        """
        获取行业板块排名 (申万一级行业)
        """
        try:
            import akshare as ak
            df = ak.stock_board_industry_name_em()
            if df is not None and len(df) > 0:
                top = df.sort_values('涨跌幅', ascending=False).head(top_n)
                return {
                    "industries": [
                        {
                            "name": row['板块名称'],
                            "change_pct": float(row['涨跌幅']),
                        }
                        for _, row in top.iterrows()
                    ]
                }
        except Exception as e:
            logger.debug(f"[DataTools] 行业排名(AKShare): {e}")

        # Fallback: Tushare
        try:
            import os
            from dotenv import load_dotenv
            load_dotenv()
            import tushare as ts
            ts.set_token(os.getenv('TUSHARE_TOKEN', ''))
            pro = ts.pro_api()
            # 申万一级行业指数
            sw_codes = {
                '801780.SI': '银行', '801790.SI': '非银金融', '801120.SI': '食品饮料',
                '801150.SI': '医药生物', '801080.SI': '电子', '801750.SI': '计算机',
                '801760.SI': '传媒', '801880.SI': '汽车', '801730.SI': '电力设备',
                '801050.SI': '有色金属', '801010.SI': '农林牧渔', '801180.SI': '房地产',
            }
            today = date.today().strftime('%Y%m%d')
            results = []
            for code, name in sw_codes.items():
                try:
                    di = pro.index_daily(ts_code=code, start_date=today, end_date=today)
                    if di is not None and len(di) > 0:
                        results.append({
                            "name": name, "change_pct": float(di.iloc[0]['pct_chg']),
                        })
                except Exception:
                    pass
            if results:
                results.sort(key=lambda x: x['change_pct'], reverse=True)
                return {"industries": results[:top_n]}
        except Exception as e:
            logger.debug(f"[DataTools] 行业排名(Tushare): {e}")

        return {"error": "无法获取行业排名", "industries": []}

    # === 持仓/交易数据 ===

    def get_positions(self) -> List[Dict]:
        """获取当前模拟持仓"""
        try:
            from data.storage.sqlite_storage import storage
            today = date.today().strftime("%Y-%m-%d")
            conn = storage.get_conn()
            rows = conn.execute(
                "SELECT * FROM position_snapshots WHERE date=?",
                (today,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            return []

    def get_trade_history(self, days: int = 30) -> List[Dict]:
        """获取历史交易记录"""
        try:
            from data.storage.sqlite_storage import storage
            conn = storage.get_conn()
            rows = conn.execute(
                "SELECT * FROM trades WHERE entry_date >= date('now', ?) ORDER BY entry_date DESC",
                (f"-{days} days",)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            return []

    # === 内部辅助 ===

    def _find_kline_db(self) -> Optional[Path]:
        """查找K线数据库文件"""
        for p in self._kline_paths:
            if p.exists():
                return p
        return None


# 工具函数格式 (供LLM function calling使用)
DATA_TOOLS_SCHEMA = [
    {
        "name": "get_kline",
        "description": "获取个股K线数据，返回最近N个交易日的OHLCV",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码，6位数字"},
                "days": {"type": "integer", "description": "最近N个交易日，默认60"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "get_market_index",
        "description": "获取大盘指数行情(上证/深证/创业板)",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_realtime_quote",
        "description": "获取股票实时行情(价格/涨跌幅/成交量)",
        "parameters": {
            "type": "object",
            "properties": {
                "codes": {"type": "array", "items": {"type": "string"}, "description": "股票代码列表"},
            },
            "required": ["codes"],
        },
    },
    {
        "name": "get_news",
        "description": "获取最新财经新闻",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "获取条数，默认30"},
            },
        },
    },
    {
        "name": "get_concept_stocks",
        "description": "获取概念板块成分股",
        "parameters": {
            "type": "object",
            "properties": {
                "concept_name": {"type": "string", "description": "概念板块名称"},
            },
            "required": ["concept_name"],
        },
    },
    {
        "name": "get_positions",
        "description": "获取当前模拟持仓",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_trade_history",
        "description": "获取历史交易记录",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "最近N天，默认30"},
            },
        },
    },
]

# 全局实例
data_tools = DataTools()
