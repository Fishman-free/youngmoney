# vendor/ — 第三方项目引用（2026-09-30 引入）

用户指定引入的四个开源项目。这里只保留**文档与技能定义**（应用本体 16MB 不塞进仓库），
便于离线查阅来源、边界与用法；上游地址见每节。

## global-stock-data　`simonlin1212/global-stock-data`

美股港股全栈数据工具包（Claude Skill）。13 层架构 / 30+ 端点 / 11 数据源 / 全部零鉴权：
行情（新浪、腾讯、东财）、K线（新浪日K、Yahoo chart v8）、技术指标（纯计算）、基本面
（东财 datacenter、Yahoo quoteSummary、SEC EDGAR XBRL）、资金流、期权（Yahoo crumb）、
CBOE 官方期权链、FINRA 做空数据、SEC 申报事件流、美债/CFTC COT/财报日历。

**本项目采用**：
- `bnbot/usstock.py` 的美股日线抓取（Yahoo chart v8 零鉴权 + 东财 push2his 回退）
- 技能已装入 Hermes：`skills/global-stock-data/`（美股/港股分析时自动可用）
- 每个数据源都标注了合规分级——引入新源前先读 SKILL.md 的「数据源合规分级」

## finance-quant-skills　`lzwme/finance-quant-skills`

金融量化 Claude Skills 集合（Agent Skills 标准），13 个技能：akquant、akshare、
backtrader、baostock、jqdatasdk、joinquant-strategy、miniqmt、pywencai、qmt-strategy、
rqalpha、equity-researcher、tdxquant、tushare。

**本项目采用**：
- 全部技能已装入 Hermes：`skills/finance-quant/*`（A股数据源与回测框架知识库）
- 直接可用：`akshare`（含加密货币接口）、`backtrader`/`rqalpha`（回测范式的对照参考）、
  `equity-researcher`（机构级投研报告生成）
- **暂不采用**：`miniqmt` / `qmt-strategy` / `tdxquant`——均为 A 股券商客户端接口，
  需要境内券商账户与客户端环境，与当前加密/美股路线不匹配（要转 A 股时再启用）

## tick-stock-panel　`shy3130/tick-stock-panel`

自托管 A 股智能量化工作台（MIT）：Polars 引擎、61 个 Open API 端点、12 个 MCP 工具、
Docker 单容器、2400+ 测试。

**本项目参考**（架构层面，不直接嵌代码）：
- **MCP 暴露能力**的思路——我们已有 Binance MCP；本项目示范了自建 MCP server
- **Open API 分层 + Token 权限档**的鉴权设计，可用于 `bnbot/server.py` 的后续加固
- Polars 级全市场扫描的性能取舍，对照我们纯标准库的实现边界

## TradingAgents-astock　`simonlin1212/TradingAgents-astock`

TradingAgents（arXiv 2412.20138）的 A 股特化 fork（Apache 2.0）：7 个分析师角色 +
多空辩论 + 风控审议的多智能体投研框架。

**本项目参考**：
- **「分析师角色」= 我们的原子问题电池**：他们用多个角色各自输出结论，我们用
  `bnbot/judgment.py` 一次调用的 regime/toxicity/setup 三问——同一思想的不同实现
- **多空辩论 × 独立风控审议** 的结构，对应我们已落地的 maker-checker
  （`verify.py` 确定性验证 + `judgment.py` 概率判断 + `risk.py` 硬闸），互为印证
- 他们的 LLM 成本/延迟与我们用本地 laya 的取舍差异，是后续要不要升级到多智能体
  辩论的直接对照

## 引入原则

1. **只 vendor 文档，不 vendor 应用**：仓库保持轻量，运行时依赖按需安装
2. **能力先落地代码，再谈集成**：本次落地的实际产出是 `bnbot/usstock.py`（美股数据）
   与两套技能包；其余作为知识库与架构参照
3. **合规**：global-stock-data 明确「只分发代码、不分发数据」，各源条款差异大——
   新增数据源前先核对该源在 SKILL.md 中的合规分级
