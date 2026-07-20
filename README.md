# A股模拟量化实验室

以 50,000 元虚拟本金运行的研究型模拟盘。系统只生成模拟成交与研究报告，不连接券商、不发送真实订单。

## 风控约束

- 常态回撤目标 8%，10% 开始收缩风险，15% 强防守，20% 停止开新仓。
- 4–6 只持仓；单只初始权重不超过 12%，绝对上限 20%。
- 不因浮亏机械补仓；每天按当前信息重新比较所有候选标的。
- 候选模型只能在隔离样本和模拟盘胜出后晋级；风险上限不可被优化器修改。

## 运行

使用内置演示数据验证完整流程：

```powershell
& 'C:\Users\zsjpp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m quantlab.cli demo
& 'C:\Users\zsjpp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m quantlab.cli run
```

真实日线数据放到 `data/market.csv`，字段为：

```text
date,symbol,open,high,low,close,volume
```

系统采用当日收盘生成信号、下一交易日开盘模拟成交，避免未来数据泄漏。运行结果保存在 `state/`，日报保存在 `reports/`。

## 微信推送

个人微信没有稳定的官方机器人入口，因此默认只写本地报告。后续可在 `quantlab/notifier.py` 中接入你选定的公众号推送服务；令牌只能通过环境变量传入，不写入仓库。

## 当前边界

第一版是可审计骨架，演示数据只用于验证管线，不能用于评估收益。接入有授权的A股行情并积累足够样本后，才能评价模型效果。
