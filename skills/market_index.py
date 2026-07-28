"""
MarketIndex Skill — 大盘指数实时行情
数据源: 新浪API (实时) → Tushare (fallback)
"""
from typing import Dict, Any
import requests
from loguru import logger

from skills.base import BaseSkill, skill_registry


class MarketIndexSkill(BaseSkill):
    name = "get_market_index"
    description = "获取A股三大指数实时行情(上证/深证/创业板), 返回当前点位和涨跌幅。用于判断大盘整体走势。"
    schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    # 新浪指数代码
    INDEX_MAP = {
        "上证指数": "s_sh000001",
        "深证成指": "s_sz399001",
        "创业板指": "s_sz399006",
    }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """获取三大指数实时行情"""

        # 主数据源: 新浪API
        result = self._fetch_sina()
        if result and len(result) >= 2:
            return {"source": "sina", "data": result, "timestamp": __import__('datetime').datetime.now().isoformat()}

        # Fallback: Tushare
        logger.info("[MarketIndex] 新浪失败, 尝试Tushare...")
        result = self._fetch_tushare()
        if result:
            return {"source": "tushare", "data": result}

        return {"error": "所有数据源均失败", "data": {}}

    def _fetch_sina(self) -> Dict[str, Dict]:
        """新浪API (指数格式: [0]=名 [1]=点位 [2]=涨跌额 [3]=涨跌幅%)"""
        try:
            codes = ",".join(self.INDEX_MAP.values())
            url = f"https://hq.sinajs.cn/list={codes}"
            headers = {"Referer": "https://finance.sina.com.cn"}
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = "gbk"

            result = {}
            for name, sina_code in self.INDEX_MAP.items():
                for line in resp.text.strip().split("\n"):
                    if sina_code in line:
                        parts = line.split('"')[1].split(",")
                        if len(parts) >= 4:
                            result[name] = {
                                "name": parts[0],
                                "current": round(float(parts[1]), 2),
                                "change_amount": round(float(parts[2]), 2),
                                "change_pct": round(float(parts[3]), 2),
                            }
            return result
        except Exception as e:
            logger.warning(f"[MarketIndex] 新浪失败: {e}")
            return {}

    def _fetch_tushare(self) -> Dict[str, Dict]:
        """Tushare指数数据"""
        try:
            import os
            from dotenv import load_dotenv
            load_dotenv()
            import tushare as ts
            ts.set_token(os.getenv('TUSHARE_TOKEN', ''))
            pro = ts.pro_api()

            today = __import__('datetime').date.today().strftime('%Y%m%d')
            index_codes = {
                "上证指数": "000001.SH",
                "深证成指": "399001.SZ",
                "创业板指": "399006.SZ",
            }

            result = {}
            for name, code in index_codes.items():
                df = pro.index_daily(ts_code=code, start_date=today, end_date=today)
                if df is not None and len(df) > 0:
                    row = df.iloc[0]
                    result[name] = {
                        "name": name,
                        "current": round(float(row['close']), 2),
                        "change_pct": round(float(row['pct_chg']), 2),
                    }
            return result
        except Exception as e:
            logger.warning(f"[MarketIndex] Tushare失败: {e}")
            return {}


# 注册
market_index_skill = MarketIndexSkill()
skill_registry.register(market_index_skill)
