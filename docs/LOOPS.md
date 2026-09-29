# Loop Engineering 映射（源自 @RohOnChain 2069056530960490835，2026-09-29 学习落地）

文章核心：量化的本质就是循环（数据→信号→验证→执行→风控→重复），loop engineering
把人从循环里拿出来。六件套缺一个循环就会悄悄坏掉。本文记录 bnbot 对六件套的落地位置。

| 六件套 | 文章定义 | bnbot 落地 |
|---|---|---|
| Automation 心跳 | cron/webhook 无人触发 | `paper_loop.ps1`（4h 一轮 + 开机自启）+ `bnbot.sentiment` 每日幂等 |
| Skill 程序手册 | SKILL.md 存规则与教训 | `docs/FACTORS.md`（因子验证纪律）+ 本文件 + 每轮 LESSON 写回 STATE.md |
| State file 记忆 | 跨运行状态 + 审计日志，约 400 行 | `state/portfolio.json`（结构化）+ `state/STATE.md`（叙事审计，滚动 400 行，亏钱时唯一调试面） |
| Verifier 校验者 | maker-checker 分离，maker 不当裁判 | `bnbot/verify.py`（独立确定性规则 D1-D3，逐单过检，拒绝入审计）+ `bnbot/judgment.py`（laya 概率判断层，J1-J4 门控只否决新开仓） |
| Worktrees 隔离 | 多 agent 并行不互踩 | 单进程系统暂不需要；研究/回测/纸面通过进程分离 |
| Connectors 接手 | MCP/交易所 API | `bnbot/data.py` REST + Binance MCP（81 工具） |

## 五阶段对应

数据摄取（refresh_data 自动增量）→ 信号生成（CompositeStrategy）→ **验证（SignalVerifier，不过就杀）** → 执行（paper fills / phase-2 real）→ 风控（RiskManager，kill switch 无协商）→ 教训写回（STATE.md LESSON 行）。

## 停止条件铁律

文章原话：never "the agent says it is done"。实盘前置判据写死在 `bnbot/report.py`，
机器可检验：paper ≥60 天、≥30 笔、回撤 ≤25%、Sharpe ≥0、kill switch 零触发。
当前 verdict 由脚本给出，不由任何人的声称给出。

## 教训写回机制

验证器拒绝开仓单时自动向 STATE.md 追加 LESSON 行（日期、方向、标的、拒绝码）。
亏损轮次的完整现场在 STATE.md 对应段落，配合 logs/orders-*.log 全量回放。
