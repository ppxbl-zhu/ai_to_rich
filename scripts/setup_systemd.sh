#!/bin/bash
# QuantAgent systemd 安装 — 运行: bash scripts/setup_systemd.sh
set -e
cd /mnt/d/AI/quant-agent

# 清理旧文件
rm -f /etc/systemd/system/quant-*.service /etc/systemd/system/quant-*.timer

# === research-agent ===
cat > /etc/systemd/system/quant-research.service << 'SVC'
[Unit]
Description=QuantAgent Research
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /mnt/d/AI/quant-agent/scripts/run_research.py
WorkingDirectory=/mnt/d/AI/quant-agent
Environment=PYTHONPATH=/mnt/d/AI/quant-agent
SVC

cat > /etc/systemd/system/quant-research.timer << 'TMR'
[Unit]
Description=QuantAgent Research Timer
[Timer]
OnCalendar=*-*-* 08:00:00
Unit=quant-research.service
[Install]
WantedBy=timers.target
TMR

# === auction-pick ===
cat > /etc/systemd/system/quant-auction.service << 'SVC'
[Unit]
Description=QuantAgent Auction Pick
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /mnt/d/AI/quant-agent/scripts/run_select.py
WorkingDirectory=/mnt/d/AI/quant-agent
Environment=PYTHONPATH=/mnt/d/AI/quant-agent
SVC

cat > /etc/systemd/system/quant-auction.timer << 'TMR'
[Unit]
Description=QuantAgent Auction Timer
[Timer]
OnCalendar=*-*-* 09:14:50
Unit=quant-auction.service
[Install]
WantedBy=timers.target
TMR

# === review-agent ===
cat > /etc/systemd/system/quant-review.service << 'SVC'
[Unit]
Description=QuantAgent Review
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /mnt/d/AI/quant-agent/scripts/run_review.py
WorkingDirectory=/mnt/d/AI/quant-agent
Environment=PYTHONPATH=/mnt/d/AI/quant-agent
SVC

cat > /etc/systemd/system/quant-review.timer << 'TMR'
[Unit]
Description=QuantAgent Review Timer
[Timer]
OnCalendar=*-*-* 15:30:00
Unit=quant-review.service
[Install]
WantedBy=timers.target
TMR

# === indicator-refresh ===
cat > /etc/systemd/system/quant-indicator.service << 'SVC'
[Unit]
Description=QuantAgent Indicator Refresh
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /mnt/d/AI/quant-agent/scripts/indicator_refresh.py
WorkingDirectory=/mnt/d/AI/quant-agent
Environment=PYTHONPATH=/mnt/d/AI/quant-agent
SVC

cat > /etc/systemd/system/quant-indicator.timer << 'TMR'
[Unit]
Description=QuantAgent Indicator Timer
[Timer]
OnCalendar=*-*-* 00:30:00
Unit=quant-indicator.service
[Install]
WantedBy=timers.target
TMR

# === 启用 ===
systemctl daemon-reload
systemctl enable quant-research.timer quant-auction.timer quant-review.timer quant-indicator.timer

# === 测试 ===
echo "=== 测试执行 ==="
systemctl start quant-indicator.service && echo "✅ indicator: OK" || echo "❌ indicator: FAIL"

echo ""
echo "=== 定时器状态 ==="
systemctl list-timers --no-pager | grep quant

echo ""
echo "=== 时间表 ==="
echo "  00:30  指标刷新     quant-indicator"
echo "  08:00  盘前调研     quant-research"
echo "  09:14  竞价选股     quant-auction"
echo "  15:30  盘后复盘     quant-review"

echo ""
echo "✅ systemd 安装完成! 不需要开 Claude Code 也能自动运行"
