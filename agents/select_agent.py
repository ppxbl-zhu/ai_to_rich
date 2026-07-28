"""
Select Agent — 多策略选股 + LLM综合评分 (完整实现)
"""
import sys
from pathlib import Path
from typing import List
from loguru import logger

from core.agent_runner import BaseAgent, AgentRunResult
from core.context_manager import TradingContext, Signal as CtxSignal
from strategies.base_strategy import StrategySignal
from agents.tools.data_tools import data_tools
from agents.tools.notification_tools import notification_tools

EXISTING_SYSTEM = Path("/mnt/d/AI/auction-stock-picker")
if str(EXISTING_SYSTEM) not in sys.path:
    sys.path.append(str(EXISTING_SYSTEM))


class SelectAgent(BaseAgent):
    """多策略选股Agent"""

    agent_name = "select_agent"
    agent_description = "多策略选股: 竞价+趋势+反转+事件 → 信号合并 → LLM综合评分 → 推送推荐"

    def run(self, context: TradingContext = None, **kwargs) -> AgentRunResult:
        logger.info("[Select Agent] 开始多策略选股...")
        t0 = __import__("time").time()

        try:
            # Step 1: 运行所有策略
            all_signals = self._run_all_strategies(context)
            logger.info(f"[Select] 各策略合计产生 {len(all_signals)} 个原始信号")

            # Step 2: 信号合并
            from strategies.composite.merger import merger
            merged = merger.merge(all_signals)
            logger.info(f"[Select] 合并后: {len(merged)} 个信号")

            # Step 3: LLM综合评分 (可选)
            if merged and self._should_use_llm(context):
                merged = self._llm_review_signals(merged, context)

            # Step 4: 写入上下文
            if context:
                for s in merged:
                    context.add_signal(CtxSignal(
                        code=s.code, name=s.name, direction=s.direction,
                        strategy_id=s.strategy_name, confidence=s.confidence,
                        price=s.price, stop_loss=s.stop_loss, take_profit=s.take_profit,
                        horizon=s.horizon, reason=s.reason,
                    ))

            # Step 5: 推送推荐
            if merged:
                self._push_recommendations(merged)

            duration_ms = (__import__("time").time() - t0) * 1000
            logger.info(f"[Select Agent] 完成 ({duration_ms:.0f}ms): "
                       f"推荐{len(merged)}只")

            return AgentRunResult(
                agent_name=self.agent_name,
                status="completed",
                output={
                    "strategies": 4,
                    "raw_signals": len(all_signals),
                    "recommended": len(merged),
                    "picks": [s.to_dict() for s in merged],
                },
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"[Select Agent] 失败: {e}")
            return AgentRunResult(self.agent_name, "failed", error=str(e))

    def _run_all_strategies(self, context) -> List[StrategySignal]:
        """运行所有已注册策略"""
        all_signals = []

        strategies_to_run = [
            ("auction", self._run_auction),
            ("trend", self._run_trend),
            ("reversal", self._run_reversal),
            ("event", self._run_event),
        ]

        for name, runner in strategies_to_run:
            try:
                signals = runner(context)
                all_signals.extend(signals)
                logger.debug(f"[Select] {name}: {len(signals)} signals")
            except Exception as e:
                logger.warning(f"[Select] {name}策略失败: {e}")

        return all_signals

    def _run_auction(self, context) -> List[StrategySignal]:
        from strategies.auction_strategy.runner import AuctionStrategy
        return AuctionStrategy().generate_signals(context)

    def _run_trend(self, context) -> List[StrategySignal]:
        from strategies.trend_strategy.runner import TrendStrategy
        return TrendStrategy().generate_signals(context)

    def _run_reversal(self, context) -> List[StrategySignal]:
        from strategies.reversal_strategy.runner import ReversalStrategy
        return ReversalStrategy().generate_signals(context)

    def _run_event(self, context) -> List[StrategySignal]:
        from strategies.event_strategy.runner import EventStrategy
        return EventStrategy().generate_signals(context)

    def _should_use_llm(self, context) -> bool:
        """判断是否使用LLM复核"""
        # 检查API Key是否配置
        from config.settings import LLM_API_KEY
        if not LLM_API_KEY:
            return False
        return True

    def _llm_review_signals(self, signals: List[StrategySignal],
                            context) -> List[StrategySignal]:
        """LLM复核 + 重新排序"""
        try:
            from config.llm_config import get_prompt, chat_json

            # 构造信号摘要
            signals_text = "\n".join([
                f"{i+1}. {s.name}({s.code}) [{s.strategy_name}] "
                f"置信度={s.confidence:.2f} 价格={s.price:.2f} "
                f"理由={s.reason}"
                for i, s in enumerate(signals)
            ])

            # 获取市场背景
            market_context = "暂无"
            if context and context.market_brief:
                mb = context.market_brief
                market_context = (
                    f"市场情绪: {mb.sentiment:.2f}, "
                    f"状态: {mb.regime}, "
                    f"热点: {', '.join(mb.top_sectors[:5])}"
                )

            prompt = get_prompt("stock_selection",
                market_context=market_context,
                strategy_signals=signals_text,
                risk_preference="中等",
                holding_period="短线+中线",
            )

            messages = [
                {"role": "system", "content": "你是量化选股专家, 擅长多策略信号综合评判。"},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, temperature=0.2, use_cache=False)

            # 用LLM结果更新置信度
            llm_picks = {p["code"]: p for p in result.get("picks", [])}
            for s in signals:
                if s.code in llm_picks:
                    llm_conf = llm_picks[s.code].get("confidence", s.confidence)
                    s.confidence = (s.confidence + llm_conf) / 2  # 平均
                    llm_rationale = llm_picks[s.code].get("rationale", "")
                    if llm_rationale:
                        s.reason += f" | LLM: {llm_rationale}"

            # 按更新后的置信度重排
            signals.sort(key=lambda s: s.confidence, reverse=True)
            logger.info(f"[Select] LLM复核完成, {len(signals)} 信号已重新评分")

        except Exception as e:
            logger.warning(f"[Select] LLM复核失败: {e}, 保留原始信号")

        return signals

    def _push_recommendations(self, signals: List[StrategySignal]):
        """推送选股推荐"""
        for s in signals[:5]:
            try:
                notification_tools.send_trade_signal(s.to_dict())
            except Exception:
                pass  # 推送失败不影响主流程
