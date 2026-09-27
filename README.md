# bnbot — Binance 中低频自动化交易平台（paper-first）

USDT-M 合约中低频量化交易：趋势 + 时序动量 + 资金费率 carry 三层策略，风控为硬约束，当前阶段为**纸面交易 / 回测**，真实下单执行器仅留接口。

## 架构

```
bnbot/data.py       行情抓取（fapi REST，CSV 缓存，断点续抓）
bnbot/quant.py      EMA / Donchian / 动量等指标原语
bnbot/strategy.py   目标仓位：趋势突破 + 时序动量 + carry 倾斜（config 调权）
bnbot/risk.py       硬风控：杠杆/单标的上限、日亏熔断、回撤节流、kill switch
bnbot/backtest.py   顺序撮合回测（taker 5bp + 滑点 2bp + 8h 资金费率结算），walk-forward
bnbot/live.py       paper 循环：目标仓位 diff → 取整 → 模拟成交 → 日志/状态
tests/              unittest 26 项（信号/风控/记账不变量）
```

## 运行

```powershell
# 本机访问 binance 需代理
$env:HTTPS_PROXY="http://127.0.0.1:7890"

python -m unittest discover -s tests -v        # 测试
python -m bnbot.data --fetch --proxy http://127.0.0.1:7890   # 抓/续抓历史数据
python -m bnbot.backtest --walk-forward        # 样本内选参 + 样本外评估
python -m bnbot.live --paper --once            # 纸面跑一轮
python -m bnbot.live --paper                   # 纸面循环（默认 4h）
```

kill switch：`New-Item KILL_SWITCH` 后 live 引擎全平并拒绝新仓；删除文件恢复。

## 凭据（第二阶段真实下单才需要）

`.env`（已 gitignore）中 `BN_API_KEY` / `BN_API_SECRET`。当前 paper 模式不需要。请在 Binance 控制台限制 API key 权限（仅合约读写、不开提现、绑定 IP 白名单）。

## 当前回测实况（2024-01 至今，walk-forward，费用后）

| | 样本内 2024-01→2025-12 | 样本外 2025-12→2026-09 |
|---|---|---|
| 年化收益 | +0.61% | -3.96% |
| 年化波动 | 24.7% | 26.8% |
| Sharpe | 0.15 | -0.02 |
| 最大回撤 | -25.1% | -19.8% |
| 换手（年化） | 63.9x | 136.1x |

**结论：当前参数远未达到 15% 年化目标。** 主要损耗：换手过高（两年手续费约 1,640 USDT / 万本金）与平均仓位过轻（暴露 0.28–0.49）。改进方向：再平衡带宽降换手、提高波动率目标利用率、carry 叠层增强、参数稳健性扫描。任何修改必须重跑 walk-forward 以样本外表现为准。

## 风险声明

- 历史回测不代表未来；15% 年化是目标，不是承诺。
- 杠杆交易可能导致本金全部损失；回撤 25% 的样本内表现是真实代价标签。
- paper 成交为模拟撮合，真实滑点/冲击成本可能更差。
- 本软件按现状提供，使用者自负盈亏。
