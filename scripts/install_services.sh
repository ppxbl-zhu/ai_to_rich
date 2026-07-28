#!/bin/bash
# QuantAgent systemd 服务安装脚本
# 运行: sudo bash scripts/install_services.sh

set -e
cd /mnt/d/AI/quant-agent

echo "=== QuantAgent systemd 安装 ==="

# 1. 复制服务文件
echo "1. 安装service/timer文件..."
cp -f scheduler/services/*.service /etc/systemd/system/
cp -f scheduler/services/*.timer /etc/systemd/system/
systemctl daemon-reload
echo "   ✅ 已复制"

# 2. 启用定时器
echo "2. 启用定时器..."
systemctl enable research-agent.timer
systemctl enable auction-pick.timer
systemctl enable review-agent.timer
systemctl enable indicator-refresh.timer
systemctl enable ga-daily.timer
echo "   ✅ 已启用"

# 3. 启动常驻服务
echo "3. 启动常驻服务..."
systemctl restart dashboard.service
echo "   ✅ Dashboard (端口5001)"
systemctl restart monitor.service
echo "   ✅ Monitor (交易时段监控)"

# 4. 显示状态
echo ""
echo "=== 定时任务时间表 ==="
systemctl list-timers --no-pager 2>/dev/null | grep -E "agent|auction|indicator|ga-daily|NEXT" || true

echo ""
echo "=== 服务状态 ==="
for svc in dashboard monitor; do
    status=$(systemctl is-active $svc.service 2>/dev/null || echo "inactive")
    echo "  $svc: $status"
done

echo ""
echo "=== 定时任务一览 ==="
echo "  00:30  指标刷新      indicator-refresh"
echo "  02:00  每日GA微调     ga-daily"
echo "  08:00  盘前调研       research-agent"
echo "  09:14  竞价选股       auction-pick"
echo "  15:30  盘后复盘       review-agent"
echo "  常驻   Dashboard      :5001"
echo "  常驻   实时监控       monitor"

echo ""
echo "✅ 安装完成! 明天开始自动运行"
echo "   Dashboard: http://localhost:5001"
echo "   查看日志: journalctl -u <service名> -f"
