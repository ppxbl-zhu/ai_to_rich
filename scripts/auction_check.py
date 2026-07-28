#!/usr/bin/env python3
"""竞价数据自检 — 每日09:25运行, 检查数据源状态并推送微信"""
import sys; sys.path.insert(0, '/mnt/d/AI/quant-agent')
import time
from datetime import datetime

def check():
    results = {}

    # 1. 检查东方财富竞价API
    print("[Check 1] 东方财富竞价数据...")
    try:
        import requests
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        resp = requests.get(url, params={
            "pn":"1","pz":"5","po":"1","np":"1","fltt":"2","invt":"2",
            "fid":"f3","fs":"m:0+t:6,m:0+t:80",
            "fields":"f2,f3,f12,f14",
        }, headers={"Referer":"https://quote.eastmoney.com/"}, timeout=10)
        data = resp.json()
        if data.get("data",{}).get("diff"):
            results['eastmoney'] = f"OK ({len(data['data']['diff'])} stocks)"
            print(f"  ✅ Eastmoney OK")
        else:
            results['eastmoney'] = "FAIL: no data"
            print(f"  ❌ Eastmoney no data")
    except Exception as e:
        results['eastmoney'] = f"FAIL: {str(e)[:50]}"
        print(f"  ❌ Eastmoney: {e}")

    # 2. 检查新浪实时行情
    print("[Check 2] 新浪实时行情...")
    try:
        import requests
        resp = requests.get('https://hq.sinajs.cn/list=s_sh000001,sz000001',
                          headers={"Referer":"https://finance.sina.com.cn"}, timeout=8)
        resp.encoding='gbk'
        if '="' in resp.text and len(resp.text) > 100:
            results['sina'] = "OK"
            print(f"  ✅ Sina OK")
        else:
            results['sina'] = "FAIL: empty response"
            print(f"  ❌ Sina empty")
    except Exception as e:
        results['sina'] = f"FAIL: {str(e)[:50]}"
        print(f"  ❌ Sina: {e}")

    # 3. 检查今日K线是否已更新
    print("[Check 3] K线数据...")
    try:
        import sqlite3
        today = datetime.now().strftime('%Y%m%d')
        conn = sqlite3.connect('/mnt/d/AI/auction-stock-picker/data/cache/kline_cache.db')
        cnt = conn.execute('SELECT COUNT(*) FROM kline_daily WHERE date=?', (today,)).fetchone()[0]
        conn.close()
        if cnt > 0:
            results['kline'] = f"OK ({cnt} stocks for today)"
            print(f"  ✅ K-line OK")
        else:
            results['kline'] = "WARN: today data not yet available (normal before EOD)"
            print(f"  ⚠️ K-line: today not yet")
    except Exception as e:
        results['kline'] = f"FAIL: {str(e)[:50]}"

    # 4. 汇总 & 推送微信
    ok_count = sum(1 for v in results.values() if v.startswith('OK'))
    fail_count = sum(1 for v in results.values() if v.startswith('FAIL'))

    status = "✅" if fail_count == 0 else "⚠️" if fail_count <= 1 else "❌"

    body = f"{status} 竞价数据自检 — {datetime.now().strftime('%H:%M')}\n\n"
    for name, result in results.items():
        icon = "✅" if result.startswith('OK') else "❌" if result.startswith('FAIL') else "⚠️"
        body += f"{icon} {name}: {result}\n"

    if fail_count > 0:
        body += "\n⚠️ 部分数据源不可用, 将使用可用数据源进行选股"

    print(f"\n{body}")

    # 推送微信
    if fail_count > 0:
        from agents.tools.notification_tools import notification_tools
        notification_tools.send_alert(
            f"{status} 竞价数据自检",
            body,
            priority="high" if fail_count > 1 else "normal",
            channel="wechat",
        )

    return results

if __name__ == '__main__':
    check()
