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
| 状态面板 | http://127.0.0.1:8787/dashboard | **分仓表（A/B/C 各一行 + 汇总）+ 各仓收益指数** |
| 快照 JSON | http://127.0.0.1:8787/ | 同上，给程序读（`mode: "sleeves"`） |
| 审计日志 | `state/sleeves/<id>/STATE.md` | 每轮目标仓位、成交、拒绝原因；亏钱时唯一调试面 |
| 计数器 | `state/sleeves/<id>/metrics.json` | cycles/orders/fills/rejected/late/fees 累计 |
| 订单流水 | `logs/sleeves/<id>/orders-YYYYMMDD.log` | 逐单原始记录 |
| 判断层日志 | `state/sleeves/<id>/judgment-log.jsonl` | laya 每次判断的状态与答案（校准三元组） |
| 情绪记录 | `state/sentiment-shadow.csv` | 每日 X 情绪分（只记录，不参与下单） |

> **面板读哪份数据**：`state/sleeves/` 存在就自动按三仓聚合（各仓权益取该仓
> `STATE.md` 里 live.py 用真实价标记的那条，不在面板里重算）；没有则回落到旧的
> 单账户视图。`--legacy` 可强制后者。取某仓的审计块：
> `http://127.0.0.1:8787/history?sleeve=C&n=5`。

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

**C 仓进真钱的门禁**（脚本化判定，不是感觉）：

```powershell
python -m bnbot.gate --sleeve C          # 人读报告 + 判定
python -m bnbot.gate --sleeve C --json    # 机器读
```

| 门 | 判据 |
|---|---|
| G1 成交数 | ≥ 200 笔 |
| G2 净期望 | > 0（按权益变化 ÷ 笔数） |
| G3 最大回撤 | ≤ 30% |
| G4 急停次数 | = 0 |

**C 仓参数证据（2026-09-30 回测）**：walk-forward 在样本内**否决了快参数**（12/3d），
选中最慢的 donchian=96/mom=30d；OOS 年化 +8.39%/Sharpe 0.41/最大回撤 **-19.89%**。
该回撤发生在 ~0.47 倍平均敞口下，**按 10 倍杠杆放大即强平**。故 C 仓实配杠杆已从
10x 降到 **3x**（代码硬顶 `SLEEVE_CEILINGS["C"]=10x` 保留，改回需你明确点头）。

**注意 `enabled` 的语义**：`enabled: true` = 该仓进入**模拟盘**循环攒证据（包括 C 仓）；
它**不代表可以进真钱**。真钱只有一条路：门禁四门全过 + 你本人明确点头。

**杠杆上限写在 `bnbot/sleeves.py` 的 `SLEEVE_CEILINGS`**，配置只能收紧不能放松——即使改 config 也不会突破 A≤2x / B≤3x / C≤10x 的硬顶。

### 验证器 D2 可按仓收紧（2026-10-06 修复）

`bnbot/verify.py` 的 D2 规则默认 `all`：开新仓要求 **趋势与动量同时** 同向。
C 仓靠"快动量先于趋势确认"入场，在 `all` 下 **24 次拒单 / 0 成交**，
200 笔门禁结构上永远达不到。现在 D2 可按仓配置：

```jsonc
// config.json → sleeves.list[]
{ "id": "C", "verify": { "d2_mode": "mom" }, ... }
```

| 模式 | 规则 |
|---|---|
| `all`（默认） | 趋势 **且** 动量同向 —— A/B 保持此档 |
| `any` | 任一方向一致即可 |
| `mom` | 只看动量（C 仓用） |
| `trend` | 只看趋势 |

**只有显式声明 `verify` 的仓会放宽**；A/B 不声明即继承严格默认。D1（数据健全）
不受影响，风控与判断层照旧一票否决。

同一机制也用于 D3（波动率上限）。C 的山寨宇宙跑得比全域上限热——`QNTUSDT`
年化波动率实测 **3.77**，高于默认 `vol_cap: 2.0`，会被 D3 永久拦下：

```jsonc
{ "id": "C", "verify": { "d2_mode": "mom", "vol_cap": 5.0 }, ... }
```

5.0 仍能拦住真正坏掉的数据（10 倍级），只是不再误杀 QNT 这类高波动标的。
A/B 不声明 `vol_cap`，用 `verify.py` 的 `DEFAULTS`（2.0）。

```powershell
python -m bnbot.sleeves --list                                    # 看三仓参数与配额
python -m bnbot.sleeves --export C --out state/sleeves/C/backtest-config.json
python -m bnbot.backtest --config state/sleeves/C/backtest-config.json --walk-forward
```

## 4. 系统架构（五层，各司其职）

```
数据层 bnbot/data.py        增量抓 K 线/资金费率，网络失败自动降级用缓存；
                            MEXC 回退源；美股走 data/equities/（bnbot/usstock.py）
信号层 bnbot/strategy.py    趋势(Donchian48) + 动量(30d) + 资金费率carry + 跨截面XS
     bnbot/indicators.py    技术指标（MA/EMA/MACD/RSI/KDJ/布林/ATR，纯 Python）
判定层 bnbot/verify.py      确定性验证器 D1-D3（数据/信号一致/波动率），拒绝开新仓
     bnbot/judgment.py      概率判断层 J1-J6（laya 六问电池：regime/toxicity/setup
                            + 分析师三问 trend/risk/flow，角色思想取自 TradingAgents）
风控层 bnbot/risk.py        杠杆/集中度/日亏/回撤 硬闸，kill switch 无协商
执行层 bnbot/live.py        paper 撮合（真执行器 phase-2 待启用）+ 订单生命周期
```

### 美股/港股（2026-09-30 接入）

```powershell
python -m bnbot.usstock --fetch SOXL,ARM --interval 1d --range 5y --derive-4h --proxy http://127.0.0.1:7890
python -m scripts.equity_backtest --symbols SOXL,ARM
```

数据源：Yahoo chart v8（零鉴权）→ 回退东财 push2his。行格式与加密管线一致，
`MarketData.load` 自动识别 `data/equities/` 下的标的（无资金费率，相关因子贡献 0）。

实测（日线，IS/OOS 7:3）：

| 标的 | IS 年化/Sharpe | OOS 年化/Sharpe | OOS 回撤 |
|---|---|---|---|
| SOXL | -2.84% / -0.24 | **+12.56% / 0.90** | 8.05% |
| ARM | +1.86% / 0.25 | **+8.75% / 1.03** | 6.57% |

注意：SOXL 样本内为负说明该配方对**制度（regime）敏感**，样本外好不代表稳健——
这与加密那条线一样，要过门禁而非看单段数字。

### 判断层六问电池（TradingAgents 启发）

| 问题 | 类型 | 作用 |
|---|---|---|
| regime | choice | 制度判定 |
| toxicity | noul | 超买/超卖回撤风险 |
| setup | score 0-3 | 形态质量 |
| trend_analyst | choice | 趋势分析师：方向背离则否决（J5） |
| risk_analyst | noul | 风险分析师：下行风险高则否决（J6） |
| flow_analyst | noul | 资金流分析师：**仅记录不拦截** |

**角色只能否决，不能放大**——这是判断层的第一原则。

优先级：**风控 > 验证器 > 判断层**。任何下层只能否决，不能放大。

#### 🔴 判断层「挂死」防护（2026-10-06 修复，必读）

判断层是可选依赖，设计上「缺失/报错就降级放行」。但**卡死不是异常，`except`
接不住**——实测踩了两次：

1. **`laya.Router()` 构造是瞬间返回的**，真正的模型加载是**惰性的**，发生在
   第一次 `predict()` 内部（`laya/router.py` → `Agent.__init__` → `snapshot_download`）。
   只包住构造函数等于没包。
2. **`hf_xet` 不认 `HTTPS_PROXY`**（`huggingface_hub` ≥ 1.x 默认走 Xet 后端）。
   同一个文件走普通 HTTPS 3.7 秒就下来（HTTP 206），走 Xet 0 字节挂 12 分钟，
   进程 100% idle 在 I/O（线程转储：`httpx → httpcore → ssl.read`）。

后果：有订单要过判断层时，整轮（以及背后的 4h 循环）**永久阻塞**。

现在两道闸：

- `judgment.py` 在 import 前设 `HF_HUB_DISABLE_XET=1`，强制走普通 HTTP 下载
- `ask()` 整体跑在守护线程里，硬时限：首次调用（含惰性加载）`load_timeout_s: 300`，
  热调用 `battery_timeout_s: 10`；超时即标记该引擎本轮作废、**降级放行**，
  并在 `judgment-log.jsonl` 记 `"status": "timeout"`

**排查判断层是否在岗**：看 `state/sleeves/<id>/judgment-log.jsonl` 的 `status`
字段。全是 `ok` = 在岗干活；出现 `timeout` = 引擎挂了在降级；**文件长期不增长 =
这一轮根本没订单过判断层**（10-05 那轮就是这样，掩盖了模型已丢失的事实）。

**模型丢失症状**：offline 加载秒失败 `Incompatible model: 'model.safetensors'
not found`；online 加载则挂死。缓存位置
`<HERMES_HOME>/cache/huggingface/hub/models--convaiinnovations--laya/`，
`model.safetensors` ≈ 803 MB。

## 5. 实盘开关（当前状态：关闭）

实盘门禁写死在 `bnbot/report.py`，全部通过才谈实盘：

```powershell
python -m bnbot.report            # 逐仓判定 + 汇总
python -m bnbot.report --json     # 机器读
python -m bnbot.report --legacy   # 忽略三仓，只看顶层 logs/
```

| 门 | 判据 |
|---|---|
| G1 | paper 运行 ≥ 60 天 |
| G2 | 成交 ≥ 30 笔 |
| G3 | 最大回撤 ≤ 25% |
| G4 | 年化 Sharpe ≥ 0 |
| G5 | kill switch 零触发 |

**逐仓判定**：三仓各跑同一套五门、各出一行结论，**全部 GO 才算整体 GO**——
一仓不合格只挡它自己进真钱。2026-10-06 之前这个脚本只 glob 顶层
`logs/orders-*.log`，把 09-30 之后的三仓轮次**全部漏掉**，报出来的却是一份
"实盘 NO-GO" 裁决；现在读的是 `logs/sleeves/<id>/`。

**真金操作（划转/下单）必须你本人确认后我才执行。**

## 6. 常驻与自启

- 已配：`Startup\bnbot_paper.vbs` 开机自启三仓循环 + `bnbot_status.vbs` 自启状态服务
- 手动重启：杀掉旧进程后 `python -m bnbot.live --sleeves --proxy ...`（后台）
- 日志：`logs/paper-loop.log`

**每轮开跑前先探测数据源就绪**（2026-10-06 加）：

```
[skip] 数据源不可达（代理 http://127.0.0.1:7890，已探测 N 次 / 10 分钟）：
       跳过本轮，避免用陈旧缓存写假数据；4h 后重试。检查 Clash/代理是否在跑。
```

探测口径与数据层一致：**主源（币安）或备用源（MEXC）任一连通即可开跑**
（币安 451 期间本来就走 MEXC 回退，不该因此停摆）。探测不到就跳过本轮，
不往 `STATE.md` 的权益序列里塞一个用陈旧价格标记出来的假点。

> **为什么加**：2026-10-05 实测事故——机器 23:31:27 开机、循环 23:32:14 起来，
> 但代理 23:46:53 才起。首轮所有行情请求被拒（WinError 10061），全程读了
> **10-02 的缓存**，把一个假权益点写进了审计日志。

**开机时序提醒**：代理（Clash Verge）比循环晚起十来分钟是常态，所以循环等它，
而不是硬跑。

## 7. 故障排查

| 症状 | 处理 |
|---|---|
| `-2015 Invalid API-key/IP` | 出口 IP 变了，把新 IP 加白名单（`curl --proxy ... https://api.ipify.org` 查） |
| `451 Service unavailable from restricted location` | 出口节点被币安地域风控，换节点（数据层自动走 MEXC） |
| 划转报 `331025` | 股票 T+1 结算未完成，等结算自动解锁（实测五条路径全锁） |
| 行情抓不到 | 检查代理；数据层会自动降级用缓存，不会中断循环 |
| 循环日志出现 `[skip] 数据源不可达` | 代理没起或挂了。循环**故意不跑**（避免假数据），起代理后下一轮自愈 |
| 面板显示的是旧的单账户数字 | 面板按三仓聚合要有 `state/sleeves/<id>/`。查 `--legacy` 是否被传了；或那份 `state/portfolio.json` 本就没在更新 |
| `report.py` 报的数字和面板对不上 | 2026-10-06 前 `report.py` 只读顶层 `logs/`。现在默认逐仓；`--legacy` 才是旧口径 |
| 面板风控一直显示"正常"但确实熔断了 | 旧版把 `kill_switch` 硬编码为 False，已修；现在是真去查 KILL_SWITCH 文件 |
| 启动报错 laya | 判断层可选，缺失自动降级（`judgment-log.jsonl` 记 error） |
| 某仓一直不成交 | 看该仓 `STATE.md` 的 `REJ` 行：`D2` 是信号不一致、`D3` 是波动率超限、`J*` 是判断层否决。C 仓的 QNT 会稳定被 D3 拦（vol 3.77 > 2.0） |

## 8. 测试与验证

```powershell
python -m pytest -q                       # 119 项（canonical）
python -m unittest discover -s tests      # 119 项（tox 第二 runner）
python "C:\Users\21560\AppData\Local\Temp\hermes-verify-*.py"   # 留存验证载体，复跑即取证
```

## 9. 数据来源说明

平台不吃任何专有/闭源数据（如幻方量化的训练数据不可得也没必要）：
行情来自交易所公共接口，情绪面来自 X 检索，判断推理来自开源 laya 模型本地推理。
全部可复现、可审计。
