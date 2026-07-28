"""
Review Agent — 盘后复盘诊断 (完整实现)
交易归因 + LLM深度复盘 + 改进假设 → GA引擎
"""
import time
from datetime import date
from typing import Dict, Any
from loguru import logger

from core.agent_runner import BaseAgent, AgentRunResult
from core.context_manager import TradingContext
from agents.tools.data_tools import data_tools
from agents.tools.analysis_tools import analysis_tools
from agents.tools.notification_tools import notification_tools


class ReviewAgent(BaseAgent):
    """复盘诊断Agent — 每日盘后运行"""

    agent_name = "review_agent"
    agent_description = "盘后复盘: 交易归因 + LLM深度分析 + 改进假设生成 → GA引擎"

    def run(self, context: TradingContext = None, **kwargs) -> AgentRunResult:
        logger.info("[Review Agent] 开始复盘...")
        t0 = time.time()

        try:
            result = {}

            # Step 1: 收集数据
            trades = data_tools.get_trade_history(days=1)
            positions = data_tools.get_positions()
            market = data_tools.get_market_index()

            # Step 2: 绩效归因
            if trades:
                attribution = analysis_tools.performance_attribution(trades)
                result["attribution"] = attribution
                logger.info(f"[Review] 归因分析: {attribution.get('total_trades', 0)}笔, "
                           f"胜率={attribution.get('win_rate', 0)}%")

            # Step 3: 风险评估
            if positions:
                risk = analysis_tools.assess_risk(positions)
                result["risk"] = risk

            # Step 4: LLM深度复盘
            review_result = self._llm_deep_review(trades, market, context)
            result["review"] = review_result

            # Step 5: 生成改进假设
            hypotheses = review_result.get("improvement_hypotheses", [])
            if hypotheses:
                self._feed_to_ga(hypotheses, context)
                result["hypotheses_count"] = len(hypotheses)

            # Step 6: 写入上下文
            if context:
                context.review_output = result

            # Step 7: 推送复盘报告
            self._push_review_report(result, review_result)

            duration_ms = (time.time() - t0) * 1000
            logger.info(f"[Review Agent] 完成 ({duration_ms:.0f}ms): "
                       f"交易={len(trades)}笔, 改进假设={len(hypotheses)}个")

            return AgentRunResult(
                agent_name=self.agent_name,
                status="completed",
                output=result,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"[Review Agent] 失败: {e}")
            return AgentRunResult(self.agent_name, "failed", error=str(e))

    def _llm_deep_review(self, trades: list, market: dict, context) -> Dict:
        """LLM深度复盘"""
        try:
            from config.llm_config import get_prompt, chat_json

            # 构造交易记录摘要
            if not trades:
                trades_text = "今日无交易"
            else:
                trades_text = "\n".join([
                    f"- {t.get('direction','')} {t.get('stock_name','')}({t.get('stock_code','')}) "
                    f"盈亏={(t.get('pnl') or 0):.2f}({(t.get('pnl_pct') or 0):.1f}%) "
                    f"理由={t.get('exit_reason','')} 策略={t.get('strategy_id','')}"
                    for t in trades
                ])

            # 市场走势
            market_text = ""
            for name, idx in (market or {}).items():
                if isinstance(idx, dict):
                    market_text += f"{name}: {idx.get('current',0):.1f} ({idx.get('change',0):+.2f}%)\n"

            prompt = get_prompt("review",
                trade_records=trades_text,
                strategy_performance="待统计",
                market_movement=market_text or "暂无数据",
            )

            messages = [
                {"role": "system", "content": "你是交易复盘教练, 善于从交易中提炼经验教训。"},
                {"role": "user", "content": prompt},
            ]

            result = chat_json(messages, temperature=0.4, use_cache=False)
            return result

        except Exception as e:
            logger.warning(f"[Review] LLM复盘失败: {e}")
            return self._heuristic_review(trades)

    def _heuristic_review(self, trades: list) -> Dict:
        """启发式复盘 (LLM不可用时的fallback)"""
        if not trades:
            return {"day_rating": "N/A", "summary": "今日无交易", "improvement_hypotheses": []}

        wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
        total = len(trades)
        win_rate = wins / total * 100 if total > 0 else 0

        rating = "A" if win_rate >= 70 else "B" if win_rate >= 50 else "C" if win_rate >= 40 else "D"

        hypotheses = []
        if win_rate < 50:
            hypotheses.append({
                "target": "min_confidence",
                "current_value": "0.40",
                "suggested_direction": "increase",
                "rationale": f"胜率仅{win_rate:.0f}%, 建议提高信号置信度门槛",
            })

        return {
            "day_rating": rating,
            "key_lessons": [f"今日胜率{win_rate:.0f}%"],
            "mistakes": [],
            "improvement_hypotheses": hypotheses,
            "summary": f"启发式复盘: {total}笔交易, 胜率{win_rate:.0f}%",
        }

    def _feed_to_ga(self, hypotheses: list, context):
        """
        将改进假设喂给GA引擎
        - 保存到数据库
        - 作为下次GA优化的种子
        """
        try:
            from data.storage.sqlite_storage import storage

            # 保存复盘记录
            storage.get_conn().execute("""
                INSERT INTO review_notes
                (date, trade_ids, improvement_hypotheses, summary)
                VALUES (?, ?, ?, ?)
            """, (
                date.today().strftime("%Y-%m-%d"),
                "[]",  # TODO: 关联trade_ids
                __import__("json").dumps(hypotheses),
                f"生成{len(hypotheses)}个改进假设",
            ))
            storage.get_conn().commit()
            storage.get_conn().close()

            logger.info(f"[Review] {len(hypotheses)} 个改进假设已存档, 等待GA迭代")

        except Exception as e:
            logger.warning(f"[Review] 改进假设存档失败: {e}")

    def _push_review_report(self, result: Dict, review: Dict):
        """推送复盘报告"""
        day_rating = review.get("day_rating", "N/A")
        summary = review.get("summary", "")

        body = f"📊 今日评级: {day_rating}\n\n{summary}\n\n"

        # 关键教训
        lessons = review.get("key_lessons", [])
        if lessons:
            body += "💡 关键教训:\n" + "\n".join(f"  - {l}" for l in lessons) + "\n\n"

        # 改善建议
        hypotheses = review.get("improvement_hypotheses", [])
        if hypotheses:
            body += "🔧 策略优化建议:\n"
            for h in hypotheses[:3]:
                body += (f"  - {h.get('target','')}: "
                        f"{'增大' if h.get('suggested_direction')=='increase' else '减小'} "
                        f"(当前={h.get('current_value','')})\n")

        notification_tools.send_alert(
            f"复盘报告 - {date.today().strftime('%Y-%m-%d')}",
            body,
            priority="normal",
        )
