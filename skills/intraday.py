"""
Intraday Skills — 盘中实时数据 (东方财富Web API)
盘中概念排名 + 行业排名 + 个股扫描 + "昨日指标+今日价格"组合信号
"""
from typing import Dict, Any, List
import requests
from datetime import datetime
from loguru import logger

from skills.base import BaseSkill, skill_registry


# 东方财富实时行情API
EM_BASE = "http://push2.eastmoney.com/api/qt/clist/get"
EM_HEADERS = {"Referer": "https://quote.eastmoney.com/"}


def _fetch_em(sector: str, sort_by: str = "f3", page_size: int = 50) -> List[Dict]:
    """通用东方财富数据拉取 (3次重试)"""
    for attempt in range(3):
        try:
            resp = requests.get(EM_BASE, params={
                "pn": "1", "pz": str(page_size), "po": "1", "np": "1",
                "fltt": "2", "invt": "2", "fid": sort_by, "fs": sector,
                "fields": "f2,f3,f4,f12,f14,f15,f16,f17,f5,f6,f10",
            }, headers=EM_HEADERS, timeout=10)
            data = resp.json()
            if data.get("data") and data["data"].get("diff"):
                return data["data"]["diff"]
        except Exception as e:
            if attempt < 2:
                __import__('time').sleep(1)
            else:
                logger.warning(f"[EM] {sector[:20]}... 3次重试均失败: {e}")
    return []


def _fetch_sina_quotes(codes: List[str]) -> Dict[str, Dict]:
    """新浪实时行情 fallback"""
    if not codes:
        return {}
    try:
        batch_size = 50
        results = {}
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i+batch_size]
            sina_codes = [f'{"sh" if c.startswith(("6","9")) else "sz"}{c}' for c in batch]
            url = f'https://hq.sinajs.cn/list={",".join(sina_codes)}'
            resp = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)
            resp.encoding = "gbk"
            for line in resp.text.strip().split("\n"):
                if '="' not in line: continue
                try:
                    parts = line.split('"')[1].split(",")
                    if len(parts) > 9:
                        code = line.split("=")[0][-6:]
                        results[code] = {
                            "price": float(parts[3]),
                            "change_pct": round((float(parts[3])/float(parts[2])-1)*100, 2),
                            "volume_hand": int(float(parts[8])),
                        }
                except (ValueError, IndexError):
                    continue
        return results
    except Exception as e:
        logger.warning(f"[Sina] fallback: {e}")
        return {}


# ============================================================
# Skill 1: 盘中概念板块排名
# ============================================================
class IntradayConceptSkill(BaseSkill):
    name = "get_intraday_concepts"
    description = "获取盘中实时概念板块涨幅排名(东方财富), 数据秒级更新。用于识别当前真正的热点板块。"
    schema = {
        "type": "object",
        "properties": {
            "top_n": {"type": "integer", "description": "返回前N个, 默认20"},
        },
        "required": [],
    }

    def execute(self, top_n: int = 20, **kwargs) -> Dict[str, Any]:
        items = _fetch_em("m:90+t:3", page_size=top_n)
        concepts = []
        for item in items:
            concepts.append({
                "name": item.get("f14", ""),
                "code": item.get("f12", ""),
                "change_pct": round(item.get("f3", 0), 2),
                "price": item.get("f2", 0),
            })
        return {
            "source": "eastmoney_realtime",
            "timestamp": datetime.now().isoformat(),
            "count": len(concepts),
            "concepts": concepts,
        }


# ============================================================
# Skill 2: 盘中行业板块排名
# ============================================================
class IntradayIndustrySkill(BaseSkill):
    name = "get_intraday_industries"
    description = "获取盘中实时行业板块涨幅排名(东方财富), 用于判断行业轮动方向。"
    schema = {
        "type": "object",
        "properties": {
            "top_n": {"type": "integer", "description": "返回前N个, 默认15"},
        },
        "required": [],
    }

    def execute(self, top_n: int = 15, **kwargs) -> Dict[str, Any]:
        items = _fetch_em("m:90+t:2", page_size=top_n)
        industries = []
        for item in items:
            industries.append({
                "name": item.get("f14", ""),
                "code": item.get("f12", ""),
                "change_pct": round(item.get("f3", 0), 2),
            })
        return {
            "source": "eastmoney_realtime",
            "timestamp": datetime.now().isoformat(),
            "count": len(industries),
            "industries": industries,
        }


# ============================================================
# Skill 3: 盘中实时扫描 — 昨日指标 + 今日盘中价 = 实时信号
# ============================================================
class IntradayScanSkill(BaseSkill):
    name = "scan_intraday"
    description = "盘中实时扫描: 结合昨日技术指标(MA/MACD/RSI)+今日实时价格/涨跌幅/量比, 发现盘中交易机会。"
    schema = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["trend", "reversal", "volume_breakout", "all"],
                "description": "扫描模式",
            },
            "top_n": {"type": "integer", "description": "返回前N个, 默认10"},
        },
        "required": [],
    }

    def execute(self, mode: str = "all", top_n: int = 10, **kwargs) -> Dict[str, Any]:
        """盘中扫描 = 快照表指标 + 东方财富实时价格"""
        try:
            import sqlite3
            from pathlib import Path

            # 1. 从快照表加载昨日指标
            db = self._find_db()
            if not db:
                return {"error": "快照表未找到", "signals": []}

            conn = sqlite3.connect(str(db))
            df = __import__('pandas').read_sql_query(
                "SELECT * FROM daily_indicator_snapshot "
                "WHERE ma20 IS NOT NULL AND rsi14 IS NOT NULL "
                "AND name NOT LIKE '%ST%' AND name NOT LIKE '%退%'",
                conn
            )
            conn.close()

            if len(df) == 0:
                return {"error": "快照表为空"}

            # 2. 从东方财富拉取今日实时行情, 失败则用新浪fallback
            em_items = _fetch_em("m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                                sort_by="f3", page_size=200)
            live = {}
            if em_items:
                for item in em_items:
                    code = item.get("f12", "")
                    live[code] = {
                        "price": item.get("f2", 0),
                        "change_pct": item.get("f3", 0),
                        "volume_hand": item.get("f5", 0),
                        "turnover": item.get("f6", 0),
                        "high": item.get("f15", 0),
                        "low": item.get("f16", 0),
                        "volume_ratio": item.get("f10", 0),
                    }
            else:
                # Fallback: 新浪API — 先从快照表筛选候选股, 再拉实时价
                # 过滤有技术面潜力的候选 (MA多头/RSI超卖/量比)
                df['score_filter'] = 0
                if 'ma5' in df.columns and 'ma20' in df.columns and 'ma60' in df.columns:
                    ma_ok = (df['ma5'] > df['ma20']) & (df['ma20'] > df['ma60'])
                    df.loc[ma_ok, 'score_filter'] += 3
                if 'rsi14' in df.columns:
                    df.loc[df['rsi14'] < 35, 'score_filter'] += 2
                if 'vol_ratio_5' in df.columns:
                    df.loc[df['vol_ratio_5'] > 1.3, 'score_filter'] += 1
                if 'drawdown_20d' in df.columns:
                    df.loc[df['drawdown_20d'] < -10, 'score_filter'] += 1

                # 取评分最高的800只候选
                candidates = df[df['score_filter'] >= 2].nlargest(800, 'score_filter')
                if len(candidates) < 100:
                    candidates = df.nlargest(300, 'score_filter')  # 兜底

                codes = [str(row["code"]).zfill(6) for _, row in candidates.iterrows()]
                live = _fetch_sina_quotes(codes)
                for code in live:
                    live[code].setdefault("volume_ratio", 1.0)
                    live[code].setdefault("high", live[code]["price"])
                    live[code].setdefault("low", live[code]["price"])
                logger.info(f"[IntradayScan] 东方财富失败, 新浪fallback: 候选{candidates.shape[0]}只→行情{len(live)}只")

            # 3. 合并: 昨日指标 + 今日实时价格
            signals = []
            for _, row in df.iterrows():
                code = str(row["code"]).zfill(6)
                if code not in live:
                    continue

                l = live[code]
                price = l["price"]
                chg = l["change_pct"]
                vol_ratio = l.get("volume_ratio", 1)
                pre_close = row.get("pre_close", 0)
                ma5 = row.get("ma5")
                ma20 = row.get("ma20")
                ma60 = row.get("ma60")
                rsi14 = row.get("rsi14")

                score = 0
                reasons = []

                # 趋势模式: 均线多头 + 今日放量突破
                if mode in ("trend", "all"):
                    if ma5 and ma20 and ma60 and ma5 > ma20 > ma60:
                        if price > ma5 and vol_ratio > 1.5:
                            score = max(score, 0.7)
                            reasons.append("均线多头+今日放量")

                # 反转模式: RSI超卖 + 今日反弹
                if mode in ("reversal", "all"):
                    if rsi14 and rsi14 < 30 and chg > 1:
                        score = max(score, 0.65)
                        reasons.append(f"RSI={rsi14:.0f}超卖+今日反弹{chg:+.1f}%")

                # 放量突破模式
                if mode in ("volume_breakout", "all"):
                    if vol_ratio > 2.5 and chg > 2:
                        score = max(score, 0.6)
                        reasons.append(f"量比{vol_ratio:.1f}+涨{chg:+.1f}%")

                if score > 0.5:
                # 安全过滤
                name = str(row.get('name', ''))
                if 'ST' in name.upper() or '退' in name:
                    continue
                signals.append({
                        "code": code,
                        "name": row.get("name", ""),
                        "price": price,
                        "change_pct": chg,
                        "volume_ratio": vol_ratio,
                        "ma5": ma5, "ma20": ma20, "rsi14": rsi14,
                        "score": round(score, 2),
                        "reasons": reasons,
                    })

            # 按分数排序
            signals.sort(key=lambda x: x["score"], reverse=True)
            signals = signals[:top_n]

            return {
                "source": "snapshot+live",
                "timestamp": datetime.now().isoformat(),
                "stocks_with_live_data": len(live),
                "signals_count": len(signals),
                "signals": signals,
            }

        except Exception as e:
            return {"error": str(e), "signals": []}

    def _find_db(self):
        from pathlib import Path
        for p in [Path("/mnt/d/AI/auction-stock-picker/data/cache/kline_cache.db"),
                  Path("data/cache/kline_cache.db")]:
            if p.exists():
                return p
        return None


# 注册
skill_registry.register(IntradayConceptSkill())
skill_registry.register(IntradayIndustrySkill())
skill_registry.register(IntradayScanSkill())
