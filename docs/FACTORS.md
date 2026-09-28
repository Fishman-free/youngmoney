# 因子研发笔记（2026-09-28）

## 调研依据

GitHub 检索（crypto quant trading strategy，按 star 排序）头部为 QuantDinger（12.2k）、howtrader（963，51bitquant 的 crypto 量化框架）等，多为执行框架而非因子库。真正可借鉴的因子证据来自机构公开产品与量化从业者一手分享（经 x_search 检索核验）：

1. **资金费率 carry / 期现基差**是机构级核心策略。Bitwise Crypto Carry Fund（USCC，前 Superstate）AUM 超 2.67 亿美元，公开描述为捕捉现货-期货基差与 funding；Hilbert Capital 的 BTC Basis+ 以受监管基金形态运行。容量大，delta-neutral，失效条件为 funding 归零/反转与拥挤滑点。
2. **跨截面动量是 crypto 跨截面里唯一稳健的因子**。X 上量化从业者（blothecap 等 vault 运营者）实盘口径为 cross sectional factors in crypto: only momentum matters；反转因子在 crypto 明显弱于股票。传统动量 2020-2026 在 BTC 上 Sharpe 约 1.0，但存在动量崩盘（熊转牛、高波动 regime）风险，且 alpha 衰减快（有从业者称等策略在推特上出现时，30 亿规模基金已经跑了 14 个月）。
3. **波动率风险溢价**（卖方策略）依赖期权深度与对冲能力，Binance 永续无期权腿，本阶段不实装。
4. **流动性提供/做市**属于执行层高频能力，与中低频定位不符，放弃。

## 本轮实装的自研因子

### XS-MOM（跨截面动量）
宇宙 7 个高流动性永续（BTC/ETH/SOL/AVAX/LINK/XRP/DOGE）。对每个标的取 30 日收益率，在宇宙内做秩排序，做多前 2 名、做空后 2 名，权重和为 0（市场中性），总敞口 xs_weight=0.6。秩打分而非原始值，规避山寨币收益率的肥尾离群值。

### HIGH-52（52 周高点效应）
经典动量变体（George-Hwang 52-week-high），比原始动量更少受路径噪声影响。取收盘价 / 365 日最高价之比做秩排序，同样多头前 2 空头后 2。

### 复合方式
得分 = 0.6 × rank(XS-MOM) + 0.4 × rank(HIGH-52)，秩归一到 [0,1]，两因子同向叠加后取极端分位开仓。与原有方向性仓位（趋势/时序动量/carry）加总后过风控（杠杆 ≤2x、单标的 ≤35%、日亏熔断、回撤节流）。

## 被否决的因子（及理由）

- **短期反转**：调研实盘口径 crypto 反转弱、交易成本侵蚀严重，不实装。
- **基差期限结构择时**：premiumIndex 历史数据 3 分钟粒度、全量回补需数百次请求，本阶段数据管线不支持；funding carry 已部分代理该信息。
- **期权 VRP**：无期权腿。
- **链上巨鲸流**：需要 Glassnode/Nansen 类数据源，暂缺凭据。

## 验证纪律

每个因子必须过 walk-forward（IS 70% 选参 / OOS 30% 评估），样本外不达标即弃。禁止用全样本调参后谎称样本外。
