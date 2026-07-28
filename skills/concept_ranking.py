"""
ConceptRanking Skill — 概念板块涨幅排名
数据源: Tushare ths_daily (同花顺概念板块日行情)
返回当日或最近交易日的概念板块涨幅TOP N
"""
from typing import Dict, Any
from datetime import date, timedelta
from loguru import logger

from skills.base import BaseSkill, skill_registry


class ConceptRankingSkill(BaseSkill):
    name = "get_concept_ranking"
    description = "获取A股概念板块涨幅排名(同花顺1725个概念), 返回TOP N的热门概念及涨跌幅。用于识别当日热点板块和资金流向。"
    schema = {
        "type": "object",
        "properties": {
            "top_n": {
                "type": "integer",
                "description": "返回前N个概念, 默认20",
            },
        },
        "required": [],
    }

    def execute(self, top_n: int = 20, **kwargs) -> Dict[str, Any]:
        """获取概念板块排名"""

        try:
            import os
            from dotenv import load_dotenv
            load_dotenv()
            import tushare as ts

            token = os.getenv('TUSHARE_TOKEN', '')
            if not token:
                return {"error": "TUSHARE_TOKEN 未配置", "concepts": []}

            ts.set_token(token)
            pro = ts.pro_api()

            # 获取最近交易日 (Tushare EOD数据, 当日盘中可能还没出)
            trade_dates = self._get_recent_trade_dates(pro)
            if not trade_dates:
                return {"error": "无法获取交易日", "concepts": []}

            # 尝试获取数据
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
                return {"error": "无概念板块数据", "concepts": []}

            # 获取概念名称映射
            idx = pro.ths_index()
            if idx is None:
                return {"error": "无法获取概念名称", "concepts": []}

            code2name = dict(zip(idx['ts_code'], idx['name']))
            df['name'] = df['ts_code'].map(code2name)
            df = df.dropna(subset=['name'])

            # 按涨幅排序 — 过滤异常值
            df['pct_change'] = df['pct_change'].astype(float)
            df_valid = df[(df['pct_change'] > -20) & (df['pct_change'] < 20)]
            # 如果有效数据太少(<100条), 说明数据源异常, 回退到前一天
            if len(df_valid) < 100:
                logger.warning(f"[ConceptRanking] {used_date} 有效数据仅{len(df_valid)}条, 数据可能异常")
                # 尝试前一天
                prev_date = (date.today() - timedelta(days=2)).strftime('%Y%m%d')
                try:
                    df = pro.ths_daily(trade_date=prev_date)
                    if df is not None and len(df) > 0:
                        df['name'] = df['ts_code'].map(code2name)
                        df = df.dropna(subset=['name'])
                        df['pct_change'] = df['pct_change'].astype(float)
                        df_valid = df[(df['pct_change'] > -20) & (df['pct_change'] < 20)]
                        used_date = prev_date
                        logger.info(f"[ConceptRanking] 回退到 {prev_date}: {len(df_valid)} 条")
                except Exception:
                    pass
            top = df_valid.sort_values('pct_change', ascending=False).head(top_n)

            concepts = []
            for _, row in top.iterrows():
                concepts.append({
                    "name": row['name'],
                    "code": row['ts_code'],
                    "change_pct": round(float(row['pct_change']), 2),
                    "volume": int(row.get('vol', 0)),
                })

            # 计算板块统计
            avg_change = df['pct_change'].mean()
            up_count = (df['pct_change'] > 0).sum()
            down_count = (df['pct_change'] < 0).sum()

            return {
                "source": "tushare_ths",
                "date": used_date,
                "total": len(df),
                "up_count": int(up_count),
                "down_count": int(down_count),
                "avg_change": round(float(avg_change), 2),
                "concepts": concepts,
            }

        except Exception as e:
            logger.error(f"[ConceptRanking] 失败: {e}")
            return {"error": str(e), "concepts": []}

    def _get_recent_trade_dates(self, pro) -> list:
        """获取最近几个交易日日期"""
        today = date.today()
        dates = []

        # 往前找最多5天
        for offset in range(5):
            d = today - timedelta(days=offset)
            d_str = d.strftime('%Y%m%d')

            try:
                cal = pro.trade_cal(exchange='SSE', start_date=d_str, end_date=d_str)
                if cal is not None and len(cal) > 0 and cal.iloc[0].get('is_open', 0) == 1:
                    dates.append(d_str)
            except Exception:
                # 如果API调不通, 直接按日期尝试
                if d.weekday() < 5:
                    dates.append(d_str)

        return dates


# 注册
concept_ranking_skill = ConceptRankingSkill()
skill_registry.register(concept_ranking_skill)
