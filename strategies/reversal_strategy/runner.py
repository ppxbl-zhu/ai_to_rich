"""
Reversal Strategy — 超跌反弹策略
捕捉超跌后的反弹机会: RSI超卖 + 资金抄底 + 止跌形态, 短线1-3天
"""
from typing import List, Optional, Any
from pathlib import Path
import numpy as np
import pandas as pd
from loguru import logger

from strategies.base_strategy import BaseStrategy, StrategySignal


class ReversalScanner:
    """反转扫描器 — 识别超跌反弹形态"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.rsi_oversold = self.config.get("rsi_oversold", 30)
        self.max_drawdown = self.config.get("max_drawdown", -20)    # 20日内最大回撤
        self.min_bounce = self.config.get("min_bounce", 2.0)        # 最小反弹%
        self.min_market_cap = self.config.get("min_market_cap", 20)

    def scan(self, kline_data: pd.DataFrame) -> pd.DataFrame:
        """
        扫描超跌反弹信号
        """
        if kline_data is None or len(kline_data) == 0:
            return pd.DataFrame()

        df = kline_data.copy()

        # 1. RSI超卖区域
        if "rsi14" in df.columns:
            df["rsi_oversold"] = df["rsi14"] < self.rsi_oversold
        else:
            df["rsi_oversold"] = False

        # 2. 近期有较大跌幅 (20日回撤)
        if "drawdown_20d" in df.columns:
            df["deep_drawdown"] = df["drawdown_20d"] < self.max_drawdown
        else:
            df["deep_drawdown"] = False

        # 3. 今日出现反弹 (阳线且涨幅>min_bounce%)
        if "close" in df.columns and "open" in df.columns:
            df["is_yang"] = df["close"] > df["open"]
            if "pre_close" in df.columns:
                df["bounced"] = (df["close"] / df["pre_close"] - 1) * 100 > self.min_bounce
            else:
                df["bounced"] = df["is_yang"]
        else:
            df["is_yang"] = True
            df["bounced"] = True

        # 4. 放量反弹 (量比>1.2)
        if "vol_ma5" in df.columns and "volume" in df.columns:
            df["volume_spike"] = df["volume"] > df["vol_ma5"] * 1.2
        else:
            df["volume_spike"] = True

        # 5. 价格在MA60下方 (超跌)
        if "ma60" in df.columns and "close" in df.columns:
            df["below_ma60"] = df["close"] < df["ma60"]
        else:
            df["below_ma60"] = True

        # 综合筛选: RSI超卖 OR 深度回撤 → 出现反弹+放量
        mask = (
            (df["rsi_oversold"] | df["deep_drawdown"]) &
            df["bounced"] &
            df["is_yang"] &
            df["volume_spike"] &
            df["below_ma60"]
        )
        result = df[mask].copy()

        result["reversal_score"] = self._compute_score(result)
        logger.info(f"[反转扫描] {len(df)}只 → 筛选出 {len(result)} 只反转候选")
        return result

    def _compute_score(self, df: pd.DataFrame) -> pd.Series:
        """计算反转强度得分"""
        score = pd.Series(0.3, index=df.index)

        # RSI越低越好 (超卖程度)
        if "rsi14" in df.columns:
            rsi_bonus = ((30 - df["rsi14"].clip(10, 30)) / 20).clip(0, 1)
            score += rsi_bonus * 0.3

        # 回撤越大越好 (反弹空间)
        if "drawdown_20d" in df.columns:
            dd_bonus = ((-df["drawdown_20d"] - 20) / 20).clip(0, 1)
            score += dd_bonus * 0.2

        # 反弹力度
        if "bounced" in df.columns:
            score += df["bounced"].astype(float) * 0.1

        # 量比越大越好
        if "vol_ma5" in df.columns and "volume" in df.columns:
            vol_ratio = (df["volume"] / df["vol_ma5"]).clip(0.5, 5)
            score += (vol_ratio - 1) * 0.1

        return score.clip(0, 1)


class ReversalStrategy(BaseStrategy):
    """
    超跌反弹策略
    捕捉RSI超卖后放量反弹的短线机会
    """

    strategy_name = "reversal"
    strategy_description = "超跌反弹策略 — RSI超卖 + 深度回撤 + 放量反弹, 短线1-3天"

    def __init__(self, config: dict = None):
        super().__init__(config or {})
        self.default_config = {
            "rsi_oversold": 30,
            "max_drawdown": -20,
            "min_bounce": 2.0,
            "min_market_cap": 20,
            "top_n_picks": 3,
            "holding_days": 2,
            "stop_loss_pct": -0.03,
            "take_profit_pct": 0.05,
        }
        for k, v in self.default_config.items():
            self.config.setdefault(k, v)
        self.scanner = ReversalScanner(self.config)

    def generate_signals(self, context: Any = None) -> List[StrategySignal]:
        """生成反转信号 — 直接从快照表读取预计算指标"""
        logger.info("[反转策略] 开始扫描...")
        signals = []

        try:
            candidates = self._scan_snapshot()
            if candidates is None or len(candidates) == 0:
                logger.info("[反转策略] 无符合条件的反转候选")
                return signals

            candidates = candidates.sort_values("reversal_score", ascending=False)
            top_n = min(self.config["top_n_picks"], len(candidates))

            for _, row in candidates.head(top_n).iterrows():
                code = str(row.get("code", "")).zfill(6)
                name = row.get("name", "")
                price = row.get("close", 0)
                score = row.get("reversal_score", 0)

                signal = StrategySignal(
                    code=code,
                    name=name,
                    direction="buy",
                    confidence=min(score, 1.0),
                    price=price,
                    stop_loss=price * (1 + self.config["stop_loss_pct"]),
                    take_profit=price * (1 + self.config["take_profit_pct"]),
                    horizon="短线",
                    reason=f"反转策略: 超跌反弹, 得分{score:.2f}",
                    strategy_name=self.strategy_name,
                    factors={
                        "reversal_score": score,
                        "rsi14": float(row.get("rsi14", 0)),
                        "drawdown_20d": float(row.get("drawdown_20d", 0)),
                    },
                )
                signals.append(signal)

            logger.info(f"[反转策略] 生成 {len(signals)} 个信号")

        except Exception as e:
            logger.error(f"[反转策略] 扫描失败: {e}")

        self.signals_today = signals
        return signals

    def _scan_snapshot(self) -> "pd.DataFrame":
        """从快照表读取预计算指标并筛选反转候选"""
        db_path = self._find_db()
        if not db_path:
            return None

        import sqlite3
        conn = sqlite3.connect(str(db_path))

        query = """
            SELECT code, name, close, volume,
                   ma5, ma20, ma60,
                   rsi14, vol_ratio_5,
                   drawdown_20d, high_20d, low_20d,
                   pre_close, open
            FROM daily_indicator_snapshot
            WHERE rsi14 IS NOT NULL
              AND drawdown_20d IS NOT NULL
              AND ma60 IS NOT NULL
              AND close > 0
              AND name NOT LIKE '%ST%'
              AND name NOT LIKE '%退%'
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        if len(df) == 0:
            return None

        # 反转条件筛选
        mask = (
            ((df["rsi14"] < self.config.get("rsi_oversold", 30)) |
             (df["drawdown_20d"] < self.config.get("max_drawdown", -20))) &
            (df["close"] < df["ma60"]) &                 # 在MA60下方(超跌)
            (df["close"] > df["open"]) &                  # 收阳(反弹)
            (df["vol_ratio_5"] > 1.2)                     # 放量
        )
        df = df[mask].copy()

        # 计算反转得分
        df["reversal_score"] = 0.3
        if "rsi14" in df.columns:
            df["reversal_score"] += ((30 - df["rsi14"].clip(10, 30)) / 20).clip(0, 1) * 0.3
        if "drawdown_20d" in df.columns:
            df["reversal_score"] += ((-df["drawdown_20d"] - 20) / 20).clip(0, 1) * 0.2
        df["reversal_score"] += (df["vol_ratio_5"] - 1).clip(0, 2) * 0.1
        df["reversal_score"] = df["reversal_score"].clip(0, 1)

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
        self.scanner = ReversalScanner(self.config)
