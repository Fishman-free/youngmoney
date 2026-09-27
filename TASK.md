# 任务书：Binance 中低频自动化交易平台（paper-first）

## 目标
在本目录（C:\Users\21560\Desktop\binance）从零搭建一个**Binance USDT-M 合约中低频自动化交易平台**，以历史回测 + 纸面交易（paper trading）为第一阶段，年化收益目标 15%+（目标不是承诺，回测要诚实呈现风险）。

## 硬性约束
- Windows + PowerShell 5.1 环境；Python 3.14 在 PATH（`python`）。**只用标准库**（urllib/json/csv/unittest），不 pip install 任何包。
- 网络：本机访问 binance 域名需走代理 `http://127.0.0.1:7890`（fapi.binance.com 直连可能不通）。所有 HTTP 调用读环境变量 `HTTPS_PROXY/HTTP_PROXY`（urllib 默认尊重），并在 README 写明运行前 ` $env:HTTPS_PROXY="http://127.0.0.1:7890" `。为数据抓取脚本提供 `--proxy` 显式开关。
- **禁止**把 API key 写进代码。真实下单（第二阶段）凭据从环境变量 `BN_API_KEY/BN_API_SECRET` 读取；本阶段只实现 paper 引擎，真实执行器只留接口（raise NotImplementedError 或明确 TODO），不要实现签名下单逻辑。
- 代码标识符英文；README.md 用中文。

## 数据源（Binance USDT-M futures 公共 REST，无需鉴权）
- 基址 https://fapi.binance.com
- K线 `/fapi/v1/klines?symbol=&interval=&startTime=&endTime=&limit=1500`（4h 与 1d 为主）
- 资金费率 `/fapi/v1/fundingRate?symbol=&startTime=&endTime=&limit=1000`（8h 一档）
- 指数/溢价 `/fapi/v1/premiumIndex?symbol=`
- 交易规则 `/fapi/v1/exchangeInfo`（取 PRICE_PRECISION / LOT_SIZE 用于下单数量取整）
- 历史数据缓存到 `data/`（CSV，含断点续抓：已有区间不重复抓，注意限速 2400 weight/min，抓取间 sleep）。
- 回测主力标的：BTCUSDT、ETHUSDT、SOLUSDT（流动性最好）；TradFi 永续（AAPLUSDT/SPYUSDT/QQQUSDT/XAUUSDT，实测在列）只在 README 提及为可扩展配置，回测不强制。

## 架构（包名 bnbot/，python -m 方式运行）
1. `bnbot/data.py`：REST 抓取 + CSV 缓存 + 对齐合成 DataFrame-like 结构（用 list[dict] 或简单类即可，别引 pandas）。
2. `bnbot/strategy.py`：策略接口 `target_positions(ctx) -> {symbol: weight}`（权重为账户净值比例，可多空）。
   - 趋势策略：Donchian 通道突破 + EMA(20/50) 过滤，4h 周期；
   - 时序动量：过去 N 日收益率符号决定多空，1d 周期；
   - 资金费率 carry 叠层：资金费率年化 > 阈值时对现货腿做多/对永续做空的正 carry 倾斜（用权重偏移表达，不需要真实双腿记账）。
   - 组合权重在 config 中可调。
3. `bnbot/risk.py`：风控层，硬约束先生效再下单：
   - 总名义杠杆上限（默认 2.0x）；单标的权重上限（默认 0.35）；
   - 日内亏损熔断（当日回撤 > 3% 停止开新仓）；总回撤节流（回撤 > 15% 全部减半仓，> 25% 清仓待命）；
   - kill switch 文件 `KILL_SWITCH`（存在即全平且拒绝一切新仓）。
4. `bnbot/backtest.py`：按时间顺序撮合，费率 taker 5bp + 滑点 2bp，资金费率按 8h 结算对持仓扣/收；输出指标：年化收益、年化波动、Sharpe、Sortino、最大回撤、Calmar、胜率、换手率、暴露度。**必须做滚动样本外验证**（walk-forward：参数在前段选，后段只评估，报告两段）。
5. `bnbot/live.py`：paper 模式循环（默认每 4h 一次）：拉最新数据→算目标仓位→与 `state/portfolio.json` 当前仓位 diff→按 exchangeInfo 取整→模拟成交写 `logs/orders-YYYYMMDD.log`。真钱模式入口留接口不实现。
6. `tests/`：unittest 覆盖：策略信号正确性（构造合成序列断言多空方向）、风控约束（杠杆上限/熔断/kill switch 必须拦截）、回测记账不变量（无交易时净值=初始、手续费扣减正确、资金费率结算方向正确）。
7. `config.yaml`（用 json 也行，标准库）：资本、目标波动率、策略权重、风控参数、标的列表。

## 验收标准（自己先跑通再交付）
- `python -m unittest discover -s tests -v` 全绿；
- `python -m bnbot.data --fetch --proxy http://127.0.0.1:7890` 能抓下至少 2024-01-01 至今的 4h/1d 数据；
- `python -m bnbot.backtest --walk-forward` 输出两段指标表（样本内/样本外），数字来自真实抓取的数据，不许编造；
- `python -m bnbot.live --paper --once` 能跑一轮并写出订单日志；
- README.md：架构图（ASCII）、运行命令、风险声明（历史表现不代表未来、杠杆风险、15% 是目标非承诺）。

## 交付
git init + 一次提交（`git commit -F` 方式写提交信息，见下）。不推送。
