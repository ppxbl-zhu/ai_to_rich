# A股模拟量化实验室

以 100,000 元虚拟本金运行的研究型模拟盘。系统只生成模拟成交与研究报告，不连接券商、不发送真实订单。

## 风控约束

- 常态回撤目标 8%，10% 开始收缩风险，15% 强防守，20% 停止开新仓。
- 4–6 只持仓；单只初始权重不超过 12%，绝对上限 20%。
- 不因浮亏机械补仓；每天按当前信息重新比较所有候选标的。
- 候选模型只能在隔离样本和模拟盘胜出后晋级；风险上限不可被优化器修改。
- 个股默认8%硬止损；盈利达到5%后启用8%移动止损，并在趋势失效时退出。
- 单行业最多2只持仓，高相关股票不同时买入；涨跌停或停牌时拒绝伪造成交。
- 组合回撤达到10%减仓、15%强防守、20%停止开仓并触发组合退出。

## 运行

使用内置演示数据验证完整流程：

```powershell
& 'C:\Users\zsjpp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m quantlab.cli demo
& 'C:\Users\zsjpp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m quantlab.cli fetch
& 'C:\Users\zsjpp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m quantlab.cli run
```

`fetch` 默认使用环境变量 `TUSHARE_TOKEN` 调用 Tushare，建立全A股合规名册，剔除官方 ST 名单和上市未满120天的股票；首阶段按成交额为500只训练标的生成前复权历史日线。Tushare失败时才降级到腾讯自选股备用源，实际来源写入 `data/market.meta.json`。也可以自行放入有授权的数据，字段为：

```text
date,symbol,open,high,low,close,volume
```

系统采用当日收盘生成信号、下一交易日开盘模拟成交，避免未来数据泄漏。运行结果保存在 `state/`，日报保存在 `reports/`。

## 微信推送

个人微信没有稳定的官方机器人入口，因此默认只写本地报告。项目支持通过 PushPlus 转发到微信，令牌只从环境变量读取：

```powershell
$env:PUSHPLUS_TOKEN = "你的令牌"
& 'C:\Users\zsjpp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m quantlab.cli daily
```

`daily` 会依次更新行情、运行模拟盘并尝试推送；未配置令牌时会安全跳过推送。

## 盘中训练样本

盘中监控对全A股合规名册分批抓取快照，并压缩保存到 `data/realtime/YYYY-MM-DD.jsonl.gz`。全市场建议每60秒采样一次；采集器只在沪深连续交易时段运行，名称含 `ST` 的股票会被剔除：

```powershell
& 'C:\Users\zsjpp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m quantlab.cli monitor --interval 60 --minutes 335
```

使用 `--once` 可以在非交易时段采集一次，用于连通性诊断。实时快照只作为后续特征工程和走样本外训练的原始样本，不会触发真实交易。

## 当前边界

腾讯盘中入口只适合研究和模拟验证，不承诺可用性或数据授权范围，不应用于实盘下单。选股综合考虑个股动量、波动与流动性、板块相对强弱和全市场宽度；弱势市场会自动降低目标仓位。冠军模型只在滚动样本外适应度超过现有模型时晋级；分钟样本积累不足时不会参与模型晋级。

## 主升波段 v1

日线模型寻找未来 5–20 个交易日可能进入主升段的结构，综合多头排列、均线斜率、波动收缩、上涨/下跌成交量差、临近 60 日新高、平台突破及量能确认，并惩罚偏离 20 日均线过远的股票。未来 20 日最大涨幅达到 15% 且过程中最大回撤不超过 8% 才记为主升正样本。时间序列前 80% 用于搜索权重，最后 20% 完全隔离用于冠军晋级；只有“突破待确认”和“主升持有”阶段允许新开模拟仓位。

## 五年历史回测

```powershell
python -m quantlab.cli fetch
python -m quantlab.cli backtest
```

回测按时间顺序使用前 60% 训练、中间 20% 验证选参、最后 20% 隔离测试。成交使用信号后的下一交易日开盘价，并计入佣金、印花税、滑点和 100 股整数手约束。报告写入 `reports/backtest-YYYY-MM-DD.md`，候选冠军写入 `state/models/backtest_champion.json`；运行产物不会提交到 Git。

当前股票池按最新时点流动性生成，因此仍有幸存者偏差；历史 ST、退市样本及逐日涨跌停状态尚未完整点时复原。回测只用于研究和淘汰策略，不代表未来收益。
