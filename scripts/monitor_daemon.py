#!/usr/bin/env python3
"""监控守护进程 — 交易时段30秒循环, 含自动止损止盈"""
import sys, time
sys.path.insert(0, '/mnt/d/AI/quant-agent')

from core.state_machine import state_machine
from core.event_bus import event_bus, EventType, Event

print("Monitor daemon started (systemd)")

# 防止重复推送
last_notify = {}
NOTIFY_COOLDOWN = 600  # 同一股票同一原因10分钟内不重复推送

while True:
    state_machine.update()
    if state_machine.is_trading:
        try:
            _check_positions()
        except Exception as e:
            print(f"Monitor error: {e}")
    time.sleep(30)


def _check_positions():
    from agents.tools.trading_tools import trading_tools
    from agents.tools.data_tools import data_tools
    from agents.tools.notification_tools import notification_tools

    pf = trading_tools.get_portfolio_summary()
    positions = pf.get('positions', [])
    if not positions:
        return

    codes = [p['code'] for p in positions]
    quotes = data_tools.get_realtime_quote(codes)

    for p in positions:
        code = p['code']
        q = quotes.get(code, {})
        price = q.get('price', 0)
        if price <= 0:
            continue

        pnl_pct = (price / p['entry_price'] - 1) * 100

        # 止损: -5%
        if pnl_pct <= -5:
            key = f"{code}_stop_loss"
            now = time.time()
            if now - last_notify.get(key, 0) < NOTIFY_COOLDOWN:
                continue
            last_notify[key] = now

            r = trading_tools.execute_sell(code, price=price, reason=f'止损 {pnl_pct:.1f}%')
            if r['status'] == 'ok':
                d = r['detail']
                msg = f"🛑 止损 {p['name']}({code})\n成本{p['entry_price']:.2f}→{price:.2f}\n亏损{pnl_pct:.1f}%  ¥{d['pnl']:+,.0f}"
                print(msg)
                notification_tools.send_alert('🛑 止损触发', msg, priority='urgent', channel='wechat')

        # 止盈: +10%
        elif pnl_pct >= 10:
            key = f"{code}_take_profit"
            now = time.time()
            if now - last_notify.get(key, 0) < NOTIFY_COOLDOWN:
                continue
            last_notify[key] = now

            r = trading_tools.execute_sell(code, price=price, reason=f'止盈 {pnl_pct:.1f}%')
            if r['status'] == 'ok':
                d = r['detail']
                msg = f"🎯 止盈 {p['name']}({code})\n成本{p['entry_price']:.2f}→{price:.2f}\n盈利{pnl_pct:.1f}%  ¥{d['pnl']:+,.0f}"
                print(msg)
                notification_tools.send_alert('🎯 止盈触发', msg, priority='high', channel='wechat')

        # 浮亏只在日志记录, 不推送微信(省额度)
