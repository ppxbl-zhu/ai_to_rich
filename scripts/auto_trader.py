#!/usr/bin/env python3
"""
自动交易决策 — 选股→评估→建仓→风控 全自动
由 systemd/Cron 触发，不需要人工确认
"""
import sys; sys.path.insert(0, '/mnt/d/AI/quant-agent')
import time
from datetime import datetime
from loguru import logger


def run():
    print(f'\n🤖 自动交易决策 — {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('=' * 50)

    # 1. 运行所有策略
    from strategies.trend_strategy.runner import TrendStrategy
    from strategies.reversal_strategy.runner import ReversalStrategy
    from strategies.event_strategy.runner import EventStrategy

    all_signals = []
    for name, strategy_cls in [
        ('trend', TrendStrategy),
        ('reversal', ReversalStrategy),
        ('event', EventStrategy),
    ]:
        try:
            sigs = strategy_cls().generate_signals()
            all_signals.extend(sigs)
            print(f'  {name}: {len(sigs)} signals')
        except Exception as e:
            print(f'  {name}: error - {e}')

    if not all_signals:
        print('  无信号，跳过')
        return

    # 2. 合并+去重
    from strategies.composite.merger import SignalMerger, CapitalAllocator
    merger = SignalMerger({
        'max_positions': 5,
        'max_per_sector': 2,
        'min_confidence': 0.55,  # 只买高置信度
    })
    picks = merger.merge(all_signals)
    print(f'\n  合并后: {len(picks)} picks')

    if not picks:
        print('  无符合条件的推荐')
        return

    # 3. 检查现有持仓，避免重复
    from agents.tools.trading_tools import trading_tools
    pf = trading_tools.get_portfolio_summary()
    held = {p['code'] for p in pf.get('positions', [])}

    new_picks = [s for s in picks if s.code not in held]
    if not new_picks:
        print(f'  {len(picks)} picks 但全部已持仓')
        return

    # 4. 资金分配
    allocator = CapitalAllocator({
        'total_capital': 100000,
        'max_position_pct': 0.25,
        'method': 'confidence_weighted',
    })
    alloc = allocator.allocate(new_picks)

    # 5. 执行买入 (加退市/ST保护)
    bought = 0
    for s in new_picks:
        # 安全过滤: 不买无名、ST、退市股
        if not s.name or 'ST' in s.name.upper() or '退' in s.name:
            print(f'  🚫 跳过 {s.name or s.code}({s.code}) — ST/退市/无名股')
            continue

        if pf['cash'] < 5000:
            print(f'  现金不足(¥{pf["cash"]:,.0f})，停止买入')
            break

        a = alloc.get(s.code, {})
        amount = a.get('amount', 25000)

        result = trading_tools.execute_buy(
            code=s.code,
            name=s.name,
            price=s.price,
            amount=amount,
            strategy_id=s.strategy_name,
            reason=s.reason,
        )

        if result['status'] == 'ok':
            d = result['detail']
            bought += 1
            print(f'  ✅ 买入 {d["name"]}({d["code"]}) '
                  f'{d["shares"]}股 @{d["price"]:.2f} '
                  f'¥{d["cost"]:,.0f}')
        else:
            print(f'  ❌ {s.code}: {result.get("error", "unknown")}')

    # 6. 检查持仓是否需要止损止盈
    print()
    check_risk()

    # 7. 最终状态
    pf2 = trading_tools.get_portfolio_summary()
    print(f'\n  💰 持仓: {pf2["positions_count"]}只 | '
          f'现金: ¥{pf2["cash"]:,.0f} | '
          f'总资产: ¥{pf2["total_value"]:,.0f}')
    print('=' * 50)


def check_risk():
    """检查现有持仓的止损止盈"""
    from agents.tools.trading_tools import trading_tools
    from agents.tools.data_tools import data_tools

    pf = trading_tools.get_portfolio_summary()
    positions = pf.get('positions', [])
    if not positions:
        return

    codes = [p['code'] for p in positions]
    quotes = data_tools.get_realtime_quote(codes)

    for p in positions:
        code = p['code']
        q = quotes.get(code, {})
        price = q.get('price', p.get('current_price', p['entry_price']))
        pnl_pct = (price / p['entry_price'] - 1) * 100

        # 止损: -5%
        if pnl_pct <= -5:
            r = trading_tools.execute_sell(code, price=price, reason=f'止损 {pnl_pct:.1f}%')
            if r['status'] == 'ok':
                print(f'  🛑 止损 {p["name"]}({code}) {pnl_pct:.1f}%')
        # 止盈: +10%
        elif pnl_pct >= 10:
            r = trading_tools.execute_sell(code, price=price, reason=f'止盈 {pnl_pct:.1f}%')
            if r['status'] == 'ok':
                print(f'  🎯 止盈 {p["name"]}({code}) {pnl_pct:.1f}%')
        # 盈利>5% 设移动止盈
        elif pnl_pct > 5:
            pass  # 持有


if __name__ == '__main__':
    run()
