---
name: global-stock-data
description: 美股港股全栈数据工具包（官方源优先）— 十三层架构·30+端点·11数据源·全部零鉴权。在原有行情/K线/技术指标(MA/MACD/RSI/KDJ/布林带)/基本面/资金面/期权/SEC Filing/工具八层之上，新增：CBOE官方期权链(完整希腊字母+IV+0DTE流+异动识别)、FINRA全市场每日空头成交量、SEC EDGAR申报事件流(Form4内部人/8-K/13F机构持仓)、EDGAR全市场横截面筛选、美债收益率曲线/CFTC COT/财报日历。每个数据源标注合规级别与条款原文。内嵌全部调用代码，自包含零依赖外部文件。适用于美股港股个股分析、全市场筛选、财报解读、期权与0DTE策略、做空数据追踪、SEC文件检索、资金流与机构持仓分析等场景。
origin: custom
version: 2.0.3
---

> 📦 项目主页：https://github.com/simonlin1212/global-stock-data — 更新、反馈、支持作者
> 
> 作者：Simon 林 · X [@linsizhen](https://x.com/linsizhen) · 邮箱：simonlin0423@gmail.com

# 美股港股全栈数据工具包 V2.0 — 官方源优先

十三层数据架构，30+ 个端点，11 个数据源，全部零鉴权，实测可用（2026-07-24 全量回归验证）。

**V2.0 设计原则：官方源优先。** 新增层的主力数据取自美国政府（SEC EDGAR / Treasury / CFTC）、
自律组织（FINRA）与交易所（CBOE / Nasdaq）的公开端点。**每个数据源都标注了合规级别与条款原文**
（见下方「数据源合规分级」）——"官方"不等于"可自由使用"，各源差异极大。

**本工具只分发代码，不分发、不转售任何市场数据**；数据由使用者自行按各源条款获取。

**使用方式：** 将本文件放入 `~/.claude/skills/global-stock-data/SKILL.md`，Claude Code 会自动识别并在美股/港股相关对话中激活。

```
行情层（实时/延时）
├── 新浪财经     → 美股 gb_XXXX 36字段 / 港股 rt_hkXXXXX 25字段
├── 腾讯财经     → 美股 usXXXX 71字段 / 港股 r_hkXXXXX 78字段
└── 东财 push2   → 美股/港股 secid 实时行情，含中文名/涨跌幅/换手率

K线层（日/周/月/分钟）
├── 新浪          → 美股日K (回溯至1984年)
└── Yahoo chart   → 美股+港股 (v8 API, 零crumb)

技术指标层（纯计算，零额外依赖）
└── MA/EMA + MACD + RSI + KDJ + 布林带    基于K线OHLCV，纯Python计算

基本面层
├── 东财 datacenter → 美股/港股三表(资产负债+利润+现金流) + GMAININDICATOR(关键指标)
├── Yahoo crumb     → 23个模块(财务数据+关键指标+分析师+机构持仓)
└── SEC EDGAR XBRL  → 美股503个GAAP指标 (仅美股)

资金面层
└── 东财 push2his → 日级资金流(主力/大单/中单/小单) 美股+港股

期权层（仅美股）
└── Yahoo crumb → 期权链(calls+puts, 所有到期日) 仅美股(港股期权不在Yahoo覆盖范围)

SEC Filing层（仅美股）
├── EDGAR submissions → 10-K/10-Q/8-K 完整Filing列表
└── EDGAR XBRL        → 结构化财务指标(营收/净利/EPS等)

工具层
├── 东财 search    → 股票搜索(中英文, 含市场代码映射)
├── 东财 push2     → 全市场股票列表(涨跌幅/成交量排名, 美股5925只+港股18000+只)
├── Yahoo search   → 新闻资讯(按股票代码)
└── SEC CIK mapping → ticker↔CIK 映射 (仅美股)

━━━ 以下为 V2.0 新增（官方源优先）━━━

期权层·CBOE 官方（仅美股）⭐
└── CBOE cdn → 全链 + IV + delta/gamma/vega/theta/rho + 0DTE + 异动flow   [C级·需授权]

做空层（仅美股）⭐
└── FINRA Reg SHO → 全市场每日空头成交量(实测12,112只) + 个股时序 + 排行  [B级]

申报事件流（仅美股）⭐
├── EDGAR 每日索引 → Form4内部人/8-K/13F机构持仓/144，当日全量           [S级]
└── EDGAR 全文检索 → 2001至今所有申报正文，按关键词+表单+日期            [S级]

全市场横截面（仅美股）⭐
└── EDGAR frames → 任意XBRL标签一次拿全市场(实测1,842~5,309家)=免费screener [S级]

宏观 / 日历 ⭐
├── Treasury → 美债收益率曲线(1M~30Y, 每日)                             [S级]
├── CFTC     → COT 持仓报告                                             [S级]
└── Nasdaq   → 财报日历(含盘前盘后+EPS预期)                             [C级·未核实]
```

---

## 端点路由速查（按需定位，不必通读全文）

| 我想要… | 去哪层 | 主力源 | 合规级 |
|---|---|---|---|
| 实时/延时报价 | Layer 1 | 新浪 / 腾讯 / 东财 | C |
| K 线（日/周/月） | Layer 2 | 新浪 / Yahoo | C |
| 技术指标 MA/MACD/RSI/KDJ/布林 | Layer 3 | 本地计算 | — |
| 财报三表 / 关键指标 / 分析师 / 机构持仓 | Layer 4 | 东财 / Yahoo / EDGAR | C·S |
| 日级资金流 | Layer 5 | 东财 | C |
| **期权链 + 希腊字母 + IV + 0DTE + 异动flow** | **Layer 6.1** | **CBOE 官方** ⭐ | C |
| 期权链（无希腊字母，后备） | Layer 6.2 | Yahoo | C |
| 10-K/10-Q/8-K 列表、XBRL 财务 | Layer 7 | SEC EDGAR | **S** |
| 搜索 / 新闻 / CIK 映射 / 全市场列表 | Layer 8 | 东财 / Yahoo / SEC | C·S |
| **全市场每日空头成交量、个股空头占比** | **Layer 9** | **FINRA Reg SHO** ⭐ | B |
| **当日申报流：Form 4 内部人 / 8-K / 13F** | **Layer 10.1** | **EDGAR 每日索引** ⭐ | **S** |
| **申报全文检索（2001 至今正文）** | **Layer 10.2** | **EDGAR FTS** ⭐ | **S** |
| **全市场基本面横截面（免费 screener）** | **Layer 11** | **EDGAR frames** ⭐ | **S** |
| 美债收益率曲线 / CFTC COT / 财报日历 | Layer 12 | Treasury / CFTC / Nasdaq | S·C |

⭐ = V2.0 新增，且为 yfinance 与多数开源方案不具备的能力。

---

## 数据源合规分级（取用前必读 — 各级均引条款原文）

> 下表结论来自 **2026-07-24 逐家实读各源条款原文**，不是推断。引号内为原文。
> **各源差异极大，"官方"不等于"可自由使用"。**

### S 级 — 可自由使用（含商用与再分发）

| 源 | 依据（原文） |
|---|---|
| **SEC EDGAR** | 官网明示：*"Anyone can access and download this information **for free**"*、*"We **allow scripted access** to sec.gov content"*。**硬性要求**：`Current max request rate: 10 requests/second`，且必须声明 User-Agent（格式 `Company Name AdminContact@domain.com`），否则触发 *"Undeclared Automated Tool"* / Access Denied |
| **US Treasury / CFTC** | 美国联邦政府作品不受版权保护（17 U.S.C. §105）。⚠️ 本次**未逐条核验**两站条款正文，按政府数据惯例归此级 |

### B 级 — 数据文件系主动公开，但站点条款含限制

| 源 | 依据（原文） |
|---|---|
| **FINRA** | Reg SHO 每日文件是 FINRA 主动发布供下载的监管披露文件；但其 Terms of Use 同时禁止 *"use any process to monitor or copy the FINRA Website **in bulk**, or use any **data mining, scraping or harvesting tools (including robots)**"*，且站点声明 *"FINRA Data provides **non-commercial use** of data"*。→ **下载已发布的数据文件属常规用法；批量爬站点页面不属于。商用前请自行向 FINRA 确认。** |

### C 级 — 使用需事先授权，或条款未核实

| 源 | 依据（原文） |
|---|---|
| **CBOE** | Use of Content 政策：使用任何 Cboe Content 须 *"receive **approval in advance** from Cboe"*，并须 *"**execution of a license agreement**"*；政策**不区分**商用/非商用、不区分实时/延时。→ **本工具的 CBOE 期权层仅供个人研究；商业用途或再分发前，须先向 Cboe 申请授权。** |
| **Nasdaq** | 本次抓取条款页超时，**未核实**。按未核实处理 |
| Yahoo / 东财 / 新浪 / 腾讯 | Yahoo 官方文档写明 **personal use only**；其余为站点前端接口。仅供个人研究，勿用于商业产品或再分发 |

### ⛔ 已排除的源

| 源 | 原因 |
|---|---|
| **HKEX（CCASS 港股席位持股）** | 其 Terms of Use 明文禁止 *"any '**robot**', '**bot**', '**spider**', '**scraper**' or other automated device... to access, obtain, copy, monitor or republish any portion of the Website"*，禁止 *"text or data mining or web scraping"*，且适用于 *"**whether or not for gain**"*（不论是否营利）。→ **本工具不提供 CCASS 抓取代码。** 需要港股席位持股/南向资金数据者，请通过 HKEX 授权渠道或其网页人工查询 |

### 给使用者的三条硬规则

1. **商业用途**：只依赖 **S 级**（SEC EDGAR / Treasury / CFTC）。B 级需自行确认，C 级须先取得授权。
2. **再分发**：本工具**只分发代码，不分发任何市场数据**。你也不应把 B/C 级源取得的数据对外分发。
3. **限速**：所有新增层的请求已内置节流（见「统一 HTTP 层」）。**不要绕过它**——SEC 的 10 req/s 是官方硬上限。

---

## When to Activate

- 用户要查**美股/港股**行情（价格/涨跌幅/成交量）
- 用户要拉 K 线（日线/周线/月线/分钟线）
- 用户要看**财报**（资产负债表/利润表/现金流量表）
- 用户要看**关键财务指标**（PE/PB/ROE/利润率/目标价）
- 用户要看**分析师预期**（EPS预测/评级/目标价区间）
- 用户要看**机构持仓**（前十大机构/持股比例）
- 用户要看**资金流向**（主力/大单/中单/小单净流入）
- 用户要查**期权链**（calls/puts/到期日/Greeks）
- 用户要查 **SEC Filing**（10-K/10-Q/8-K/年报/季报）
- 用户要做**美股财报量化分析**（从 XBRL 拉多年营收/净利/EPS 趋势）
- 用户要**搜索股票**（中英文均可）
- 用户要看**美股/港股新闻**
- 用户要看**全市场涨跌幅排名**（当日涨幅/跌幅最大的股票）
- 用户要做**全市场筛选**（遍历美股/港股列表做初筛）
- 用户要看**关键财务指标概览**（营收/净利/EPS/ROE/ROA/资产负债率 中文版）
- 用户要看**技术指标**（MACD/RSI/KDJ/布林带/均线）
- 用户要判断**金叉死叉/超买超卖/变盘信号**
- 关键词：美股、港股、AAPL、苹果、腾讯、00700、TSLA、特斯拉、BABA、阿里巴巴、行情、K线、财报、PE、PB、ROE、分析师、目标价、期权、call、put、SEC、10-K、年报、季报、资金流、主力、机构持仓、新闻、涨幅排名、全市场、筛选、关键指标、MACD、RSI、KDJ、布林带、均线、金叉、死叉、超买、超卖、技术分析

---

## Prerequisites

```bash
pip install requests
```

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| requests | any | 所有 HTTP API 直连 |

> **极简依赖：** 仅需 requests，所有数据源均为直连 HTTP API，零第三方数据封装。

---

## 市场代码规则

### 东财 secid 前缀（push2/push2his 用）

| 前缀 | 市场 | 示例 |
|------|------|------|
| 105 | 美股 NASDAQ | `105.AAPL`, `105.TSLA` |
| 106 | 美股 NYSE | `106.BABA`, `106.JD` |
| 107 | 美股 ETF/其他 | `107.CRSH` |
| 116 | 港股 | `116.00700`, `116.09988` |

> **如何判断 105/106/107？** 调 `stock_search()` 获取 `MktNum` 字段自动映射。

### Yahoo Finance 代码格式

| 市场 | 格式 | 示例 |
|------|------|------|
| 美股 | 直接 ticker | `AAPL`, `TSLA`, `BABA` |
| 港股 | 四/五位数字 + `.HK` | `0700.HK`, `9988.HK` |

### 东财 datacenter SECUCODE 格式

| 市场 | 格式 | 示例 |
|------|------|------|
| 美股 NASDAQ | `TICKER.O` | `AAPL.O`, `TSLA.O` |
| 美股 NYSE | `TICKER.N` | `BABA.N`, `JD.N` |
| 港股 | `CODE.HK` | `00700.HK`, `09988.HK` |

---

## 共用 Helper 函数

### Yahoo Finance crumb 管理器

Yahoo quoteSummary/options 等 v7/v10 接口需要 cookie+crumb。以下 helper 自动获取并缓存：

```python
import requests

_yahoo_session = None

def get_yahoo_session() -> requests.Session:
    """获取带 crumb 的 Yahoo Finance session（自动缓存）"""
    global _yahoo_session
    if _yahoo_session and hasattr(_yahoo_session, '_crumb'):
        return _yahoo_session
    
    s = requests.Session()
    s.headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    
    # Step 1: 获取 cookie
    s.get('https://fc.yahoo.com', timeout=10)
    
    # Step 2: 获取 crumb
    r = s.get('https://query2.finance.yahoo.com/v1/test/getcrumb', timeout=10)
    r.raise_for_status()
    s._crumb = r.text
    
    _yahoo_session = s
    return s

def yahoo_quote_summary(symbol: str, modules: list[str]) -> dict:
    """Yahoo quoteSummary 统一查询"""
    s = get_yahoo_session()
    r = s.get(f'https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}', params={
        'modules': ','.join(modules),
        'crumb': s._crumb,
    }, timeout=15)
    r.raise_for_status()
    results = r.json().get('quoteSummary', {}).get('result', [{}])
    return results[0] if results else {}
```

### 东财数据中心统一查询

```python
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

def eastmoney_datacenter(report_name: str, columns: str = "ALL",
                          filter_str: str = "", page_size: int = 50,
                          sort_columns: str = "", sort_types: str = "-1") -> list[dict]:
    """东财数据中心统一查询"""
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = requests.get(DATACENTER_URL, params=params, headers={"User-Agent": UA}, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []
```

---

### 官方源统一出口（限流 + UA 声明）— V2.0 新增

V2.0 新增的 Layer 9–12 全部走这个出口。它负责三件事：**按源限速**、**SEC User-Agent 声明**、
**友好错误提示**。

> ⚠️ **使用前必改**：把 `SEC_CONTACT` 换成你自己的真实姓名与邮箱。
> SEC 官方要求声明 User-Agent，未声明会被判定为 *Undeclared Automated Tool* 并拒绝服务。

```python
import requests, time, threading

# ⚠️⚠️ 必改：SEC 要求 UA 含真实联系方式，格式 "Company Name AdminContact@domain.com"
SEC_CONTACT = "your-name your-email@example.com"


class DataNotAvailable(RuntimeError):
    """该日/该标的确实没有数据（如非交易日、文件尚未发布）——可安全回退到下一个候选日。

    与配置错误、网络错误区分开：后者必须立刻抛给调用方，
    否则「SEC_CONTACT 没配」会被日期回退循环吞掉，最后伪装成「没找到数据」。
    """


class _RateLimiter:
    """线程安全的最小间隔节流器（用锁，避免并发下被击穿）"""

    def __init__(self, max_per_sec: float):
        self._interval = 1.0 / float(max_per_sec)
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            gap = self._interval - (time.monotonic() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()


# 各源限速：SEC 官方硬上限 10/s，此处取 8/s 留余量；其余为自律保护值
_LIMITS = {
    "sec.gov": _RateLimiter(8),
    "finra.org": _RateLimiter(4),
    "cboe.com": _RateLimiter(4),
    "nasdaq.com": _RateLimiter(2),
    "_default": _RateLimiter(5),
}


def _limiter_for(url: str) -> _RateLimiter:
    for host, lim in _LIMITS.items():
        if host != "_default" and host in url:
            return lim
    return _LIMITS["_default"]


def _is_object_missing(resp) -> bool:
    """
    正向识别「资源确实不存在」。

    ⚠️ SEC Archives 与 FINRA CDN 都托管在 S3 上，而 S3 在调用方没有
    ListBucket 权限时，对**不存在的对象**返回 `403 AccessDenied`（XML）
    而不是 404 NoSuchKey。实测 2026-07-24 两个源行为一致。

    真正的拒绝长得完全不同（SEC 的 UA 未声明返回 ~4.8KB HTML 页面），
    所以这里按 Content-Type + XML 错误码正向判定，
    而不是用「排除法」——否则限流/封禁会被伪装成「没数据」。
    """
    if resp.status_code == 404:
        return True
    if resp.status_code != 403:
        return False
    ctype = (resp.headers.get("Content-Type") or "").lower()
    head = (resp.text or "")[:500]
    return "xml" in ctype and "<Code>AccessDenied</Code>" in head


def official_get(url: str, params: dict = None, headers: dict = None,
                 timeout: int = 30, as_json: bool = False):
    """
    V2.0 官方源统一出口：自动节流 + UA 处理 + 友好错误。
    as_json=True 返回 dict，否则返回 str。

    异常语义：资源不存在 → DataNotAvailable（调用方可回退到下一个候选日）；
             配置/限流/网络 → RuntimeError（必须冒泡）。
    """
    if "sec.gov" in url:
        if "your-email@example.com" in SEC_CONTACT:
            raise RuntimeError(
                "请先把 SEC_CONTACT 改成你的真实姓名与邮箱 —— SEC 要求声明 "
                "User-Agent，否则返回 Undeclared Automated Tool 错误。")
        h = {"User-Agent": SEC_CONTACT, "Accept-Encoding": "gzip, deflate"}
    else:
        h = {"User-Agent": UA}
    h.update(headers or {})

    _limiter_for(url).wait()
    try:
        r = requests.get(url, params=params, headers=h, timeout=timeout)
        r.raise_for_status()
    except requests.HTTPError as e:
        resp = e.response
        code = resp.status_code
        low = (resp.text or "")[:4000].lower()
        # ① 正向识别：资源确实不存在（404，或 S3 风格的 403 AccessDenied）
        if _is_object_missing(resp):
            raise DataNotAvailable(
                f"HTTP {code} {url[:80]} — 资源不存在（该日无数据/尚未发布）") from e
        # ② SEC 的 UA 未声明（返回 HTML 页，含 Undeclared Automated Tool）
        if code == 403 and "undeclared" in low:
            raise RuntimeError(
                f"SEC 拒绝请求：User-Agent 未被识别为已声明。"
                f"当前 SEC_CONTACT={SEC_CONTACT!r}，"
                f"格式应为 'Company Name AdminContact@domain.com'") from e
        # ③ 其余一律视为真错误，必须冒泡（限流/封禁/权限/接口变更）
        hint = {403: "被拒绝：限流、封禁或权限问题（已排除「资源不存在」）",
                404: "端点不存在：接口可能已变更",
                429: "请求过快：已内置节流，若仍触发请调低 _LIMITS"}.get(code, "")
        raise RuntimeError(f"HTTP {code} {url[:80]} — {hint}") from e
    except requests.RequestException as e:
        raise RuntimeError(f"请求失败 {url[:80]} — {type(e).__name__}: {e}") from e
    return r.json() if as_json else r.text


# ── 异常约定（V2.0）──
#   DataNotAvailable : 该日/该标的确实没有数据（非交易日、文件未发布、标的无期权…）
#                      → 调用方可安全回退到下一个候选日
#   RuntimeError     : 配置错误（SEC_CONTACT 未改）、限流、网络故障
#                      → 必须冒泡给使用者，不可伪装成「没数据」
#   ValueError       : 参数错误（如把港股代码传给仅支持美股的层）


def assert_us_ticker(ticker: str) -> str:
    """Layer 6.1 / 9 / 10 / 11 仅支持美股；传入港股代码时给出明确提示"""
    t = str(ticker).upper()
    if t.endswith(".HK") or (t.isdigit() and len(t) in (4, 5)):
        raise ValueError(f"'{ticker}' 看起来是港股代码；该层仅支持美股。"
                         f"港股请用 Layer 1-5 的港股端点。")
    if not t.replace(".", "").replace("-", "").isalnum():
        raise ValueError(f"无效的 ticker: '{ticker}'")
    return t
```

> `requests` 会自动解压 gzip 响应，因此上面带 `Accept-Encoding` 是安全的。
> 若你改用 `urllib` 自行实现，**必须手动 `gzip.decompress`**，否则 SEC 返回的内容会解析失败。

---

## Layer 1: 行情层

### 1.1 美股实时行情 — 新浪 + 腾讯

两个独立数据源，任一可用即可。新浪字段侧重价格成交，腾讯字段更全（含52周高低/市值/PE）。

```python
import requests, re

def us_stock_quote_sina(ticker: str) -> dict:
    """
    新浪美股行情 — 36字段
    ticker: 纯字母，如 "AAPL", "TSLA", "BABA"
    """
    url = f"https://hq.sinajs.cn/list=gb_{ticker.lower()}"
    r = requests.get(url, headers={
        "Referer": "https://finance.sina.com.cn/",
        "User-Agent": UA,
    }, timeout=10)
    r.encoding = "gbk"
    text = r.text
    
    m = re.search(r'"(.+)"', text)
    if not m:
        return {}
    
    fields = m.group(1).split(",")
    if len(fields) < 30:
        return {}
    
    return {
        "name": fields[0],           # 中文名
        "price": float(fields[1]),    # 最新价
        "change_pct": float(fields[2]),  # 涨跌幅 %
        "timestamp": fields[3],       # 时间
        "prev_close": float(fields[26]),  # 昨收
        "open": float(fields[5]),     # 开盘
        "high": float(fields[6]),     # 最高
        "low": float(fields[7]),      # 最低
        "volume": float(fields[10]) if fields[10] else 0,  # 成交量
        "high_52w": float(fields[8]) if fields[8] else 0,  # 52周最高
        "low_52w": float(fields[9]) if fields[9] else 0,   # 52周最低
        "market_cap": float(fields[12]) if fields[12] else 0,  # 市值
        "eps": float(fields[13]) if fields[13] else 0,  # EPS
        "pe": float(fields[14]) if fields[14] else 0,   # PE
    }


def us_stock_quote_tencent(ticker: str) -> dict:
    """
    腾讯美股行情 — 71字段
    ticker: 纯字母，如 "AAPL"
    """
    url = f"https://qt.gtimg.cn/q=us{ticker.upper()}"
    r = requests.get(url, timeout=10)
    r.encoding = "gbk"
    text = r.text
    
    m = re.search(r'"(.+)"', text)
    if not m:
        return {}
    
    fields = m.group(1).split("~")
    if len(fields) < 52:   # 需读到 fields[51](PB)，美股正常返回 71 个
        return {}
    
    # ⚠️ 下标以实测为准，勿照抄港股那套（两市布局不同，见本节末「腾讯行情字段对照表」）
    return {
        "name": fields[1],           # 中文名
        "name_en": fields[46],       # 英文名，如 "Apple Inc."
        "price": float(fields[3]) if fields[3] else 0,
        "prev_close": float(fields[4]) if fields[4] else 0,
        "open": float(fields[5]) if fields[5] else 0,
        "volume": int(float(fields[6])) if fields[6] else 0,
        "high": float(fields[33]) if fields[33] else 0,
        "low": float(fields[34]) if fields[34] else 0,
        "high_52w": float(fields[48]) if fields[48] else 0,
        "low_52w": float(fields[49]) if fields[49] else 0,
        "change_pct": float(fields[32]) if fields[32] else 0,
        "float_market_cap": float(fields[44]) if fields[44] else 0,  # 流通市值，亿美元
        "market_cap": float(fields[45]) if fields[45] else 0,        # 总市值，亿美元
        "eps": float(fields[47]) if fields[47] else 0,
        "pe": float(fields[39]) if fields[39] else 0,
        "pb": float(fields[51]) if fields[51] else 0,
        "currency": fields[35],      # "USD"
        "timestamp": fields[30],
    }
```

### 1.2 港股实时行情 — 腾讯 + 新浪

```python
def hk_stock_quote_tencent(code: str) -> dict:
    """
    腾讯港股行情 — 78字段（最全）
    code: 五位数字，如 "00700", "09988"
    """
    url = f"https://qt.gtimg.cn/q=r_hk{code}"
    r = requests.get(url, timeout=10)
    r.encoding = "gbk"
    text = r.text
    
    m = re.search(r'"(.+)"', text)
    if not m:
        return {}
    
    fields = m.group(1).split("~")
    if len(fields) < 76:   # 需读到 fields[75](币种)，港股正常返回 78 个
        return {}
    
    # ⚠️ 下标以实测为准，与美股那套不同（见本节末「腾讯行情字段对照表」）
    return {
        "name": fields[1],           # 中文名
        "code": fields[2],           # 五位代码，如 "00700"（旧版误当英文名）
        "name_en": fields[46],       # 英文名，如 "TENCENT"
        "price": float(fields[3]) if fields[3] else 0,
        "prev_close": float(fields[4]) if fields[4] else 0,
        "open": float(fields[5]) if fields[5] else 0,
        "high": float(fields[33]) if fields[33] else 0,
        "low": float(fields[34]) if fields[34] else 0,
        "volume": int(float(fields[6])) if fields[6] else 0,  # 成交量(股)
        "amount": float(fields[37]) if fields[37] else 0,     # 成交额
        "change_pct": float(fields[32]) if fields[32] else 0,
        "pe": float(fields[39]) if fields[39] else 0,
        "pb": float(fields[58]) if fields[58] else 0,
        "high_52w": float(fields[48]) if fields[48] else 0,
        "low_52w": float(fields[49]) if fields[49] else 0,
        "float_market_cap": float(fields[44]) if fields[44] else 0,  # 流通市值，亿港元
        "market_cap": float(fields[45]) if fields[45] else 0,        # 总市值，亿港元
        "currency": fields[75],      # "HKD"
        "timestamp": fields[30],
    }


def hk_stock_quote_sina(code: str) -> dict:
    """
    新浪港股行情 — 25字段
    code: 五位数字，如 "00700"
    """
    url = f"https://hq.sinajs.cn/list=rt_hk{code}"
    r = requests.get(url, headers={
        "Referer": "https://finance.sina.com.cn/",
        "User-Agent": UA,
    }, timeout=10)
    r.encoding = "gbk"
    text = r.text
    
    m = re.search(r'"(.+)"', text)
    if not m:
        return {}
    
    fields = m.group(1).split(",")
    if len(fields) < 15:
        return {}
    
    return {
        "name_en": fields[0],
        "name": fields[1],           # 中文名
        "open": float(fields[2]) if fields[2] else 0,
        "prev_close": float(fields[3]) if fields[3] else 0,
        "high": float(fields[4]) if fields[4] else 0,
        "low": float(fields[5]) if fields[5] else 0,
        "price": float(fields[6]) if fields[6] else 0,
        "change": float(fields[7]) if fields[7] else 0,
        "change_pct": float(fields[8]) if fields[8] else 0,
        "volume": float(fields[12]) if fields[12] else 0,
        "amount": float(fields[11]) if fields[11] else 0,
    }
```

#### 腾讯行情字段对照表（`qt.gtimg.cn` · 2026-07-26 实测校准）

⚠️ **美股与港股的字段布局不同，不能共用一套下标。** 美股返回 71 个字段，港股 78 个。
下面每个下标都以真实响应逐个核对过（`usAAPL` / `hk00700`），网上流传的映射表多处有误。

| 含义 | 美股下标 | 港股下标 | 实测值（AAPL / 00700） |
|---|---|---|---|
| 中文名 | 1 | 1 | 苹果 / 腾讯控股 |
| 代码 | 2 | 2 | AAPL.OQ / 00700 |
| **英文名** | **46** | **46** | Apple Inc. / TENCENT |
| 现价 | 3 | 3 | 333.02 / 434.600 |
| 昨收 / 今开 | 4 / 5 | 4 / 5 | — |
| 成交量 | 6 | 6 | ⚠️ 港股带小数位（`22959603.0`），必须 `int(float(x))` |
| 涨跌幅 % | 32 | 32 | 3.53 / -2.38 |
| 当日最高 / 最低 | 33 / 34 | 33 / 34 | — |
| **币种** | **35** | **75** | USD / HKD |
| **PE** | **39** | **39** | 40.32 / 15.87 |
| **流通市值**（亿本币） | **44** | **44** | 48881.62 / 39516.08 |
| **总市值**（亿本币） | **45** | **45** | 48911.83 / 39516.08 |
| EPS | 47 | — | 8.26（333.02 ÷ 8.26 = 40.32 ✓ 与 PE 自洽） |
| **52 周最高 / 最低** | **48 / 49** | **48 / 49** | 334.99·200.72 / 677.7·411.0 |
| **PB** | **51** | **58** | 45.93 / 3.14 |

**市值单位是「亿本币」，不是股数**：AAPL 总市值 48911.83（亿美元）= 现价 333.02 × 总股本 14,687,356,000，可用 `fields[62]` 的总股本反算核对。港股同理，单位为亿港元。

**自行复现命令**（行号 N ↔ 数组下标 N−1）：

```bash
curl -s "https://qt.gtimg.cn/q=usAAPL"  | iconv -f GBK -t UTF-8 | tr '~' '\n' | cat -n
curl -s "https://qt.gtimg.cn/q=hk00700" | iconv -f GBK -t UTF-8 | tr '~' '\n' | cat -n
```

> 港股 `hk` 与 `r_hk` 两种前缀返回的字段布局完全一致（均 78 个），可互换。
> 感谢 [@HoRiZonn0](https://github.com/HoRiZonn0) 在 issue #2 中提供的完整对照，本表据此逐条复测后修订。

### 1.3 东财 push2 实时行情 — 美股 + 港股

东财 push2 接口，通过 secid 统一查询美股/港股实时行情。优点：有中文名、换手率、涨跌幅，且 secid 可由 `stock_search()` 自动获取。

```python
def stock_quote_eastmoney(ticker_or_code: str, secid_prefix: int = 105) -> dict:
    """
    东财 push2 实时行情 — 美股+港股统一接口
    美股: stock_quote_eastmoney("AAPL", 105)  # NASDAQ
          stock_quote_eastmoney("BABA", 106)  # NYSE
    港股: stock_quote_eastmoney("00700", 116)
    返回: 最新价/开高低收/成交量/成交额/换手率/涨跌幅/中文名
    
    secid_prefix 说明: 105=NASDAQ, 106=NYSE, 107=US_ETF, 116=港股
    如不确定前缀，先调 stock_search() 获取 mkt_num
    """
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "secid": f"{secid_prefix}.{ticker_or_code}",
        "fields": "f43,f44,f45,f46,f47,f48,f55,f57,f58,f59,f60,f170",
    }
    r = requests.get(url, params=params, timeout=10)
    d = r.json().get("data")
    if not d:
        return {}
    
    # f59 = 小数位数, 价格字段需除以 10^f59 还原真实值
    dec = d.get("f59", 3)
    divisor = 10 ** dec
    
    def _p(key):
        v = d.get(key)
        if v is None or v == "-":
            return None
        return round(v / divisor, dec)
    
    return {
        "code": d.get("f57"),           # 股票代码
        "name": d.get("f58"),           # 中文名
        "price": _p("f43"),             # 最新价
        "high": _p("f44"),              # 最高
        "low": _p("f45"),               # 最低
        "open": _p("f46"),              # 开盘
        "volume": d.get("f47"),         # 成交量(股)
        "amount": d.get("f48"),         # 成交额
        "turnover_rate": d.get("f55"),  # 换手率(%)
        "prev_close": _p("f60"),        # 昨收
        "change_pct": round(d["f170"] / 100, 2) if d.get("f170") is not None else None,  # 涨跌幅(%)
    }
```

---

## Layer 2: K线层

### 2.1 美股 K 线 — 新浪（主）+ Yahoo（备）

两个独立数据源。新浪最长可回溯到 1984 年；Yahoo 适合需要复权数据的场景。

> **注意：** 东财 push2his kline/get 端点实测不返回美股/港股数据（2026-05-20 验证），仅支持 A 股。美股/港股 K 线用新浪和 Yahoo。

```python
def us_stock_kline_sina(ticker: str, num: int = 120) -> list[dict]:
    """
    新浪美股日K — 可回溯到1984年
    ticker: 如 "AAPL"
    返回: [{date, open, high, low, close, volume}, ...]
    """
    url = "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var/US_MinKService.getDailyK"
    params = {"symbol": ticker.upper(), "num": num}
    r = requests.get(url, params=params, headers={"Referer": "https://finance.sina.com.cn/"}, timeout=15)
    text = r.text
    
    # 解析 JSONP: var=([{...},...])
    import json
    m = re.search(r'\((\[.+\])\)', text)
    if not m:
        return []
    
    items = json.loads(m.group(1))
    result = []
    for item in items:
        result.append({
            "date": item.get("d"),
            "open": float(item.get("o", 0)),
            "high": float(item.get("h", 0)),
            "low": float(item.get("l", 0)),
            "close": float(item.get("c", 0)),
            "volume": int(item.get("v", 0)),
        })
    return result


def stock_kline_yahoo(symbol: str, interval: str = "1d",
                       range_: str = "6mo") -> list[dict]:
    """
    Yahoo Finance chart API — 美股+港股通用，零crumb
    symbol: "AAPL" (美股) 或 "0700.HK" (港股)
    interval: "1d", "1wk", "1mo", "5m", "15m", "1h"
    range_: "1d", "5d", "1mo", "3mo", "6mo", "1y", "5y", "max"
    返回: [{date, open, high, low, close, volume}, ...]
    """
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": interval, "range": range_}
    r = requests.get(url, params=params, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }, timeout=15)
    r.raise_for_status()
    
    d = r.json()
    chart = d.get("chart", {}).get("result", [{}])[0]
    timestamps = chart.get("timestamp", [])
    quote = chart.get("indicators", {}).get("quote", [{}])[0]
    
    from datetime import datetime
    result = []
    for i, ts in enumerate(timestamps):
        result.append({
            "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if "m" in interval or "h" in interval else datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
            "open": round(quote["open"][i], 2) if quote["open"][i] else 0,
            "high": round(quote["high"][i], 2) if quote["high"][i] else 0,
            "low": round(quote["low"][i], 2) if quote["low"][i] else 0,
            "close": round(quote["close"][i], 2) if quote["close"][i] else 0,
            "volume": int(quote["volume"][i]) if quote["volume"][i] else 0,
        })
    return result
```

### 2.2 港股 K 线 — Yahoo（唯一可用源）

港股 K 线只有 Yahoo 一个可用源（新浪港股K线已失效，东财 push2his 不返回港股K线数据）。

```python
# 港股 Yahoo K线: 直接调 stock_kline_yahoo("0700.HK")
```

---

## Layer 3: 技术指标层

基于 K 线 OHLCV 数据的纯 Python 技术指标计算，零额外依赖。

**使用方式：** 先调 K 线函数获取数据，再传入技术指标函数：
```python
klines = us_stock_kline_sina("AAPL", 120)
macd = calc_macd(klines)
rsi = calc_rsi(klines)
```

### 3.1 移动平均线 MA / EMA

```python
def _ema(values: list[float], period: int) -> list[float]:
    """EMA 指数移动平均（内部辅助）"""
    result = [values[0]]
    k = 2 / (period + 1)
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def calc_ma(klines: list[dict], periods: list[int] = None) -> list[dict]:
    """
    移动平均线 MA + EMA
    klines: K线数据 [{date, open, high, low, close, volume}, ...]
    periods: 周期列表，默认 [5, 10, 20, 60]
    返回: [{date, close, ma5, ma10, ma20, ma60, ema12, ema26}, ...]
    """
    if periods is None:
        periods = [5, 10, 20, 60]
    closes = [k["close"] for k in klines]
    
    # EMA 12/26（MACD 常用）
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    
    result = []
    for i, k in enumerate(klines):
        row = {"date": k["date"], "close": k["close"]}
        for p in periods:
            if i >= p - 1:
                row[f"ma{p}"] = round(sum(closes[i - p + 1:i + 1]) / p, 4)
            else:
                row[f"ma{p}"] = None
        row["ema12"] = round(ema12[i], 4)
        row["ema26"] = round(ema26[i], 4)
        result.append(row)
    return result
```

### 3.2 MACD

```python
def calc_macd(klines: list[dict], fast: int = 12, slow: int = 26,
              signal: int = 9) -> list[dict]:
    """
    MACD (Moving Average Convergence Divergence)
    klines: K线数据
    fast/slow/signal: 快线/慢线/信号线周期（默认 12/26/9）
    返回: [{date, close, dif, dea, macd_hist}, ...]
    
    dif = EMA(fast) - EMA(slow)        金叉/死叉看 dif 穿越 dea
    dea = EMA(signal) of dif           信号线
    macd_hist = (dif - dea) * 2        柱状图（红涨绿跌）
    """
    closes = [k["close"] for k in klines]
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    
    dif = [round(f - s, 4) for f, s in zip(ema_fast, ema_slow)]
    dea = _ema(dif, signal)
    
    result = []
    for i, k in enumerate(klines):
        result.append({
            "date": k["date"],
            "close": k["close"],
            "dif": round(dif[i], 4),
            "dea": round(dea[i], 4),
            "macd_hist": round((dif[i] - dea[i]) * 2, 4),
        })
    return result
```

### 3.3 RSI

```python
def calc_rsi(klines: list[dict],
             periods: list[int] = None) -> list[dict]:
    """
    RSI (Relative Strength Index)
    klines: K线数据
    periods: 周期列表（默认 [6, 12, 24]）
    返回: [{date, close, rsi6, rsi12, rsi24}, ...]
    
    RSI > 70 超买区（可能回调）
    RSI < 30 超卖区（可能反弹）
    """
    if periods is None:
        periods = [6, 12, 24]
    closes = [k["close"] for k in klines]
    
    # 涨跌额序列
    changes = [0.0] + [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    
    result = []
    for i, k in enumerate(klines):
        row = {"date": k["date"], "close": k["close"]}
        for p in periods:
            if i < p:
                row[f"rsi{p}"] = None
                continue
            avg_gain = sum(gains[i - p + 1:i + 1]) / p
            avg_loss = sum(losses[i - p + 1:i + 1]) / p
            if avg_loss == 0:
                row[f"rsi{p}"] = 100.0
            else:
                rs = avg_gain / avg_loss
                row[f"rsi{p}"] = round(100 - 100 / (1 + rs), 2)
        result.append(row)
    return result
```

### 3.4 KDJ

```python
def calc_kdj(klines: list[dict], n: int = 9,
             m1: int = 3, m2: int = 3) -> list[dict]:
    """
    KDJ 随机指标
    klines: K线数据
    n: RSV 周期（默认9）
    m1/m2: K/D 平滑系数（默认3/3）
    返回: [{date, close, k, d, j}, ...]
    
    K/D > 80 超买，K/D < 20 超卖
    J > 100 或 J < 0 为极端信号
    金叉: K 上穿 D；死叉: K 下穿 D
    """
    k_val, d_val = 50.0, 50.0
    result = []
    
    for i, kline in enumerate(klines):
        if i < n - 1:
            result.append({"date": kline["date"], "close": kline["close"],
                           "k": None, "d": None, "j": None})
            continue
        
        window = klines[i - n + 1:i + 1]
        high_n = max(w["high"] for w in window)
        low_n = min(w["low"] for w in window)
        
        rsv = (kline["close"] - low_n) / (high_n - low_n) * 100 if high_n != low_n else 50.0
        k_val = (1 / m1) * rsv + (1 - 1 / m1) * k_val
        d_val = (1 / m2) * k_val + (1 - 1 / m2) * d_val
        j_val = 3 * k_val - 2 * d_val
        
        result.append({
            "date": kline["date"],
            "close": kline["close"],
            "k": round(k_val, 2),
            "d": round(d_val, 2),
            "j": round(j_val, 2),
        })
    return result
```

### 3.5 布林带

```python
def calc_boll(klines: list[dict], period: int = 20,
              num_std: float = 2.0) -> list[dict]:
    """
    布林带 (Bollinger Bands)
    klines: K线数据
    period: 中轨 MA 周期（默认20）
    num_std: 标准差倍数（默认2）
    返回: [{date, close, upper, middle, lower, bandwidth}, ...]
    
    价格触及 upper → 可能超买
    价格触及 lower → 可能超卖
    bandwidth 收窄 → 即将变盘
    """
    closes = [k["close"] for k in klines]
    result = []
    
    for i, k in enumerate(klines):
        if i < period - 1:
            result.append({"date": k["date"], "close": k["close"],
                           "upper": None, "middle": None, "lower": None,
                           "bandwidth": None})
            continue
        
        window = closes[i - period + 1:i + 1]
        ma = sum(window) / period
        std = (sum((x - ma) ** 2 for x in window) / period) ** 0.5
        upper = ma + num_std * std
        lower = ma - num_std * std
        
        result.append({
            "date": k["date"],
            "close": k["close"],
            "upper": round(upper, 4),
            "middle": round(ma, 4),
            "lower": round(lower, 4),
            "bandwidth": round((upper - lower) / ma * 100, 2) if ma else None,
        })
    return result
```

---

## Layer 4: 基本面层

### 4.1 财报三表 — 东财 datacenter

东财 datacenter 提供美股/港股的资产负债表、利润表、现金流量表，中文字段名，按科目行展开。

```python
def financial_statements_eastmoney(secucode: str, statement: str = "balance",
                                     page_size: int = 200) -> list[dict]:
    """
    东财 datacenter 财报三表
    secucode: "AAPL.O" (NASDAQ) / "BABA.N" (NYSE) / "00700.HK" (港股)
    statement: "balance" / "income" / "cashflow"
    返回: [{ITEM_NAME, AMOUNT, YOY_RATIO, REPORT, REPORT_DATE, ...}, ...]
    
    注意: 数据按科目行展开，每行一个科目（如"流动资产合计"、"营业收入"等），
    同一期报告有多行。用 REPORT_DATE 分组可还原整张报表。
    """
    # 报表名映射（注意命名不统一：balance/income 用 F10，cashflow 用 SK）
    report_map = {
        "balance": {"us": "RPT_USF10_FN_BALANCE", "hk": "RPT_HKF10_FN_BALANCE"},
        "income":  {"us": "RPT_USF10_FN_INCOME",  "hk": "RPT_HKF10_FN_INCOME"},
        "cashflow": {"us": "RPT_USSK_FN_CASHFLOW", "hk": "RPT_HKSK_FN_CASHFLOW"},
    }
    
    market = "hk" if secucode.endswith(".HK") else "us"
    report_name = report_map[statement][market]
    
    return eastmoney_datacenter(
        report_name=report_name,
        filter_str=f'(SECUCODE="{secucode}")',
        page_size=page_size,
        sort_columns="REPORT_DATE",
        sort_types="-1",
    )
    # 每行字段:
    # SECUCODE, SECURITY_CODE, SECURITY_NAME_ABBR, REPORT_DATE,
    # STD_ITEM_CODE, ITEM_NAME (科目名), AMOUNT (金额),
    # YOY_RATIO (同比%), REPORT (如 "2026/Q2"), REPORT_TYPE,
    # ACCOUNT_STANDARD (如 "美国会计准则"/"国际会计准则"),
    # CURRENCY (如 "美元"/"人民币")
```

### 4.2 关键财务指标(中文) — 东财 GMAININDICATOR

东财 datacenter 的 GMAININDICATOR 报表，提供中文关键财务指标概览。美股 49 字段、港股 75 字段，包含 ROE/ROA/EPS/毛利率/资产负债率/流动比率等，按季度报告。

```python
def key_indicators_eastmoney(secucode: str, page_size: int = 4) -> list[dict]:
    """
    东财 GMAININDICATOR 关键财务指标（中文）
    secucode: "AAPL.O" (NASDAQ) / "BABA.N" (NYSE) / "00700.HK" (港股)
    page_size: 返回最近几期报告（默认4期=一年）
    返回: [{REPORT_DATE, OPERATE_INCOME, BASIC_EPS, ROE_AVG, ROA, ...}, ...]
    
    美股核心字段(49): OPERATE_INCOME(营收), GROSS_PROFIT(毛利), GROSS_PROFIT_RATIO(毛利率%),
      PARENT_HOLDER_NETPROFIT(归母净利), NET_PROFIT_RATIO(净利率%), BASIC_EPS, DILUTED_EPS,
      ROE_AVG(平均ROE%), ROA(%), CURRENT_RATIO(流动比率), DEBT_ASSET_RATIO(资产负债率%),
      OPERATE_INCOME_YOY(营收同比%), BASIC_EPS_YOY(EPS同比%)
    
    港股额外字段(75): BPS(每股净资产), ROIC(投入资本回报率), EQUITY_RATIO(产权比率),
      HOLDER_PROFIT(股东应占溢利), OCF_SALES(经营现金流/营收%), DPS_HKD(每股股息),
      DIVI_RATIO(股息率%), PER_NETCASH_OPERATE(每股经营现金流)
    """
    market = "hk" if secucode.endswith(".HK") else "us"
    report_name = f"RPT_{'HK' if market == 'hk' else 'US'}F10_FN_GMAININDICATOR"
    
    return eastmoney_datacenter(
        report_name=report_name,
        filter_str=f'(SECUCODE="{secucode}")',
        page_size=page_size,
        sort_columns="REPORT_DATE",
        sort_types="-1",
    )
```

### 4.3 关键财务指标(英文) — Yahoo quoteSummary

Yahoo quoteSummary 的 `financialData` + `defaultKeyStatistics` 模块提供最核心的估值指标。

```python
def key_statistics(symbol: str) -> dict:
    """
    Yahoo 关键财务指标
    symbol: "AAPL" (美股) 或 "0700.HK" (港股)
    返回: PE/PB/EV/EBITDA/利润率/目标价/ROE/Beta 等
    """
    data = yahoo_quote_summary(symbol, ["financialData", "defaultKeyStatistics", "summaryDetail"])
    
    fd = data.get("financialData", {})
    ks = data.get("defaultKeyStatistics", {})
    sd = data.get("summaryDetail", {})
    
    def _val(d, key):
        v = d.get(key, {})
        return v.get("raw") if isinstance(v, dict) else v
    
    return {
        # 价格相关
        "current_price": _val(fd, "currentPrice"),
        "target_high": _val(fd, "targetHighPrice"),
        "target_low": _val(fd, "targetLowPrice"),
        "target_mean": _val(fd, "targetMeanPrice"),
        "recommendation": fd.get("recommendationKey"),  # buy/hold/sell
        
        # 估值指标
        "trailing_pe": _val(sd, "trailingPE"),
        "forward_pe": _val(ks, "forwardPE"),
        "peg_ratio": _val(ks, "pegRatio"),
        "price_to_book": _val(ks, "priceToBook"),
        "enterprise_value": _val(ks, "enterpriseValue"),
        "ev_to_ebitda": _val(ks, "enterpriseToEbitda"),
        "ev_to_revenue": _val(ks, "enterpriseToRevenue"),
        
        # 盈利能力
        "profit_margin": _val(ks, "profitMargins"),
        "operating_margin": _val(fd, "operatingMargins"),
        "gross_margin": _val(fd, "grossMargins"),
        "return_on_equity": _val(fd, "returnOnEquity"),
        "return_on_assets": _val(fd, "returnOnAssets"),
        
        # 成长性
        "earnings_growth": _val(fd, "earningsGrowth"),
        "revenue_growth": _val(fd, "revenueGrowth"),
        
        # 风险
        "beta": _val(ks, "beta"),
        "short_ratio": _val(ks, "shortRatio"),
        
        # 股息
        "dividend_yield": _val(sd, "dividendYield"),
        "payout_ratio": _val(ks, "payoutRatio"),
        
        # 规模
        "market_cap": _val(sd, "marketCap"),
        "total_revenue": _val(fd, "totalRevenue"),
        "total_cash": _val(fd, "totalCash"),
        "total_debt": _val(fd, "totalDebt"),
    }
```

### 4.4 分析师预期与评级 — Yahoo quoteSummary

```python
def analyst_estimates(symbol: str) -> dict:
    """
    Yahoo 分析师预期 — EPS预测/评级趋势/升降级历史
    symbol: "AAPL" 或 "0700.HK"
    """
    data = yahoo_quote_summary(symbol, [
        "earningsTrend", "recommendationTrend", "upgradeDowngradeHistory",
        "earnings", "earningsHistory",
    ])
    
    # EPS 趋势
    et = data.get("earningsTrend", {}).get("trend", [])
    eps_trend = []
    for t in et:
        eps_trend.append({
            "period": t.get("period"),
            "end_date": t.get("endDate"),
            "eps_estimate": t.get("earningsEstimate", {}).get("avg", {}).get("raw"),
            "eps_high": t.get("earningsEstimate", {}).get("high", {}).get("raw"),
            "eps_low": t.get("earningsEstimate", {}).get("low", {}).get("raw"),
            "revenue_estimate": t.get("revenueEstimate", {}).get("avg", {}).get("raw"),
            "num_analysts": t.get("earningsEstimate", {}).get("numberOfAnalysts", {}).get("raw"),
        })
    
    # 评级趋势 (最近4个月)
    rt = data.get("recommendationTrend", {}).get("trend", [])
    rating_trend = []
    for r_ in rt:
        rating_trend.append({
            "period": r_.get("period"),
            "strong_buy": r_.get("strongBuy"),
            "buy": r_.get("buy"),
            "hold": r_.get("hold"),
            "sell": r_.get("sell"),
            "strong_sell": r_.get("strongSell"),
        })
    
    # 升降级历史 (最近20条)
    udh = data.get("upgradeDowngradeHistory", {}).get("history", [])[:20]
    upgrades = []
    for u in udh:
        upgrades.append({
            "date": u.get("epochGradeDate"),
            "firm": u.get("firm"),
            "to_grade": u.get("toGrade"),
            "from_grade": u.get("fromGrade"),
            "action": u.get("action"),  # up/down/main/init
        })
    
    return {
        "eps_trend": eps_trend,
        "rating_trend": rating_trend,
        "upgrade_downgrade": upgrades,
    }
```

### 4.5 机构持仓 — Yahoo quoteSummary

```python
def institutional_holders(symbol: str) -> dict:
    """
    Yahoo 机构持仓 — 前10大机构 + 内部人持股比例
    symbol: "AAPL" 或 "0700.HK"
    """
    data = yahoo_quote_summary(symbol, ["institutionOwnership", "majorHoldersBreakdown"])
    
    # 持股比例总览
    mhb = data.get("majorHoldersBreakdown", {})
    def _val(d, key):
        v = d.get(key, {})
        return v.get("raw") if isinstance(v, dict) else v
    
    overview = {
        "insiders_pct": _val(mhb, "insidersPercentHeld"),
        "institutions_pct": _val(mhb, "institutionsPercentHeld"),
        "institutions_float_pct": _val(mhb, "institutionsFloatPercentHeld"),
        "institutions_count": _val(mhb, "institutionsCount"),
    }
    
    # 前10大机构
    io = data.get("institutionOwnership", {}).get("ownershipList", [])
    top_holders = []
    for h in io[:10]:
        top_holders.append({
            "name": h.get("organization"),
            "shares": _val(h, "position"),
            "value": _val(h, "value"),
            "pct_held": _val(h, "pctHeld"),
            "report_date": h.get("reportDate", {}).get("fmt") if isinstance(h.get("reportDate"), dict) else None,
        })
    
    return {"overview": overview, "top_holders": top_holders}
```

### 4.6 年度/季度财报明细 — Yahoo quoteSummary

东财 datacenter 按科目行展开，Yahoo 直接返回完整报表结构，两个互补。

```python
def financial_statements_yahoo(symbol: str,
                                 quarterly: bool = False) -> dict:
    """
    Yahoo 财报三表 — 结构化完整报表
    symbol: "AAPL" 或 "0700.HK"
    quarterly: False=年度, True=季度
    返回: {"income": [...], "balance": [...], "cashflow": [...]}
    """
    suffix = "Quarterly" if quarterly else ""
    data = yahoo_quote_summary(symbol, [
        f"incomeStatementHistory{suffix}",
        f"balanceSheetHistory{suffix}",
        f"cashflowStatementHistory{suffix}",
    ])
    
    def _extract(statements):
        result = []
        for stmt in statements:
            row = {}
            for k, v in stmt.items():
                if isinstance(v, dict) and "raw" in v:
                    row[k] = v["raw"]
                elif isinstance(v, dict) and "fmt" in v:
                    row[k] = v["fmt"]
                else:
                    row[k] = v
            result.append(row)
        return result
    
    income_key = f"incomeStatementHistory{suffix}"
    balance_key = f"balanceSheetHistory{suffix}"
    cashflow_key = f"cashflowStatementHistory{suffix}"
    
    return {
        "income": _extract(data.get(income_key, {}).get("incomeStatementHistory", [])),
        "balance": _extract(data.get(balance_key, {}).get("balanceSheetStatements", [])),
        "cashflow": _extract(data.get(cashflow_key, {}).get("cashflowStatements", [])),
    }
```

---

## Layer 5: 资金面层

### 5.1 日级资金流 — 东财 push2his

```python
def fund_flow_daily(ticker_or_code: str, secid_prefix: int = 105,
                      limit: int = 100) -> list[dict]:
    """
    东财 push2his 日级资金流 — 主力/大单/中单/小单净流入
    美股: fund_flow_daily("AAPL", 105)  # NASDAQ
          fund_flow_daily("BABA", 106)  # NYSE
    港股: fund_flow_daily("00700", 116)
    返回: [{date, main_net, big_net, mid_net, small_net, main_pct, ...}, ...]
    """
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": f"{secid_prefix}.{ticker_or_code}",
        "klt": 101,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "lmt": limit,
    }
    r = requests.get(url, params=params, timeout=15)
    d = r.json()
    data = d.get("data")
    if not data or not data.get("klines"):
        return []
    
    result = []
    for line in data["klines"]:
        parts = line.split(",")
        # f51=日期, f52=主力净流入, f53=小单净流入, f54=中单净流入, f55=大单净流入, f56=超大单净流入
        result.append({
            "date": parts[0],
            "main_net": float(parts[1]),       # 主力净流入（元）
            "small_net": float(parts[2]),       # 小单净流入
            "mid_net": float(parts[3]),         # 中单净流入
            "big_net": float(parts[4]),         # 大单净流入
            "super_big_net": float(parts[5]),   # 超大单净流入
            "main_pct": float(parts[6]) if len(parts) > 6 and parts[6] else 0,  # 主力净占比%
        })
    return result
```

---

## Layer 6: 期权层

### 6.1 期权链 + 希腊字母 + 0DTE 流 — CBOE 官方（主力 ⭐ V2.0 新增）

数据源 `cdn.cboe.com`，零鉴权。单只标的全链一次返回（实测 NVDA 3,908 / TSLA 6,200 / AAPL 3,576 合约），
字段含 `bid/ask/volume/open_interest/iv/delta/gamma/vega/theta/rho`。

> ⚠️ **合规（C 级）**：Cboe 的 Use of Content 政策要求使用前取得书面批准与 license。
> 以下代码**仅供个人研究**；商业用途或再分发前须先向 Cboe 申请授权。

```python
import re
from datetime import datetime, timezone, timedelta
# 依赖「官方源统一出口」的 official_get / assert_us_ticker

CBOE_BASE = "https://cdn.cboe.com/api/global/delayed_quotes"
# OCC 合约代码: 标的 + YYMMDD + C/P + 8位行权价(千分之一美元)
# root 允许含数字：拆股/分拆等公司行为会产生调整后合约（如 NVDA1、BRKB1）。
# 后面全是定宽组（6+1+8=15 字符），正则回溯能正确对齐，标准合约解析结果不变。
_OSI = re.compile(r"^(?P<root>[A-Z][A-Z0-9]*)(?P<y>\d{2})(?P<m>\d{2})(?P<d>\d{2})"
                  r"(?P<cp>[CP])(?P<strike>\d{8})$")


def parse_osi(symbol: str) -> dict:
    """解析 OCC 合约代码 → {expiry, type, strike}；无法解析返回 {}"""
    m = _OSI.match(symbol)
    if not m:
        return {}
    g = m.groupdict()
    return {"expiry": f"20{g['y']}-{g['m']}-{g['d']}",
            "type": "call" if g["cp"] == "C" else "put",
            "strike": int(g["strike"]) / 1000.0}


def options_chain_cboe(ticker: str) -> dict:
    """
    CBOE 官方延时期权全链（仅美股）。
    返回 {"ticker","timestamp","spot","contracts":[{symbol,expiry,type,strike,bid,ask,
          volume,open_interest,iv,delta,gamma,vega,theta,rho,last_trade_price}]}
    """
    ticker = assert_us_ticker(ticker)
    raw = official_get(f"{CBOE_BASE}/options/{ticker}.json", as_json=True)
    data = raw.get("data") or {}
    contracts = []
    for o in data.get("options") or []:
        meta = parse_osi(o.get("option", ""))
        if not meta:
            continue
        contracts.append({
            "symbol": o["option"], **meta,
            "bid": o.get("bid"), "ask": o.get("ask"),
            "volume": o.get("volume") or 0,
            "open_interest": o.get("open_interest") or 0,
            "iv": o.get("iv"), "delta": o.get("delta"), "gamma": o.get("gamma"),
            "vega": o.get("vega"), "theta": o.get("theta"), "rho": o.get("rho"),
            "last_trade_price": o.get("last_trade_price"),
        })
    if not contracts:
        raise DataNotAvailable(f"{ticker} 未返回任何期权合约 —— 该标的可能无期权，"
                               f"或不在 CBOE 覆盖范围（CBOE 仅覆盖美股）")
    return {"ticker": ticker, "timestamp": raw.get("timestamp"),
            "spot": data.get("current_price"), "contracts": contracts}


try:
    from zoneinfo import ZoneInfo
    _ET_TZ = ZoneInfo("America/New_York")
except Exception:      # Windows 上 zoneinfo 可能缺 tzdata
    _ET_TZ = None


def _et_today() -> str:
    """
    美东今日 YYYY-MM-DD，用于 0DTE 判定。

    ⚠️ 必须区分 EDT(UTC-4) 与 EST(UTC-5)：硬编码 UTC-4 会让冬令时
    UTC 04:00–05:00 这一小时算成次日，导致 0DTE 选错到期日。
    """
    now = datetime.now(timezone.utc)
    if _ET_TZ is not None:
        return now.astimezone(_ET_TZ).strftime("%Y-%m-%d")
    # 无 tzdata 时的回退：按美国 DST 规则（3月第2个周日 ~ 11月第1个周日）自算
    y = now.year
    # 美国 DST 在**当地时间 2:00** 切换，换算成 UTC：
    #   开始 = 3月第2个周日 02:00 EST = 07:00 UTC
    #   结束 = 11月第1个周日 02:00 EDT = 06:00 UTC
    # 用 00:00 UTC 当切换点会在切换日凌晨那几小时取错偏移。
    mar8 = datetime(y, 3, 8, tzinfo=timezone.utc)
    dst_start = (mar8 + timedelta(days=(6 - mar8.weekday()) % 7)
                 ).replace(hour=7)
    nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
    dst_end = (nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
               ).replace(hour=6)
    offset = 4 if dst_start <= now < dst_end else 5
    return (now - timedelta(hours=offset)).strftime("%Y-%m-%d")


def filter_expiry(chain: dict, expiry: str = None, dte_max: int = None) -> list[dict]:
    """按到期日筛选。expiry='0DTE' 取当日到期；dte_max 取 N 天内到期"""
    cs = chain["contracts"]
    if expiry == "0DTE":
        return [c for c in cs if c["expiry"] == _et_today()]
    if expiry:
        return [c for c in cs if c["expiry"] == expiry]
    if dte_max is not None:
        today = datetime.strptime(_et_today(), "%Y-%m-%d")
        return [c for c in cs
                if 0 <= (datetime.strptime(c["expiry"], "%Y-%m-%d") - today).days <= dte_max]
    return cs


def unusual_activity(contracts: list[dict], min_volume: int = 500,
                     vol_oi_min: float = 1.0) -> list[dict]:
    """
    异动合约识别：成交量 >= min_volume 且 volume/open_interest >= vol_oi_min。
    vol/OI > 1 = 当日成交超过存量持仓 = 新建仓，是 options flow 的核心信号。
    """
    out = []
    for c in contracts:
        vol, oi = c["volume"], c["open_interest"]
        if vol < min_volume:
            continue
        ratio = vol / oi if oi > 0 else float("inf")
        if ratio >= vol_oi_min:
            out.append({**c, "vol_oi_ratio": round(ratio, 2) if oi > 0 else None})
    return sorted(out, key=lambda x: -x["volume"])


def chain_summary(contracts: list[dict]) -> dict:
    """链级聚合：put/call 量比与持仓比、成交量加权 IV、净 delta 敞口"""
    calls = [c for c in contracts if c["type"] == "call"]
    puts = [c for c in contracts if c["type"] == "put"]
    cv, pv = sum(c["volume"] for c in calls), sum(c["volume"] for c in puts)
    coi, poi = sum(c["open_interest"] for c in calls), sum(c["open_interest"] for c in puts)
    traded = [c for c in contracts if c["volume"] > 0 and c.get("iv")]
    tot_v = sum(c["volume"] for c in traded)
    vwiv = sum(c["iv"] * c["volume"] for c in traded) / tot_v if tot_v else None
    net_delta = sum((c.get("delta") or 0) * c["volume"] * 100 for c in contracts)
    return {"call_volume": cv, "put_volume": pv,
            "put_call_volume_ratio": round(pv / cv, 3) if cv else None,
            "call_oi": coi, "put_oi": poi,
            "put_call_oi_ratio": round(poi / coi, 3) if coi else None,
            "volume_weighted_iv": round(vwiv, 4) if vwiv else None,
            "net_delta_exposure_shares": round(net_delta),
            "contracts_total": len(contracts),
            "contracts_traded": len([c for c in contracts if c["volume"] > 0])}


def cboe_quote(ticker: str) -> dict:
    """CBOE 个股快照（含现价，可与期权链配合定 ATM）"""
    return official_get(f"{CBOE_BASE}/quotes/{assert_us_ticker(ticker)}.json",
                        as_json=True)["data"]
```

**用法**
```python
chain = options_chain_cboe("NVDA")
zero  = filter_expiry(chain, expiry="0DTE")      # 当日到期合约
near  = filter_expiry(chain, dte_max=7)          # 7 日内到期
flow  = unusual_activity(zero, min_volume=1000)  # 0DTE 异动
summ  = chain_summary(zero)                      # P/C 比、加权 IV、净 delta
```

**实测样本（2026-07-24）**

| 标的 | 全链 | 0DTE 合约 | P/C 量比 | 量加权 IV | 净 delta 敞口 |
|---|---|---|---|---|---|
| NVDA | 3,908 | 168 | 0.542 | 43.1% | +16,496,611 股 |
| TSLA | 6,200 | 326 | 1.041 | 83.2% | −37,364,065 股 |

> TSLA 当日 −14.52%，期权层三个指标（put 占优 / IV 83% / 净 delta 为负）独立指向同一方向，可交叉验证。

⚠️ **限制**：CBOE 端点仅覆盖**美股**（港股期权需港交所专有接口）；数据为**延时**，
不适用于实盘下单，适用于研究与流向分析。

---

### 6.2 期权链 — Yahoo Finance（后备 · 无希腊字母）

```python
def options_chain(symbol: str, expiration: int = None) -> dict:
    """
    Yahoo 期权链 — calls + puts 完整数据（仅美股）
    symbol: "AAPL", "TSLA" 等美股 ticker
    ⚠️ 港股(如0700.HK)期权不在Yahoo覆盖范围，调用会返回空列表
    expiration: Unix timestamp (不传则返回最近到期日 + 所有到期日列表)
    返回: {"expiration_dates": [...], "calls": [...], "puts": [...]}
    """
    s = get_yahoo_session()
    params = {"crumb": s._crumb}
    if expiration:
        params["date"] = expiration
    
    r = s.get(f"https://query2.finance.yahoo.com/v7/finance/options/{symbol}",
              params=params, timeout=15)
    r.raise_for_status()
    
    oc = r.json().get("optionChain", {}).get("result", [{}])[0]
    
    exp_dates = oc.get("expirationDates", [])
    options = oc.get("options", [{}])[0] if oc.get("options") else {}
    
    def _parse_options(opts):
        result = []
        for o in opts:
            def _val(key):
                v = o.get(key, {})
                return v.get("raw") if isinstance(v, dict) else v
            result.append({
                "strike": _val("strike"),
                "last_price": _val("lastPrice"),
                "bid": _val("bid"),
                "ask": _val("ask"),
                "volume": _val("volume"),
                "open_interest": _val("openInterest"),
                "implied_volatility": _val("impliedVolatility"),
                "in_the_money": o.get("inTheMoney"),
                "expiration": o.get("expiration", {}).get("fmt") if isinstance(o.get("expiration"), dict) else None,
                "contract_symbol": o.get("contractSymbol"),
            })
        return result
    
    return {
        "expiration_dates": exp_dates,  # Unix timestamps, 可依次传入获取各期
        "calls": _parse_options(options.get("calls", [])),
        "puts": _parse_options(options.get("puts", [])),
        "underlying_price": oc.get("quote", {}).get("regularMarketPrice"),
    }
```

---

## Layer 7: SEC Filing 层（仅美股）

### 7.1 SEC Filing 列表 — EDGAR submissions

```python
SEC_HEADERS = {"User-Agent": "SimonLin global-stock-data/1.0 (contact@example.com)"}

def sec_filings(cik: str, form_type: str = None) -> dict:
    """
    SEC EDGAR Filing 列表
    cik: CIK号（10位补零），如 "0000320193" (Apple)
         可通过 ticker_to_cik() 从 ticker 转换
    form_type: 筛选类型，如 "10-K", "10-Q", "8-K"（不传返回全部）
    返回: {"company_name": ..., "filings": [{form, date, accession_number, primary_document}, ...]}
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    r = requests.get(url, headers=SEC_HEADERS, timeout=15)
    r.raise_for_status()
    
    data = r.json()
    recent = data.get("filings", {}).get("recent", {})
    
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])
    
    filings = []
    for i in range(len(forms)):
        if form_type and forms[i] != form_type:
            continue
        filings.append({
            "form": forms[i],
            "date": dates[i],
            "accession_number": accessions[i],
            "primary_document": primary_docs[i] if i < len(primary_docs) else "",
            "description": descriptions[i] if i < len(descriptions) else "",
            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accessions[i].replace('-', '')}/{primary_docs[i]}" if i < len(primary_docs) and primary_docs[i] else "",
        })
    
    return {
        "company_name": data.get("name"),
        "cik": cik,
        "ticker": data.get("tickers", [""])[0] if data.get("tickers") else "",
        "filings": filings[:50],  # 最近50条
    }
```

### 7.2 SEC XBRL 结构化财务数据 — EDGAR companyfacts

覆盖 503 个 GAAP 指标，可精确提取多年营收/净利/EPS/资产/负债等。

```python
def sec_xbrl_facts(cik: str, metrics: list[str] = None) -> dict:
    """
    SEC EDGAR XBRL 结构化财务数据
    cik: CIK号（10位补零）
    metrics: 要提取的指标名，如 ["RevenueFromContractWithCustomerExcludingAssessedTax",
             "NetIncomeLoss", "EarningsPerShareDiluted"]
             不传则返回所有可用指标名列表
    
    返回: {"company": ..., "metrics": {"Revenue": [{end, val, form, filed}, ...], ...}}
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    r = requests.get(url, headers=SEC_HEADERS, timeout=15)
    r.raise_for_status()
    
    facts = r.json()
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    
    # 如果不传 metrics，返回所有可用指标
    if not metrics:
        available = []
        for k, v in us_gaap.items():
            label = v.get("label", k)
            units = list(v.get("units", {}).keys())
            available.append({"name": k, "label": label, "units": units})
        return {
            "company": facts.get("entityName"),
            "total_metrics": len(available),
            "available_metrics": available,
        }
    
    # 提取指定指标
    result = {}
    for metric_name in metrics:
        metric = us_gaap.get(metric_name, {})
        if not metric:
            result[metric_name] = []
            continue
        
        # 自动选择单位（USD 或 USD/shares）
        units = metric.get("units", {})
        unit_key = "USD" if "USD" in units else list(units.keys())[0] if units else None
        if not unit_key:
            result[metric_name] = []
            continue
        
        entries = units[unit_key]
        # 只取 10-K 和 10-Q
        filtered = [e for e in entries if e.get("form") in ("10-K", "10-Q")]
        result[metric_name] = [{
            "end": e.get("end"),
            "val": e.get("val"),
            "form": e.get("form"),
            "filed": e.get("filed"),
            "fy": e.get("fy"),
            "fp": e.get("fp"),
        } for e in filtered[-20:]]  # 最近20条
    
    return {
        "company": facts.get("entityName"),
        "metrics": result,
    }
```

**常用 XBRL 指标名速查：**

| 指标 | XBRL 名 |
|------|---------|
| 营业收入 | `RevenueFromContractWithCustomerExcludingAssessedTax` 或 `Revenues` |
| 净利润 | `NetIncomeLoss` |
| 稀释 EPS | `EarningsPerShareDiluted` |
| 基本 EPS | `EarningsPerShareBasic` |
| 总资产 | `Assets` |
| 总负债 | `Liabilities` |
| 股东权益 | `StockholdersEquity` |
| 经营现金流 | `NetCashProvidedByOperatingActivities` |
| 研发费用 | `ResearchAndDevelopmentExpense` |
| 股份回购 | `PaymentsForRepurchaseOfCommonStock` |
| 股息支付 | `PaymentsOfDividends` |

---

## Layer 8: 工具层

### 8.1 股票搜索 — 东财 search API

```python
def stock_search(keyword: str, count: int = 10) -> list[dict]:
    """
    东财股票搜索 — 支持中英文，返回代码+市场+中文名
    keyword: "AAPL" / "苹果" / "Tencent" / "00700" / "特斯拉"
    返回: [{code, name, mkt_num, market_name, security_type}, ...]
    
    mkt_num 即 push2/push2his 的 secid 前缀:
    105=NASDAQ, 106=NYSE, 107=美股ETF, 116=港股
    """
    url = "https://searchapi.eastmoney.com/api/suggest/get"
    params = {
        "input": keyword,
        "type": 14,  # 14=全球市场
        "token": "D43BF722C8E33BDC906FB84D85E326E8",
        "count": count,
    }
    r = requests.get(url, params=params, timeout=10)
    d = r.json()
    
    suggestions = d.get("QuotationCodeTable", {}).get("Data", [])
    result = []
    for s in suggestions:
        mkt = s.get("MktNum", "")
        # 只保留美股和港股
        if str(mkt) not in ("105", "106", "107", "116"):
            continue
        
        market_map = {"105": "NASDAQ", "106": "NYSE", "107": "US_OTHER", "116": "HK"}
        result.append({
            "code": s.get("Code"),
            "name": s.get("Name"),
            "mkt_num": int(mkt),
            "market_name": market_map.get(str(mkt), str(mkt)),
            "security_type": s.get("SecurityTypeName"),
        })
    return result
```

### 8.2 股票新闻 — Yahoo Finance search

```python
def stock_news(keyword: str, count: int = 10) -> list[dict]:
    """
    Yahoo Finance 新闻搜索
    keyword: 股票代码或关键词，如 "AAPL", "Tesla", "0700.HK"
    返回: [{title, publisher, link, publish_time, thumbnail}, ...]
    注意: 需要先获取 Yahoo cookie 才能调用，否则返回 400
    """
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    s.get("https://fc.yahoo.com", timeout=10)  # 获取 cookie
    
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    params = {"q": keyword, "quotesCount": 0, "newsCount": count}
    r = s.get(url, params=params, timeout=10)
    r.raise_for_status()
    
    news = r.json().get("news", [])
    result = []
    for n in news:
        result.append({
            "title": n.get("title"),
            "publisher": n.get("publisher"),
            "link": n.get("link"),
            "publish_time": n.get("providerPublishTime"),
            "thumbnail": n.get("thumbnail", {}).get("resolutions", [{}])[0].get("url") if n.get("thumbnail") else None,
        })
    return result
```

### 8.3 Ticker → CIK 映射 — SEC EDGAR（仅美股）

```python
_cik_cache = None

def ticker_to_cik(ticker: str) -> dict:
    """
    SEC EDGAR ticker → CIK 映射
    ticker: 如 "AAPL", "TSLA", "MSFT"
    返回: {"ticker": "AAPL", "cik": "0000320193", "company": "Apple Inc."}
    
    首次调用下载完整映射表(~10KB JSON, 10000+公司)并缓存。
    """
    global _cik_cache
    if not _cik_cache:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers=SEC_HEADERS, timeout=15)
        r.raise_for_status()
        _cik_cache = r.json()
    
    ticker_upper = ticker.upper()
    for _, v in _cik_cache.items():
        if v.get("ticker") == ticker_upper:
            cik_str = str(v["cik_str"]).zfill(10)
            return {
                "ticker": ticker_upper,
                "cik": cik_str,
                "company": v.get("title"),
            }
    return {}
```

### 8.4 全市场股票列表 — 东财 push2

```python
def market_stock_list(market: str = "us_nasdaq", sort_field: str = "f3",
                       sort_desc: bool = True, page: int = 1,
                       page_size: int = 20) -> dict:
    """
    东财 push2 全市场股票列表 — 涨跌幅/成交量/成交额排名
    market: "us_nasdaq" (m:105), "us_nyse" (m:106), "hk" (m:116)
    sort_field: 排序字段
      f3=涨跌幅, f5=成交量, f6=成交额, f2=最新价, f7=振幅, f15=最高, f16=最低
    sort_desc: True=降序(默认), False=升序
    page/page_size: 分页（默认第1页，每页20条）
    返回: {"total": 5925, "stocks": [{code, name, price, change_pct, volume, ...}, ...]}
    
    典型用途:
    - 今日涨幅 TOP 20: market_stock_list("us_nasdaq", "f3", True)
    - 今日跌幅 TOP 20: market_stock_list("us_nasdaq", "f3", False)
    - 成交量 TOP 20: market_stock_list("hk", "f5", True)
    - 遍历全市场: 循环 page=1..N, 每页100条做筛选
    """
    market_map = {"us_nasdaq": "m:105", "us_nyse": "m:106", "us_etf": "m:107", "hk": "m:116"}
    fs = market_map.get(market, market)
    
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "fs": fs,
        "fields": "f2,f3,f4,f5,f6,f7,f12,f14,f15,f16,f17,f18",
        "pn": page,
        "pz": page_size,
        "fid": sort_field,
        "po": 1 if sort_desc else 0,
    }
    r = requests.get(url, params=params, timeout=15)
    d = r.json()
    data = d.get("data", {})
    
    total = data.get("total", 0)
    diff = data.get("diff", [])
    # 东财 push2 的 diff 有时是 list、有时是按序号为键的 dict（如 {"0":{...},"1":{...}}）。
    # 直接 for item in diff 遇到 dict 会拿到字符串键 → AttributeError，统一成列表。
    if isinstance(diff, dict):
        diff = list(diff.values())
    
    stocks = []
    for item in diff:
        stocks.append({
            "code": item.get("f12"),         # 股票代码
            "name": item.get("f14"),         # 中文名
            "price": item.get("f2"),         # 最新价(原始值, 需÷10^小数位)
            "change_pct": round(item["f3"] / 100, 2) if item.get("f3") is not None else None,  # 涨跌幅(%)
            "change_amount": item.get("f4"), # 涨跌额(原始值)
            "volume": item.get("f5"),        # 成交量(股)
            "amount": item.get("f6"),        # 成交额
            "amplitude": round(item["f7"] / 100, 2) if item.get("f7") is not None else None,  # 振幅(%)
            "high": item.get("f15"),         # 最高(原始值)
            "low": item.get("f16"),          # 最低(原始值)
            "open": item.get("f17"),         # 开盘(原始值)
            "prev_close": item.get("f18"),   # 昨收(原始值)
        })
    
    return {"total": total, "stocks": stocks}
```

---

## Layer 9: 做空层 — FINRA Reg SHO（B 级 ⭐ V2.0 新增 · 仅美股）

全市场**每日**空头成交量，A 股无对应品类。单个文件覆盖全市场（实测 12,112 只）。

> ⚠️ **合规（B 级）**：Reg SHO 每日文件是 FINRA 主动发布供下载的监管披露文件，直接下载属常规用法；
> 但其站点条款禁止批量爬取页面，且声明数据为 non-commercial use。**商用前请自行向 FINRA 确认。**

```python
from datetime import datetime, timedelta
# 依赖「官方源统一出口」的 official_get


def _recent_weekdays(days_back: int = 7) -> list[str]:
    d, out = datetime.now(), []
    while len(out) < days_back:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


def short_volume_all(date: str = None, market: str = "CNMS") -> dict:
    """
    FINRA 全市场每日空头成交量。
    market: CNMS(合并全市场) / FNSQ(Nasdaq) / FNYX(NYSE) / FNRA(TRF)
    date: YYYYMMDD；不传则自动回退找最近有数据的交易日
    返回 {"date","market","count","data":{SYMBOL:{short,short_exempt,total,ratio}}}
    """
    for d in ([date] if date else _recent_weekdays(7)):
        try:
            raw = official_get(
                f"https://cdn.finra.org/equity/regsho/daily/{market}shvol{d}.txt")
        except DataNotAvailable:
            continue   # 该日无文件（非交易日/尚未发布），回退下一日
        # 其余异常（网络/限流/配置）直接抛出，不伪装成「没数据」
        rows = {}
        for line in raw.splitlines()[1:]:
            p = line.split("|")
            if len(p) < 5 or not p[1]:
                continue
            try:
                sv, se, tv = float(p[2]), float(p[3]), float(p[4])
            except ValueError:
                continue
            rows[p[1]] = {"short": sv, "short_exempt": se, "total": tv,
                          "ratio": round(sv / tv, 4) if tv else None}
        if rows:
            return {"date": d, "market": market, "count": len(rows), "data": rows}
    # 抛 DataNotAvailable 而非 RuntimeError：指定日期无数据时，
    # 调用方（如 short_volume_symbol 的多日循环）要能捕获并跳过这一天
    raise DataNotAvailable(f"未找到 {market} "
                           f"{'该日' if date else '近 7 个工作日'}的 Reg SHO 数据")


def short_volume_symbol(symbol: str, days: int = 5, market: str = "CNMS") -> list[dict]:
    """单只股票近 N 个交易日的空头成交占比时间序列"""
    out = []
    for d in _recent_weekdays(days * 2):
        if len(out) >= days:
            break
        try:
            snap = short_volume_all(date=d, market=market)
        except DataNotAvailable:
            continue
        rec = snap["data"].get(symbol.upper())
        if rec:
            out.append({"date": d, **rec})
    return out


def short_volume_ranking(snapshot: dict, min_total: float = 1_000_000,
                         top: int = 20) -> list[dict]:
    """空头占比排行（先按最小成交量过滤，避免小票噪音）"""
    rows = [{"symbol": s, **v} for s, v in snapshot["data"].items()
            if v["total"] >= min_total and v["ratio"] is not None]
    return sorted(rows, key=lambda x: -x["ratio"])[:top]
```

**实测（2026-07-23，覆盖 12,112 只）**：NVDA 空头占比 37.5% / TSLA 48.3% / MU 49.6% / AAPL 50.7%；
NVDA 近三日 37.5% → 43.0% → 33.5%。

> ⚠️ **读法**：short volume ≠ short interest。前者是**当日卖出成交里被标记为空头的部分**
> （含做市商对冲，天然偏高，40%~50% 常见），后者是**未平仓空头存量**（双月披露）。
> 用它看**日度变化趋势**，不要用绝对值下结论。

---

## Layer 10: 申报事件流 — SEC EDGAR（S 级 ⭐ V2.0 新增 · 仅美股）

> ✅ **合规（S 级）**：本工具唯一无争议的可商用源。官方明示允许脚本访问、数据免费。
> **10 requests/second 是官方硬上限**，且必须声明 User-Agent（已由统一出口处理，记得改 `SEC_CONTACT`）。

### 10.1 每日申报流（Form 4 内部人 / 8-K / 13F 机构持仓）

```python
_FORM_LABEL = {"4": "内部人交易", "8-K": "重大事件", "13F-HR": "机构持仓",
               "144": "限售股拟出售", "10-K": "年报", "10-Q": "季报",
               "SC 13D": "举牌(主动)", "SC 13G": "举牌(被动)", "S-1": "IPO注册"}


def daily_filings(date: str = None, forms: list[str] = None) -> dict:
    """
    EDGAR 每日申报流。date=YYYYMMDD，不传自动回退找最近有数据的日子。
    forms: 只保留这些表单类型，如 ["4","8-K","13F-HR"]；None=全部
    返回 {"date","total","by_form":{...},"filings":[{form,form_label,company,cik,date,url}]}
    """
    for d in ([date] if date else _recent_weekdays(7)):
        dt = datetime.strptime(d, "%Y%m%d")
        url = (f"https://www.sec.gov/Archives/edgar/daily-index/"
               f"{dt.year}/QTR{(dt.month - 1) // 3 + 1}/form.{d}.idx")
        try:
            raw = official_get(url)
        except DataNotAvailable:
            continue   # 该日无索引文件，回退下一日
        # 配置错误（SEC_CONTACT 未改）与网络错误在此直接抛出——
        # 否则会被 7 次循环吞掉，最终误报成「未找到 EDGAR 每日索引」
        lines = raw.splitlines()
        start = next((i + 1 for i, L in enumerate(lines) if L.startswith("---")), 11)
        filings, by_form = [], {}
        for L in lines[start:]:
            if len(L) < 98:
                continue
            form, company = L[:12].strip(), L[12:74].strip()
            cik, filed, path = L[74:86].strip(), L[86:98].strip(), L[98:].strip()
            if not form:
                continue
            by_form[form] = by_form.get(form, 0) + 1
            if forms and form not in forms:
                continue
            filings.append({"form": form, "form_label": _FORM_LABEL.get(form, ""),
                            "company": company, "cik": cik, "date": filed,
                            "url": f"https://www.sec.gov/Archives/{path}" if path else None})
        if by_form:
            return {"date": d, "total": sum(by_form.values()),
                    "by_form": dict(sorted(by_form.items(), key=lambda x: -x[1])),
                    "filings": filings}
    raise DataNotAvailable("未找到近 7 个工作日的 EDGAR 每日索引")
```

**实测（2026-07-23，当日 3,703 份）**：424B2=627 / **Form 4 内部人=547** / **8-K=370** /
**13F-HR=261** / D=204 / 144=118。

### 10.2 全文检索（覆盖 2001 年至今所有申报正文）

```python
def fulltext_search(query: str, forms: str = None, date_from: str = None,
                    date_to: str = None, limit: int = 20) -> dict:
    """
    query: 加引号为精确短语，如 '"HBM4"'
    forms: "8-K" / "10-K" 等；date_from/to: YYYY-MM-DD
    """
    p = {"q": query, "from": 0, "size": limit}
    if forms:
        p["forms"] = forms
    if date_from:
        p["dateRange"], p["startdt"] = "custom", date_from
    if date_to:
        p["dateRange"], p["enddt"] = "custom", date_to
    j = official_get("https://efts.sec.gov/LATEST/search-index", params=p, as_json=True)
    hits = (j.get("hits") or {}).get("hits") or []
    return {"total": ((j.get("hits") or {}).get("total") or {}).get("value", 0),
            "results": [{"form": (h.get("_source") or {}).get("root_form"),
                         "company": ((h.get("_source") or {}).get("display_names") or [None])[0],
                         "filed": (h.get("_source") or {}).get("file_date"),
                         "id": h.get("_id")} for h in hits]}
```

**实测**：`fulltext_search('"HBM4"', forms="8-K")` → 命中 5 条，含 MICRON (MU) 2026-06-24、
AMD 2026-05-05。→ 可用于追踪某个技术名词/产品代号首次出现在哪家公司的正式申报里。

---

## Layer 11: 全市场横截面 — EDGAR frames（S 级 ⭐ V2.0 新增 · 免费 screener）

一次请求拿到**所有申报公司**某个指标某期的值。实测「研发费用 CY2025Q1」覆盖 1,842 家、
「净利润 CY2025Q1」覆盖 5,309 家。

```python
XBRL_TAGS = {
    "营业收入": "Revenues",
    "营业收入(合同)": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "净利润": "NetIncomeLoss",
    "研发费用": "ResearchAndDevelopmentExpense",
    "毛利": "GrossProfit",
    "经营利润": "OperatingIncomeLoss",
    "总资产": "Assets",
    "股东权益": "StockholdersEquity",
    "现金及等价物": "CashAndCashEquivalentsAtCarryingValue",
    "经营现金流": "NetCashProvidedByUsedInOperatingActivities",
    "资本开支": "PaymentsToAcquirePropertyPlantAndEquipment",
    "长期负债": "LongTermDebtNoncurrent",
    "稀释EPS": "EarningsPerShareDiluted",
}

# ⚠️ 时点(instant)概念 —— 资产负债表科目描述的是「某一时刻的余额」，而非一段期间的发生额。
# SEC Frames 对这类概念**要求周期带 I 后缀**，且**没有纯年度周期**：
#   Assets/CY2025Q1  -> 404      Assets/CY2025Q1I -> 200 (5643 家)
#   Assets/CY2024    -> 404      Assets/CY2024Q4I -> 200 (6248 家)
# 期间(duration)概念(营收/净利/现金流等)则相反，用 CY2025Q1 / CY2024。
# 以上均为 2026-07-26 逐个实测结果。
_INSTANT_TAGS = {
    "Assets",
    "StockholdersEquity",
    "CashAndCashEquivalentsAtCarryingValue",
    "LongTermDebtNoncurrent",
}


def _frame_period(year: int, quarter, instant: bool) -> str:
    """时点概念没有纯年度周期，年度请求落到 Q4I。"""
    if instant:
        return f"CY{year}Q{quarter}I" if quarter else f"CY{year}Q4I"
    return f"CY{year}Q{quarter}" if quarter else f"CY{year}"


def market_frame(tag: str, year: int, quarter: int = None, unit: str = "USD",
                 instant=None) -> dict:
    """
    全市场横截面。tag 可用 XBRL_TAGS 的中文键或原始 XBRL 标签。
    quarter: 1-4 季度；None 为年度
    instant: 是否为时点(资产负债表)概念。None=自动判定。

    自动判定逻辑：先按 _INSTANT_TAGS 猜一种周期形式，404 再换另一种重试。
    这样**任意原始 XBRL 标签**（Liabilities / InventoryNet / AssetsCurrent …）
    都能正确取到数，而不必把所有时点概念都枚举进 _INSTANT_TAGS。
    已知类型时显式传 instant=True/False 可省掉一次探测请求。
    """
    tag = XBRL_TAGS.get(tag, tag)
    guess = (tag in _INSTANT_TAGS) if instant is None else instant
    attempts = [guess] if instant is not None else [guess, not guess]

    last_err = None
    for is_instant in attempts:
        period = _frame_period(year, quarter, is_instant)
        try:
            j = official_get(
                f"https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/{unit}/{period}.json",
                timeout=45, as_json=True)
        except DataNotAvailable as e:      # 周期形式不对时 SEC 返回 404
            last_err = e
            continue
        rows = [{"cik": d.get("cik"), "entity": d.get("entityName"),
                 "value": d.get("val"), "end": d.get("end")} for d in j.get("data", [])]
        return {"tag": tag, "period": period, "unit": unit,
                "instant": is_instant, "count": len(rows), "data": rows}
    raise last_err


def frame_ranking(frame: dict, top: int = 20, ascending: bool = False) -> list[dict]:
    return sorted(frame["data"], key=lambda x: x["value"], reverse=not ascending)[:top]


def frame_screen(frame: dict, min_value: float = None,
                 max_value: float = None) -> list[dict]:
    """按数值区间筛选全市场公司"""
    out = frame["data"]
    if min_value is not None:
        out = [r for r in out if r["value"] >= min_value]
    if max_value is not None:
        out = [r for r in out if r["value"] <= max_value]
    return out
```

**实测**：研发费用 CY2025Q1 → Alphabet $13.56B / Meta $12.15B / Apple $8.55B /
微软 $8.20B / NVDA $3.99B；研发 > $10 亿的共 17 家。

> ⚠️ 不同公司使用的 XBRL 标签口径不完全一致（如营收有 `Revenues` 与
> `RevenueFromContractWithCustomerExcludingAssessedTax` 两种），做横截面对比时需交叉两个标签取并集。

---

## Layer 12: 宏观 / 日历（S 级为主 ⭐ V2.0 新增）

```python
import csv, io


def treasury_yield_curve(year: int = None) -> list[dict]:
    """美国国债收益率曲线（每日，1M~30Y）。政府数据，S 级。返回 [0] 为最新一日"""
    year = year or datetime.now().year
    url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
           f"daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
           f"&field_tdr_date_value={year}&page&_format=csv")
    return list(csv.DictReader(io.StringIO(official_get(url))))


def cftc_cot(limit: int = 20, market_contains: str = None) -> list[dict]:
    """CFTC 持仓报告(COT)。政府数据，S 级"""
    q = {"$limit": limit, "$order": "report_date_as_yyyy_mm_dd DESC"}
    if market_contains:
        q["$where"] = f"upper(contract_market_name) like upper('%{market_contains}%')"
    return official_get("https://publicreporting.cftc.gov/resource/6dca-aqww.json",
                        params=q, as_json=True)


def earnings_calendar(date: str = None) -> dict:
    """Nasdaq 财报日历。date=YYYY-MM-DD，不传取今天"""
    date = date or datetime.now().strftime("%Y-%m-%d")
    j = official_get("https://api.nasdaq.com/api/calendar/earnings",
                     params={"date": date}, headers={"Accept": "application/json"},
                     as_json=True)
    rows = ((j.get("data") or {}).get("rows")) or []
    return {"date": date, "count": len(rows),
            "rows": [{"symbol": r.get("symbol"), "name": r.get("name"),
                      "time": r.get("time"), "eps_forecast": r.get("epsForecast"),
                      "market_cap": r.get("marketCap")} for r in rows]}
```

**实测（2026-07-23/24）**：收益率曲线 3M=3.95 / 2Y=4.37 / 10Y=4.71 / 30Y=5.17
（10Y−2Y=+0.34，未倒挂）；CFTC COT 最新报告日 2026-07-14；今日财报日历 41 家
（AXP 盘前 EPS 预期 $4.41、VZ、NEE、HCA…）。

---

## 数据源优先级

| 场景 | 第一优先 | 备选 | 说明 |
|------|---------|------|------|
| 美股行情 | 新浪 `gb_XXXX` | 腾讯 / 东财 push2 | 新浪有中文名+EPS+PE |
| 港股行情 | 腾讯 `r_hkXXXXX` | 新浪 / 东财 push2 | 腾讯字段最全(78个) |
| 美股K线 | 新浪 | Yahoo chart | 新浪回溯至1984年；Yahoo支持多周期 |
| 港股K线 | Yahoo chart | — | 新浪港股K线已失效；push2his不返回港股K线 |
| 财报三表(中文) | 东财 datacenter | — | 中文科目名，按行展开 |
| 财报三表(结构化) | Yahoo quoteSummary | — | 英文，完整报表结构 |
| 关键指标(中文) | 东财 GMAININDICATOR | — | ROE/ROA/EPS/毛利率/资产负债率 (美49/港75字段) |
| 关键指标(英文) | Yahoo quoteSummary | — | PE/PB/EV/利润率/目标价 |
| 分析师预期 | Yahoo quoteSummary | — | EPS预测+评级+升降级 |
| 机构持仓 | Yahoo quoteSummary | — | 前10大机构+内部人 |
| 资金流 | 东财 push2his | — | 日级主力/大单/中单/小单 |
| **期权链/希腊字母/IV/0DTE** | **CBOE 官方** ⭐ | Yahoo options | CBOE 含 delta/gamma/vega/theta/rho；Yahoo 无希腊字母。仅美股。⚠️C 级需授权 |
| **异动 options flow** | **CBOE 官方** ⭐ | — | `unusual_activity()`：vol/OI>1 = 新建仓 |
| **全市场每日空头量** | **FINRA Reg SHO** ⭐ | — | 单文件覆盖全市场，仅美股。B 级 |
| **当日申报流(Form4/8-K/13F)** | **EDGAR 每日索引** ⭐ | — | 仅美股。**S 级可商用** |
| **申报全文检索** | **EDGAR FTS** ⭐ | — | 2001 至今正文。**S 级可商用** |
| **全市场基本面横截面** | **EDGAR frames** ⭐ | — | 免费 screener。**S 级可商用** |
| **收益率曲线 / COT / 财报日历** | **Treasury / CFTC / Nasdaq** ⭐ | — | 宏观与事件驱动 |
| SEC Filing | EDGAR | — | 官方数据，仅美股 |
| XBRL财务 | EDGAR | — | 503个GAAP指标 |
| 搜索 | 东财 search | Yahoo search | 东财有 secid 映射 |
| 新闻 | Yahoo search | — | 唯一稳定的新闻源 |
| 全市场列表 | 东财 push2 clist | — | 涨跌幅/成交量排名，美股5925+港股18000+ |

---

## 数据源汇总

| 数据源 | 合规级 | 协议 | 鉴权 | 覆盖 |
|--------|------|------|------|------|
| **SEC EDGAR** | **S** | HTTPS | 零(需真实UA) | 美股 Filing/XBRL/**每日申报流**/**全文检索**/**全市场横截面** |
| **US Treasury** | **S** | HTTPS | 零 | **收益率曲线(1M~30Y)** |
| **CFTC** | **S** | HTTPS | 零 | **COT 持仓报告** |
| **FINRA** | **B** | HTTPS | 零 | 美股 **每日空头成交量(全市场)**（商用需自行确认） |
| **CBOE** | **C** | HTTPS | 零 | 美股 **期权全链+希腊字母+IV+0DTE**（使用需 Cboe 事先授权） |
| **Nasdaq** | **C** | HTTPS | 零 | 美股 **财报日历**（条款未核实） |
| 东财 push2 | C | HTTPS | 零 | 美股+港股 实时行情+全市场列表 |
| 东财 push2his | C | HTTPS | 零 | 美股+港股 资金流（K线仅A股，不覆盖美股/港股） |
| 东财 datacenter | C | HTTPS | 零 | 美股+港股 财报三表+GMAININDICATOR关键指标 |
| 东财 search API | C | HTTPS | 零 | 全球股票搜索+secid映射 |
| Yahoo Finance | C | HTTPS | cookie+crumb(自动) | 美股+港股 全品类 |
| 新浪财经 | C | HTTP | 零 | 美股+港股 行情、美股K线 |
| 腾讯财经 | C | HTTPS | 零 | 美股+港股 行情 |

**级别含义**：**S**＝美国政府数据，可商用可再分发｜**B**＝主动公开的数据文件，商用需自行确认｜**C**＝需事先授权或条款未核实，仅个人研究。各级依据的条款原文见顶部「数据源合规分级」。

> 📦 https://github.com/simonlin1212/global-stock-data — Star ⭐ 是最好的支持
