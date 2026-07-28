"""
Trend Strategy — 趋势跟踪策略
基于均线多头排列 + 放量突破 + MACD金叉的中线选股 (3-10天)
"""
import sys
from pathlib import Path
from typing import List, Optional, Any
import numpy as np
import pandas as pd
from loguru import logger

from strategies.base_strategy import BaseStrategy, StrategySignal

# 复用现有系统数据层
EXISTING_SYSTEM = Path("/mnt/d/AI/auction-stock-picker")
if str(EXISTING_SYSTEM) not in sys.path:
    sys.path.append(str(EXISTING_SYSTEM))


class TrendScanner:
    """趋势扫描器 — 识别均线突破+放量形态"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.ma_short = self.config.get("ma_short", 5)
        self.ma_mid = self.config.get("ma_mid", 20)
        self.ma_long = self.config.get("ma_long", 60)
        self.min_volume_ratio = self.config.get("min_volume_ratio", 1.5)
        self.min_market_cap = self.config.get("min_market_cap", 20)
        self.max_market_cap = self.config.get("max_market_cap", 500)

    def scan(self, kline_data: pd.DataFrame) -> pd.DataFrame:
        """
        扫描趋势信号
        Args:
            kline_data: 日K线数据 (需包含: code, close, volume, 以及计算好的MA指标)
        Returns:
            符合趋势条件的股票DataFrame
        """
        if kline_data is None or len(kline_data) == 0:
            return pd.DataFrame()

        df = kline_data.copy()

        # 筛选条件:
        # 1. 均线多头排列: MA5 > MA20 > MA60
        ma_short_col = f"ma{self.ma_short}"
        ma_mid_col = f"ma{self.ma_mid}"
        ma_long_col = f"ma{self.ma_long}"

        has_ma = all(c in df.columns for c in [ma_short_col, ma_mid_col, ma_long_col])
        if has_ma:
            df["ma_aligned"] = (
                (df[ma_short_col] > df[ma_mid_col]) &
                (df[ma_mid_col] > df[ma_long_col])
            )
        else:
            df["ma_aligned"] = True  # 无MA数据时不过滤

        # 2. 价格在MA5上方 (强势)
        if ma_short_col in df.columns and "close" in df.columns:
            df["above_ma5"] = df["close"] > df[ma_short_col]
        else:
            df["above_ma5"] = True

        # 3. 放量: 今日成交量 > N日均量 * ratio
        vol_ma_col = f"vol_ma{self.ma_short}"
        if vol_ma_col in df.columns and "volume" in df.columns:
            df["volume_breakout"] = df["volume"] > df[vol_ma_col] * self.min_volume_ratio
        else:
            df["volume_breakout"] = True

        # 4. MACD金叉或处于零轴上方
        if "macd_dif" in df.columns and "macd_dea" in df.columns:
            df["macd_bullish"] = (
                (df["macd_dif"] > df["macd_dea"]) |  # 金叉状态
                (df["macd_dif"] > 0)                   # 或零轴上方
            )
        else:
            df["macd_bullish"] = True

        # 5. 相对位置: 不在历史高位 (60日最高点的85%以下)
        high_col = f"high_{self.ma_long}"
        if high_col in df.columns and "close" in df.columns:
            df["not_extreme"] = df["close"] < df[high_col] * 0.85
        else:
            df["not_extreme"] = True

        # 综合筛选
        mask = (
            df["ma_aligned"] &
            df["above_ma5"] &
            df["volume_breakout"] &
            df["macd_bullish"] &
            df["not_extreme"]
        )
        result = df[mask].copy()

        # 计算趋势得分 (0-1)
        result["trend_score"] = self._compute_score(result)

        logger.info(f"[趋势扫描] {len(df)}只 → 筛选出 {len(result)} 只趋势候选")
        return result

    def _compute_score(self, df: pd.DataFrame) -> pd.Series:
        """计算趋势强度得分"""
        score = pd.Series(0.5, index=df.index)

        # 均线发散度 (MA5/MA60偏离越大越好, 但不超过20%)
        ma_short_col = f"ma{self.ma_short}"
        ma_long_col = f"ma{self.ma_long}"
        if ma_short_col in df.columns and ma_long_col in df.columns:
            spread = (df[ma_short_col] / df[ma_long_col] - 1).clip(0, 0.20)
            score += spread * 1.5

        # 放量程度
        vol_ma_col = f"vol_ma{self.ma_short}"
        if vol_ma_col in df.columns and "volume" in df.columns:
            vol_ratio = (df["volume"] / df[vol_ma_col]).clip(0.5, 5)
            score += (vol_ratio - 1) * 0.1

        # MACD柱状图放大
        if "macd_bar" in df.columns:
            bar_positive = (df["macd_bar"] > 0).astype(float)
            score += bar_positive * 0.1

        return score.clip(0, 1)


class TrendStrategy(BaseStrategy):
    """
    趋势跟踪策略
    捕捉均线多头排列+放量突破的中线机会
    """

    strategy_name = "trend"
    strategy_description = "趋势跟踪策略 — 均线多头排列 + 放量突破 + MACD金叉, 中线3-10天"

    def __init__(self, config: dict = None):
        super().__init__(config or {})
        self.default_config = {
            "ma_short": 5,
            "ma_mid": 20,
            "ma_long": 60,
            "min_volume_ratio": 1.5,
            "min_market_cap": 20,
            "max_market_cap": 500,
            "top_n_picks": 5,
            "holding_days": 7,
            "stop_loss_pct": -0.05,
            "take_profit_pct": 0.08,
        }
        for k, v in self.default_config.items():
            self.config.setdefault(k, v)
        self.scanner = TrendScanner(self.config)

    def generate_signals(self, context: Any = None) -> List[StrategySignal]:
        """生成趋势信号 — 直接从快照表读取预计算指标"""
        logger.info("[趋势策略] 开始扫描...")
        signals = []

        try:
            candidates = self._scan_snapshot()
            if candidates is None or len(candidates) == 0:
                logger.info("[趋势策略] 无符合条件的趋势候选")
                return signals

            candidates = candidates.sort_values("trend_score", ascending=False)
            top_n = min(self.config["top_n_picks"], len(candidates))

            for _, row in candidates.head(top_n).iterrows():
                code = str(row.get("code", "")).zfill(6)
                name = row.get("name", "")
                price = row.get("close", 0)
                score = row.get("trend_score", 0)

                signal = StrategySignal(
                    code=code,
                    name=name,
                    direction="buy",
                    confidence=min(score, 1.0),
                    price=price,
                    stop_loss=price * (1 + self.config["stop_loss_pct"]),
                    take_profit=price * (1 + self.config["take_profit_pct"]),
                    horizon="中线",
                    reason=f"趋势策略: 均线多头+放量突破, 得分{score:.2f}",
                    strategy_name=self.strategy_name,
                    factors={
                        "trend_score": score,
                        "ma_aligned": bool(row.get("ma_aligned", False)),
                        "volume_breakout": bool(row.get("volume_breakout", False)),
                        "macd_bullish": bool(row.get("macd_bullish", False)),
                    },
                )
                signals.append(signal)

            logger.info(f"[趋势策略] 生成 {len(signals)} 个信号")

        except Exception as e:
            logger.error(f"[趋势策略] 扫描失败: {e}")

        self.signals_today = signals
        return signals

    def _scan_snapshot(self) -> "pd.DataFrame":
        """从快照表读取预计算指标并筛选趋势候选"""
        db_path = self._find_db()
        if not db_path:
            return None

        import sqlite3
        conn = sqlite3.connect(str(db_path))

        # 直接从快照表筛选 — 所有指标已预计算
        query = """
            SELECT code, name, close, volume,
                   ma5, ma20, ma60,
                   macd_dif, macd_dea, macd_bar,
                   rsi14, vol_ratio_5, vol_ratio_20,
                   high_20d, low_20d, drawdown_20d,
                   pre_close
            FROM daily_indicator_snapshot
            WHERE ma5 IS NOT NULL
              AND ma20 IS NOT NULL
              AND ma60 IS NOT NULL
              AND macd_dif IS NOT NULL
              AND close > 0
              AND name NOT LIKE '%ST%'
              AND name NOT LIKE '%退%'
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        if len(df) == 0:
            return None

        # 趋势条件筛选
        mask = (
            (df["ma5"] > df["ma20"]) &
            (df["ma20"] > df["ma60"]) &               # 均线多头
            (df["close"] > df["ma5"]) &                # 价格在MA5上
            (df["vol_ratio_5"] > self.config.get("min_volume_ratio", 1.5)) &  # 放量
            (df["macd_dif"] > df["macd_dea"]) &        # MACD金叉
            (df["close"] < df["high_20d"] * 0.85)      # 不在极端高位
        )
        df = df[mask].copy()

        # 计算趋势得分
        df["trend_score"] = 0.5
        spread = (df["ma5"] / df["ma60"] - 1).clip(0, 0.20)
        df["trend_score"] += spread * 1.5
        df["trend_score"] += (df["vol_ratio_5"] - 1).clip(0, 2) * 0.1
        df["trend_score"] += (df["macd_dif"] > 0).astype(float) * 0.15
        df["trend_score"] = df["trend_score"].clip(0, 1)

        df["ma_aligned"] = True
        df["volume_breakout"] = True
        df["macd_bullish"] = True

        return df

    def _find_db(self):
        for p in [Path("data/cache/kline_cache.db"),
                  Path("/mnt/d/AI/auction-stock-picker/data/cache/kline_cache.db")]:
            if p.exists():
                return p
        return None

    def get_parameters(self) -> dict:
        return {k: self.config.get(k, v) for k, v in self.default_config.items()}

    def set_parameters(self, params: dict):
        self.config.update(params)
        self.scanner = TrendScanner(self.config)
