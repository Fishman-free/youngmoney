# bnbot 操作手册

中低频加密量化平台。纯 Python 标准库，paper 优先，真金操作前必须人工确认。

## 0. 前置

- Python 3.10+（本机 3.14）
- 网络：所有对外请求走代理 `--proxy http://127.0.0.1:7890`
- 凭据：`.env` 放 `BN_API_KEY` / `BN_API_SECRET`（绝不入 git、绝不回显）
- 可选：`pip install laya` 启用概率判断层（缺失则自动降级放行，不影响主流程）

## 1. 常用命令

```powershell
cd C:\Users\21560\Desktop\binance

# 抓/增量更新行情数据（7 标的 4h/1d + 资金费率）
python -m bnbot.data --fetch --proxy http://127.0.0.1:7890

# 回测（含 walk-forward 样本内外切分）
python -m bnbot.backtest --walk-forward

# 模拟盘：单轮
python -m bnbot.live --paper --once --proxy http://127.0.0.1:7890

# 模拟盘：常驻循环（4 小时一轮）
python -m bnbot.live --paper --proxy http://127.0.0.1:7890

# 讯息面情绪（每日一次，幂等）
python -m bnbot.sentiment

# 实盘就绪度报告（机器判据，非口头声称）
python -m bnbot.report

# 状态服务（只读）
python -m bnbot.server --port 8787
```

## 2. 每天看什么

| 入口 | 位置 | 看什么 |
|---|---|---|
| 状态面板 | http://127.0.0.1:8787/dashboard | 权益、计数器、最近轮次 |
| 快照 JSON | http://127.0.0.1:8787/ | 同上，给程序读 |
| 审计日志 | `state/STATE.md` | 每轮目标仓位、成交、拒绝原因；亏钱时唯一调试面 |
| 计数器 | `state/metrics.json` | cycles/orders/fills/rejected/late/fees 累计 |
| 订单流水 | `logs/orders-YYYYMMDD.log` | 逐单原始记录 |
| 判断层日志 | `state/judgment-log.jsonl` | laya 每次判断的状态与答案（校准三元组） |
| 情绪记录 | `state/sentiment-shadow.csv` | 每日 X 情绪分（只记录，不参与下单） |

## 3. 三仓框架（2026-09-30 上线）

资金按三仓切分，**各有独立资金、独立风控、独立 kill switch**，一仓爆掉不碰其他仓：

| 仓 | 占比 | 杠杆上限 | 内容 | 状态 |
|---|---|---|---|---|
| A 长线 | 60% | 2x | 7 标的趋势+carry+XS（已验证引擎） | 运行中 |
| B 短线 | 30% | 3x | BTC/ETH/SOL，快参数（Donchian 24 / 动量 7d） | 运行中 |
| C 实验 | 10% | 10x | 山寨高杠杆 | **门禁未过，模拟观察中** |

```powershell
# 跑一遍三仓（各自独立状态）
python -m bnbot.live --sleeves --once --proxy http://127.0.0.1:7890

# 只跑单仓（兼容旧命令）
python -m bnbot.live --paper --once
```

隔离落盘位置（每仓一份，互不可见）：

```
state/sleeves/<id>/portfolio.json     资金与持仓
state/sleeves/<id>/metrics.json       计数器
state/sleeves/<id>/STATE.md           审计日志
state/sleeves/<id>/judgment-log.jsonl laya 判断记录
state/sleeves/<id>/KILL_SWITCH        该仓独立急停（建文件即平仓停止）
logs/sleeves/<id>/orders-*.log        订单流水
```

**C 仓进真钱的门禁**（缺一不可）：模拟盘 ≥200 笔成交、净期望（扣费用滑点）为正、
最大回撤 ≤30%、kill switch 零触发。门禁未过前 `config.json` 里保持 `"enabled": false`。

杠杆上限写在 `bnbot/sleeves.py` 的 `SLEEVE_CEILINGS`，**配置只能收紧不能放松**——
即使改 config 也不会突破 A≤2x / B≤3x / C≤10x 的硬顶。

## 4. 系统架构（五层，各司其职）

```
数据层 bnbot/data.py        增量抓 K 线/资金费率，网络失败自动降级用缓存
信号层 bnbot/strategy.py    趋势(Donchian48) + 动量(30d) + 资金费率carry + 跨截面XS
判定层 bnbot/verify.py      确定性验证器 D1-D3（数据/信号一致/波动率），拒绝开新仓
     bnbot/judgment.py     概率判断层 J1-J4（laya 原子电池：regime/toxicity/setup）
风控层 bnbot/risk.py        杠杆/集中度/日亏/回撤 硬闸，kill switch 无协商
执行层 bnbot/live.py        paper 撮合（真执行器 phase-2 待启用）+ 订单生命周期
```

优先级：**风控 > 验证器 > 判断层**。任何下层只能否决，不能放大。

## 5. 实盘开关（当前状态：关闭）

实盘门禁写死在 `bnbot/report.py`，全部通过才谈实盘：

```powershell
python -m bnbot.report
```

| 门 | 判据 |
|---|---|
| G1 | paper 运行 ≥ 60 天 |
| G2 | 成交 ≥ 30 笔 |
| G3 | 最大回撤 ≤ 25% |
| G4 | 年化 Sharpe ≥ 0 |
| G5 | kill switch 零触发 |

**真金操作（划转/下单）必须你本人确认后我才执行。**

## 6. 常驻与自启

- 已配：`Startup\bnbot_paper.vbs` 开机自启三仓循环 + `bnbot_status.vbs` 自启状态服务
- 手动重启：杀掉旧进程后 `python -m bnbot.live --sleeves --proxy ...`（后台）
- 日志：`logs/paper-loop.log`

## 7. 故障排查

| 症状 | 处理 |
|---|---|
| `-2015 Invalid API-key/IP` | 出口 IP 变了，把新 IP 加白名单（`curl --proxy ... https://api.ipify.org` 查） |
| `451 Service unavailable from restricted location` | 出口节点被币安地域风控，换节点 |
| 划转报 `331025` | 股票 T+1 结算未完成，等结算自动解锁（实测五条路径全锁） |
| 行情抓不到 | 检查代理；数据层会自动降级用缓存，不会中断循环 |
| 启动报错 laya | 判断层可选，缺失自动降级（`state/judgment-log.jsonl` 记 error） |

## 8. 测试与验证

```powershell
python -m unittest discover -s tests      # 66 项
python "C:\Users\21560\AppData\Local\Temp\hermes-verify-bnbot-*.py"   # 留存验证载体，复跑即取证
```

## 9. 数据来源说明

平台不吃任何专有/闭源数据（如幻方量化的训练数据不可得也没必要）：
行情来自交易所公共接口，情绪面来自 X 检索，判断推理来自开源 laya 模型本地推理。
全部可复现、可审计。
