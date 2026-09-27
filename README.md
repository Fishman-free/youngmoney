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

降费迭代后（再平衡带宽 0.12 + 边缘成交 + 资金费率 3 事件平滑）：

| | 样本内 2024-01→2025-12 | 样本外 2025-12→2026-09 |
|---|---|---|
| 年化收益 | +2.46% | **+22.39%** |
| 年化波动 | 24.1% | 24.0% |
| Sharpe | 0.22 | 0.96 |
| 最大回撤 | -24.7% | -16.3% |
| 换手（年化） | 19.3x | 31.5x |
| 手续费 | 259 USDT | 181 USDT |

（迭代前基线：IS +0.61% / OOS -3.96%，换手 64x/136x，手续费 857/782 USDT。）

**必须诚实面对的三点：**
1. 样本外 22.4% 达标，但只是**单段 10 个月的样本外**；样本内仅 2.46%，IS/OOS 不对称大，存在这段行情恰好适配该策略的可能。
2. 降费改进是在看过基线回测结果之后做的——尽管有 walk-forward 结构，改参过程本身已沾染了这份数据，属于弱形式的事后调整。
3. 上实钱前应再做：更长样本外、多资产扩展（TradFi 永续/更多币对）、至少 1–2 个月 paper 前向跟踪。任何修改必须重跑 walk-forward，以样本外表现为准。

## 风险声明

- 历史回测不代表未来；15% 年化是目标，不是承诺。
- 杠杆交易可能导致本金全部损失；回撤 25% 的样本内表现是真实代价标签。
- paper 成交为模拟撮合，真实滑点/冲击成本可能更差。
- 本软件按现状提供，使用者自负盈亏。
