"""
IndustryRanking Skill — 行业板块涨幅排名
数据源: AKShare 东方财富 (盘中实时) → Tushare 申万指数 (fallback)
"""
from typing import Dict, Any
from loguru import logger

from skills.base import BaseSkill, skill_registry


class IndustryRankingSkill(BaseSkill):
    name = "get_industry_ranking"
    description = "获取A股行业板块涨幅排名, 返回当日行业轮动情况。用于判断资金在行业间的流向。"
    schema = {
        "type": "object",
        "properties": {
            "top_n": {"type": "integer", "description": "返回前N个行业, 默认10"},
        },
        "required": [],
    }

    def execute(self, top_n: int = 10, **kwargs) -> Dict[str, Any]:
        """获取行业排名"""

        # 主数据源: AKShare 东方财富 (盘中实时)
        result = self._fetch_akshare(top_n)
        if result:
            return {"source": "akshare_em", **result}

        # Fallback: Tushare 申万指数
        logger.info("[IndustryRanking] AKShare失败, 尝试Tushare...")
        result = self._fetch_tushare_sw(top_n)
        if result:
            return {"source": "tushare_sw", **result}

        return {"error": "所有数据源均失败", "industries": []}

    def _fetch_akshare(self, top_n: int) -> Dict:
        """AKShare 东方财富行业板块"""
        try:
            import akshare as ak
            df = ak.stock_board_industry_name_em()
            if df is None or len(df) == 0:
                return {}

            top = df.sort_values('涨跌幅', ascending=False).head(top_n)

            industries = []
            for _, row in top.iterrows():
                industries.append({
                    "name": str(row['板块名称']),
                    "change_pct": round(float(row['涨跌幅']), 2),
                    "lead_stock": str(row.get('领涨股票', '')),
                })

            # 全市场统计
            avg_chg = df['涨跌幅'].astype(float).mean()
            up_count = (df['涨跌幅'].astype(float) > 0).sum()

            return {
                "industries": industries,
                "total": len(df),
                "up_count": int(up_count),
                "avg_change": round(float(avg_chg), 2),
            }
        except Exception as e:
            logger.debug(f"[IndustryRanking] AKShare: {e}")
            return {}

    def _fetch_tushare_sw(self, top_n: int) -> Dict:
        """Tushare 申万一级行业指数"""
        try:
            import os
            from dotenv import load_dotenv
            load_dotenv()
            import tushare as ts
            ts.set_token(os.getenv('TUSHARE_TOKEN', ''))
            pro = ts.pro_api()

            # 申万一级行业代码
            sw_codes = {
                '801780.SI': '银行', '801790.SI': '非银金融', '801120.SI': '食品饮料',
                '801150.SI': '医药生物', '801080.SI': '电子', '801750.SI': '计算机',
                '801760.SI': '传媒', '801880.SI': '汽车', '801730.SI': '电力设备',
                '801050.SI': '有色金属', '801010.SI': '农林牧渔', '801180.SI': '房地产',
                '801030.SI': '基础化工', '801140.SI': '轻工制造', '801710.SI': '建筑材料',
                '801720.SI': '建筑装饰', '801740.SI': '国防军工', '801770.SI': '通信',
                '801890.SI': '机械设备', '801960.SI': '石油石化', '801970.SI': '煤炭',
                '801980.SI': '公用事业', '801200.SI': '商贸零售', '801210.SI': '社会服务',
                '801230.SI': '综合',
            }

            today = __import__('datetime').date.today().strftime('%Y%m%d')
            results = []
            for code, name in sw_codes.items():
                try:
                    di = pro.index_daily(ts_code=code, start_date=today, end_date=today)
                    if di is not None and len(di) > 0:
                        results.append({
                            "name": name,
                            "change_pct": round(float(di.iloc[0]['pct_chg']), 2),
                        })
                except Exception:
                    pass

            if results:
                results.sort(key=lambda x: x['change_pct'], reverse=True)
                return {
                    "industries": results[:top_n],
                    "total": len(sw_codes),
                }
        except Exception as e:
            logger.debug(f"[IndustryRanking] Tushare: {e}")

        return {}


# 注册
industry_ranking_skill = IndustryRankingSkill()
skill_registry.register(industry_ranking_skill)
