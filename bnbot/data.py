"""REST data access + CSV cache for Binance USDT-M futures (public endpoints).

Network behaviour
-----------------
- All calls go through urllib, which honors HTTPS_PROXY / HTTP_PROXY env vars
  by default.  An explicit proxy can be forced with `--proxy http://127.0.0.1:7890`.
- Primary host is https://fapi.binance.com.  If it times out or answers with a
  geo-block (HTTP 403/451), the client falls back to the www.binance.com mirror
  which serves the identical /fapi/v1 API.  The first host that works is reused.
- Caches live in data/ as CSV (klines / funding) and JSON (exchangeInfo).
  Fetching is incremental: only the missing tail of each series is downloaded.
- Rate limiting: sleep between requests, far below the 2400 weight/min budget
  (a 1500-bar kline request costs weight 10).

CLI
---
    python -m bnbot.data --fetch --proxy http://127.0.0.1:7890
"""

import argparse
import bisect
import csv
import json
import math
import os
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

PRIMARY_BASE = "https://fapi.binance.com"
FALLBACK_BASES = ("https://www.binance.com",)

MS_PER_HOUR = 3_600_000
MS_PER_DAY = 86_400_000
MS_PER_YEAR = 365.25 * MS_PER_DAY

INTERVAL_MS = {
    "15m": 15 * 60_000,
    "1h": MS_PER_HOUR,
    "4h": 4 * MS_PER_HOUR,
    "1d": MS_PER_DAY,
}

KLINES_LIMIT = 1500
FUNDING_LIMIT = 1000
DEFAULT_SLEEP_SECONDS = 0.6  # between REST calls; safe vs. 2400 weight/min
FUNDING_GRACE_MS = 60_000  # fundingTime is occasionally boundary+1ms


def now_ms():
    return int(time.time() * 1000)


def parse_dt_ms(s):
    """Parse '2024-01-01' or '2024-01-01T00:00:00' (UTC) or epoch-ms string."""
    import datetime as _dt

    s = str(s).strip()
    if s.isdigit():
        return int(s)
    fmt = "%Y-%m-%dT%H:%M:%S" if "T" in s else "%Y-%m-%d"
    return int(_dt.datetime.strptime(s, fmt).replace(tzinfo=_dt.timezone.utc).timestamp() * 1000)


def fmt_dt(ms):
    import datetime as _dt

    return _dt.datetime.fromtimestamp(ms / 1000, tz=_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# HTTP client with mirror fallback
# ---------------------------------------------------------------------------


class RestClient:
    """GET JSON from Binance futures API with automatic mirror fallback."""

    def __init__(self, proxy=None, timeout=30, sleep=DEFAULT_SLEEP_SECONDS):
        if proxy:
            handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            self.opener = urllib.request.build_opener(handler)
        else:
            # empty build_opener still honors HTTPS_PROXY/HTTP_PROXY env vars
            self.opener = urllib.request.build_opener()
        self.timeout = timeout
        self.sleep = sleep
        self._base = None

    def get_json(self, path):
        bases = []
        if self._base:
            bases.append(self._base)
        bases += [b for b in (PRIMARY_BASE,) + FALLBACK_BASES if b not in bases]
        last_err = None
        for base in bases:
            try:
                req = urllib.request.Request(
                    base + path, headers={"User-Agent": "bnbot/0.1 (research)"}
                )
                with self.opener.open(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                self._base = base
                time.sleep(self.sleep)
                return data
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (403, 451):  # geo-blocked -> try next mirror
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
                continue
        raise ConnectionError(f"all binance hosts failed for {path}: {last_err}")


# ---------------------------------------------------------------------------
# REST fetchers (raw rows)
# ---------------------------------------------------------------------------


def fetch_klines(client, symbol, interval, start_ms, end_ms=None):
    """Fetch klines with open_time in [start_ms, end_ms). Closed bars only,
    deduplicated and sorted ascending. Returns list[dict]."""
    step = INTERVAL_MS[interval]
    rows = {}
    cursor = start_ms
    while True:
        path = (
            f"/fapi/v1/klines?symbol={symbol}&interval={interval}"
            f"&startTime={cursor}&limit={KLINES_LIMIT}"
        )
        if end_ms is not None:
            path += f"&endTime={end_ms - 1}"
        batch = client.get_json(path)
        if not batch:
            break
        for k in batch:
            rows[int(k[0])] = {
                "open_time": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": int(k[6]),
            }
        cursor = int(batch[-1][0]) + step
        if len(batch) < KLINES_LIMIT or (end_ms is not None and cursor >= end_ms):
            break
    cutoff = now_ms()
    return [rows[t] for t in sorted(rows) if rows[t]["close_time"] < cutoff]


MEXC_BASE = "https://api.mexc.com"
MEXC_INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                 "1h": "60m", "4h": "4h", "1d": "1d"}


def fetch_klines_mexc(symbol, interval, start_ms, end_ms=None, proxy=None):
    """Fallback kline source (MEXC spot) with a Binance-compatible row shape.

    Used when the Binance endpoints are geo-blocked or unreachable, so a symbol
    can still be researched. Rows are normalised to the same dict shape as
    fetch_klines, which keeps cache files and everything downstream portable.
    """
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        opener = urllib.request.build_opener()
    itv = MEXC_INTERVAL.get(interval, interval)
    step = INTERVAL_MS[interval]
    rows = {}
    cursor = start_ms
    while True:
        q = f"?symbol={symbol}&interval={itv}&startTime={cursor}&limit={KLINES_LIMIT}"
        if end_ms is not None:
            q += f"&endTime={end_ms - 1}"
        req = urllib.request.Request(MEXC_BASE + "/api/v3/klines" + q,
                                     headers={"User-Agent": "bnbot/0.1 (research)"})
        with opener.open(req, timeout=30) as r:
            batch = json.loads(r.read().decode())
        if not batch:
            break
        for k in batch:
            rows[int(k[0])] = {
                "open_time": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": int(k[6]),
            }
        cursor = int(batch[-1][0]) + step
        if len(batch) < KLINES_LIMIT:
            break
    cutoff = now_ms()
    return [rows[t] for t in sorted(rows) if rows[t]["close_time"] < cutoff]


def fetch_funding(client, symbol, start_ms, end_ms=None):
    """Fetch funding-rate events in [start_ms, end_ms); sorted, deduplicated."""
    rows = {}
    cursor = start_ms
    while True:
        path = f"/fapi/v1/fundingRate?symbol={symbol}&startTime={cursor}&limit={FUNDING_LIMIT}"
        if end_ms is not None:
            path += f"&endTime={end_ms - 1}"
        batch = client.get_json(path)
        if not batch:
            break
        for r in batch:
            rows[int(r["fundingTime"])] = {
                "funding_time": int(r["fundingTime"]),
                "funding_rate": float(r["fundingRate"]),
            }
        cursor = int(batch[-1]["fundingTime"]) + 1
        if len(batch) < FUNDING_LIMIT or (end_ms is not None and cursor >= end_ms):
            break
    return [rows[t] for t in sorted(rows)]


def fetch_premium_index(client, symbol):
    """Latest mark/index price snapshot (no cache; live use only)."""
    d = client.get_json(f"/fapi/v1/premiumIndex?symbol={symbol}")
    return {
        "symbol": d.get("symbol", symbol),
        "mark_price": float(d["markPrice"]),
        "index_price": float(d["indexPrice"]),
        "time": int(d.get("time", 0)),
    }


def fetch_exchange_info(client):
    return client.get_json("/fapi/v1/exchangeInfo")


# ---------------------------------------------------------------------------
# CSV / JSON cache
# ---------------------------------------------------------------------------

KLINE_FIELDS = ("open_time", "open", "high", "low", "close", "volume", "close_time")
FUNDING_FIELDS = ("funding_time", "funding_rate")


def kline_path(data_dir, symbol, interval):
    return os.path.join(data_dir, f"{symbol}_{interval}.csv")


def funding_path(data_dir, symbol):
    return os.path.join(data_dir, f"{symbol}_funding.csv")


def exchange_info_path(data_dir):
    return os.path.join(data_dir, "exchangeInfo.json")


def _write_csv(path, fieldnames, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)  # atomic on same volume


def _read_csv(path, fieldnames):
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_klines_csv(path):
    if not os.path.exists(path):
        return []
    out = []
    for row in _read_csv(path, KLINE_FIELDS):
        out.append(
            {
                "open_time": int(row["open_time"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "close_time": int(row["close_time"]),
            }
        )
    return out


def load_funding_csv(path):
    if not os.path.exists(path):
        return []
    return [
        {
            "funding_time": int(r["funding_time"]),
            "funding_rate": float(r["funding_rate"]),
        }
        for r in _read_csv(path, FUNDING_FIELDS)
    ]


def update_klines_cache(client, data_dir, symbol, interval, start_ms, end_ms=None):
    """Incrementally refresh one kline cache file. Returns (n_rows, first_ts, last_ts)."""
    path = kline_path(data_dir, symbol, interval)
    existing = load_klines_csv(path)
    if existing:
        fetch_from = existing[-1]["open_time"] + INTERVAL_MS[interval]
    else:
        fetch_from = start_ms
    if fetch_from < (end_ms or now_ms()):
        try:
            new_rows = fetch_klines(client, symbol, interval, fetch_from, end_ms)
        except Exception as e:  # geo-block / outage -> alternate venue
            print(f"[warn] binance klines failed for {symbol} {interval} ({e}); "
                  f"falling back to MEXC")
            new_rows = fetch_klines_mexc(symbol, interval, fetch_from, end_ms,
                                        proxy=getattr(client, "proxy", None))
    else:
        new_rows = []
    merged = {r["open_time"]: r for r in existing}
    for r in new_rows:
        merged[r["open_time"]] = r
    rows = [merged[t] for t in sorted(merged)]
    if rows:
        _write_csv(path, KLINE_FIELDS, rows)
    return len(rows), rows[0]["open_time"] if rows else 0, rows[-1]["open_time"] if rows else 0


def update_funding_cache(client, data_dir, symbol, start_ms, end_ms=None):
    path = funding_path(data_dir, symbol)
    existing = load_funding_csv(path)
    if existing:
        fetch_from = existing[-1]["funding_time"] + 1
    else:
        fetch_from = start_ms
    new_rows = fetch_funding(client, symbol, fetch_from, end_ms) if fetch_from < (end_ms or now_ms()) else []
    merged = {r["funding_time"]: r for r in existing}
    for r in new_rows:
        merged[r["funding_time"]] = r
    rows = [merged[t] for t in sorted(merged)]
    if rows:
        _write_csv(path, FUNDING_FIELDS, rows)
    return len(rows), rows[0]["funding_time"] if rows else 0, rows[-1]["funding_time"] if rows else 0


def update_exchange_info_cache(client, data_dir):
    info = fetch_exchange_info(client)
    path = exchange_info_path(data_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f)
    return path


def symbol_filters(data_dir, symbol, allow_synthetic=False):
    """Trading rules for one symbol from the cached exchangeInfo.

    Returns dict with price_precision, quantity_precision, step_size,
    min_qty, min_notional.  Used for order quantity rounding.

    Strict by default: an unknown symbol raises, because trading on invented
    step sizes is how orders get rejected or mis-sized. Paper mode may pass
    allow_synthetic=True for symbols sourced from an alternate venue (MEXC);
    those rows are flagged `synthetic` so a real executor can refuse them.
    """
    with open(exchange_info_path(data_dir), "r", encoding="utf-8") as f:
        info = json.load(f)
    for s in info["symbols"]:
        if s["symbol"] == symbol:
            lot = next(x for x in s["filters"] if x["filterType"] == "LOT_SIZE")
            notional = next(
                (x for x in s["filters"] if x["filterType"] == "MIN_NOTIONAL"), {"notional": "0"}
            )
            return {
                "price_precision": int(s.get("pricePrecision", 2)),
                "quantity_precision": int(s.get("quantityPrecision", 3)),
                "step_size": float(lot["stepSize"]),
                "min_qty": float(lot["minQty"]),
                "min_notional": float(notional.get("notional", 0.0)),
            }
    # Symbols sourced from an alternate venue (e.g. MEXC) are not in Binance's
    # exchangeInfo. Paper mode may proceed on conservative synthetic filters;
    # real mode must not (the flag lets an executor refuse).
    if allow_synthetic:
        print(f"[warn] symbol {symbol} not in exchangeInfo cache; using synthetic filters "
              f"(paper mode)")
        return {
            "price_precision": 4,
            "quantity_precision": 4,
            "step_size": 0.0001,
            "min_qty": 0.0001,
            "min_notional": 1.0,
            "synthetic": True,
        }
    raise KeyError(f"symbol {symbol} not found in exchangeInfo cache")


def round_step(qty, step_size):
    """Floor quantity to the exchange lot step (never round up into more risk)."""
    if step_size <= 0:
        return qty
    return math.floor(qty / step_size + 1e-9) * step_size


# ---------------------------------------------------------------------------
# In-memory market view
# ---------------------------------------------------------------------------


class BarSeries:
    """OHLCV arrays for one (symbol, interval); parallel lists, ascending time."""

    __slots__ = ("symbol", "interval", "open_time", "open", "high", "low", "close", "volume", "close_time")

    def __init__(self, symbol, interval, rows):
        self.symbol = symbol
        self.interval = interval
        self.open_time = [r["open_time"] for r in rows]
        self.open = [r["open"] for r in rows]
        self.high = [r["high"] for r in rows]
        self.low = [r["low"] for r in rows]
        self.close = [r["close"] for r in rows]
        self.volume = [r["volume"] for r in rows]
        self.close_time = [r["close_time"] for r in rows]

    def __len__(self):
        return len(self.open_time)


class MarketData:
    """Container for cached klines and funding across symbols."""

    def __init__(self):
        self.klines = {}  # (symbol, interval) -> BarSeries
        self.funding = {}  # symbol -> {"times": [int], "rates": [float]}

    @classmethod
    def load(cls, data_dir, symbols, intervals):
        md = cls()
        for sym in symbols:
            for itv in intervals:
                rows = load_klines_csv(kline_path(data_dir, sym, itv))
                if not rows:
                    raise FileNotFoundError(
                        f"missing cache {kline_path(data_dir, sym, itv)}; "
                        "run `python -m bnbot.data --fetch` first"
                    )
                md.klines[(sym, itv)] = BarSeries(sym, itv, rows)
            frows = load_funding_csv(funding_path(data_dir, sym))
            md.funding[sym] = {
                "times": [r["funding_time"] for r in frows],
                "rates": [r["funding_rate"] for r in frows],
            }
        return md

    def funding_event_at(self, symbol, ts):
        """(funding_time, rate) of the latest event with time <= ts + grace, else None."""
        f = self.funding.get(symbol)
        if not f or not f["times"]:
            return None
        i = bisect.bisect_right(f["times"], ts + FUNDING_GRACE_MS) - 1
        if i < 0:
            return None
        return f["times"][i], f["rates"][i]


class AlignedBars:
    """Union 4h grid across symbols with forward-filled closes (None before
    a symbol's first bar). Backtests iterate the grid; every decision uses
    only bars closed strictly before the grid timestamp (no lookahead)."""

    def __init__(self, grid, closes):
        self.grid = grid  # list[int] ascending
        self.closes = closes  # symbol -> list[float|None] aligned with grid

    @classmethod
    def build(cls, market, symbols, interval="4h"):
        union = set()
        for sym in symbols:
            union.update(market.klines[(sym, interval)].open_time)
        grid = sorted(union)
        closes = {}
        for sym in symbols:
            bs = market.klines[(sym, interval)]
            by_time = dict(zip(bs.open_time, bs.close))
            closes[sym] = [by_time.get(t) for t in grid]
        return cls(grid, closes)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    from .config import load_config

    ap = argparse.ArgumentParser(prog="bnbot.data", description="Fetch Binance futures data to CSV cache")
    ap.add_argument("--fetch", action="store_true", help="incrementally fetch klines + funding")
    ap.add_argument("--proxy", default=None, help="explicit proxy, e.g. http://127.0.0.1:7890")
    ap.add_argument("--config", default=None, help="path to config.json")
    ap.add_argument("--symbols", default=None, help="comma-separated override, e.g. BTCUSDT,ETHUSDT")
    ap.add_argument("--start", default=None, help="first bar date (UTC), default from config")
    ap.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS, help="seconds between REST calls")
    args = ap.parse_args(argv)

    if not args.fetch:
        ap.print_help()
        return 1

    cfg = load_config(args.config)
    symbols = args.symbols.split(",") if args.symbols else cfg["symbols"]
    intervals = cfg["data"].get("intervals", ["4h", "1d"])
    start_ms = parse_dt_ms(args.start) if args.start else parse_dt_ms(cfg["data"].get("start", "2024-01-01"))
    data_dir = cfg["data"]["data_dir"]
    os.makedirs(data_dir, exist_ok=True)

    client = RestClient(proxy=args.proxy, sleep=args.sleep)
    for sym in symbols:
        for itv in intervals:
            n, first, last = update_klines_cache(client, data_dir, sym, itv, start_ms)
            print(f"[klines ] {sym} {itv:>3}: {n:>6} bars  {fmt_dt(first)} .. {fmt_dt(last)}" if n else f"[klines ] {sym} {itv:>3}: empty")
        n, first, last = update_funding_cache(client, data_dir, sym, start_ms)
        print(f"[funding] {sym}     : {n:>6} events {fmt_dt(first)} .. {fmt_dt(last)}" if n else f"[funding] {sym}     : empty")

    info_path = update_exchange_info_cache(client, data_dir)
    print(f"[rules  ] exchangeInfo -> {info_path}")
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
