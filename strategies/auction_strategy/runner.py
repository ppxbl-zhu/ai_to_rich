"""
Auction Strategy Runner — 集合竞价策略
从现有 auction-stock-picker 移植, 适配新架构
"""
import sys
from pathlib import Path
from typing import List, Optional, Any
import pandas as pd
from loguru import logger

# 将现有系统加入路径以复用代码
EXISTING_SYSTEM = Path("/mnt/d/AI/auction-stock-picker")
if str(EXISTING_SYSTEM) not in sys.path:
    sys.path.append(str(EXISTING_SYSTEM))  # append, not insert(0), 避免遮蔽quant-agent自身模块

from strategies.base_strategy import BaseStrategy, StrategySignal


class AuctionStrategy(BaseStrategy):
    """
    集合竞价选股策略 (86.6%胜率)
    复用现有 auction-stock-picker 的引擎层
    """

    strategy_name = "auction"
    strategy_description = "A股集合竞价选股策略 — 基于多因子模型的竞价信号捕捉"

    def __init__(self, config: dict = None):
        super().__init__(config or {})
        self.default_config = {
            "min_auction_change": 1.0,
            "max_auction_change": 6.0,
            "min_volume_ratio": 1.5,
            "min_auction_amount": 100,       # 万元
            "min_market_cap": 20,             # 亿
            "max_market_cap": 500,            # 亿
            "hot_sector_top_n": 20,
            "top_n_picks": 4,
            "max_per_sector": 2,
            "holding_days": 5,
            "stop_loss_pct": -0.03,
            "take_profit_pct": 0.05,
            "use_hot_sector_filter": True,
            "use_llm_review": False,
        }
        # 合并默认值和传入配置
        for k, v in self.default_config.items():
            self.config.setdefault(k, v)

    def generate_signals(self, context: Any) -> List[StrategySignal]:
        """
        生成竞价选股信号
        复用现有 engine/scorer.py 的打分逻辑
        """
        logger.info("[竞价策略] 开始生成信号...")
        signals = []

        try:
            # 尝试复用现有竞价选股引擎
            from engine.scorer import scorer as existing_scorer
            from data.auction import auction_fetcher
            from engine.hot_sector import hot_sector_detector
            from engine.prefilter import prefilter

            # Step 1: 获取竞价数据
            auction_df = auction_fetcher.fetch_current()
            if auction_df is None or len(auction_df) == 0:
                logger.warning("[竞价策略] 无竞价数据")
                return signals

            # Step 2: 初筛
            filtered = prefilter.filter(auction_df)
            logger.info(f"[竞价策略] 初筛后: {len(filtered)} 只 (从 {len(auction_df)})")

            # Step 3: 热点板块
            hot_sectors = set()
            stock_sector_map = {}
            if self.config.get("use_hot_sector_filter"):
                try:
                    sectors = hot_sector_detector.get_hot_sectors(
                        top_n=self.config["hot_sector_top_n"]
                    )
                    hot_sectors = set(sectors.keys()) if isinstance(sectors, dict) else set(sectors)
                except Exception as e:
                    logger.warning(f"[竞价策略] 热点板块获取失败: {e}")

            # Step 4: 多因子打分
            scored = existing_scorer.score(filtered, hot_sectors, stock_sector_map)

            # Step 5: 精选TOP
            top_picks = existing_scorer.select_top_picks(
                scored,
                top_n=self.config["top_n_picks"],
                max_per_sector=self.config["max_per_sector"],
                stock_sector_map=stock_sector_map,
            )

            # Step 6: 转换为 StrategySignal
            for _, row in top_picks.iterrows():
                code = str(row["代码"]).zfill(6)
                name = row.get("名称", "")
                price = row.get("最新价", 0)
                score = row.get("总分", 0)

                signal = StrategySignal(
                    code=code,
                    name=name,
                    direction="buy",
                    confidence=min(score / 100, 1.0),  # 归一化到0-1
                    price=price,
                    stop_loss=price * (1 + self.config["stop_loss_pct"]),
                    take_profit=price * (1 + self.config["take_profit_pct"]),
                    horizon="短线",
                    reason=f"竞价策略TOP{len(top_picks)}, 总分{score}",
                    strategy_name=self.strategy_name,
                    factors={
                        "auction_score": row.get("竞价得分", 0),
                        "technical_score": row.get("技术得分", 0),
                        "capital_score": row.get("资金得分", 0),
                        "fundamental_score": row.get("基本面得分", 0),
                    },
                )
                signals.append(signal)

            logger.info(f"[竞价策略] 生成 {len(signals)} 个信号")

        except ImportError as e:
            logger.warning(f"[竞价策略] 无法导入现有引擎: {e}, 使用模拟模式")
            signals = self._generate_dummy_signals()
        except Exception as e:
            logger.error(f"[竞价策略] 执行异常: {e}")
            signals = self._generate_dummy_signals()

        self.signals_today = signals
        return signals

    def _generate_dummy_signals(self) -> List[StrategySignal]:
        """当现有引擎不可用时, 生成模拟信号 (占位)"""
        return []

    def get_parameters(self) -> dict:
        return {k: self.config.get(k, v) for k, v in self.default_config.items()}

    def set_parameters(self, params: dict):
        self.config.update(params)
        logger.info(f"[竞价策略] 参数更新: {list(params.keys())}")
