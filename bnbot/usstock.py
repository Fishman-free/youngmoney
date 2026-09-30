"""US/HK equity data via zero-auth public endpoints (adopted from global-stock-data).

Source: Yahoo Finance chart v8 — no API key, no crumb for the chart endpoint.
Rows are normalised to the SAME shape our crypto pipeline uses
(open_time/open/high/low/close/volume/close_time), so the whole downstream
stack — strategy, risk, backtester, sleeves — works on equities unchanged.

    python -m bnbot.usstock --fetch SOXL,ARM --range 5y --interval 1d

Why this matters: the platform was Binance-only, so the US names the user
actually trades (SOXL, ARM, ...) could not be researched here at all.
"""

import argparse
import json
import os
import time
import urllib.parse
import urllib.request

CHART = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600,
                    "4h": 14400,   # not served by Yahoo/Eastmoney directly -> resample
                    "1d": 86400, "1wk": 604800, "1mo": 2592000}


def resample(bars, factor):
    """Aggregate `factor` consecutive bars into one (e.g. 1h -> 4h with factor=4).

    Needed because neither upstream serves 4h, while the engine's grid uses 4h+1d.
    Buckets are aligned to the first bar's open_time; the last partial bucket is
    dropped so no synthetic half-bar ever reaches the strategy layer.
    """
    out = []
    for i in range(0, len(bars) - factor + 1, factor):
        chunk = bars[i:i + factor]
        out.append({
            "open_time": chunk[0]["open_time"],
            "open": chunk[0]["open"],
            "high": max(c["high"] for c in chunk),
            "low": min(c["low"] for c in chunk),
            "close": chunk[-1]["close"],
            "volume": sum(c["volume"] for c in chunk),
            "close_time": chunk[-1]["close_time"],
        })
    return out


def _opener(proxy=None):
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener()


def fetch_chart(symbol, interval="1d", range_="5y", proxy=None, timeout=30):
    """Return normalised bars for one symbol, oldest first."""
    url = CHART.format(symbol=urllib.parse.quote(symbol)) + "?" + urllib.parse.urlencode(
        {"interval": interval, "range": range_, "includePrePost": "false"})
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with _opener(proxy).open(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode())
    err = payload.get("chart", {}).get("error")
    if err:
        raise RuntimeError(f"yahoo chart error for {symbol}: {err}")
    res = payload["chart"]["result"][0]
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    step = INTERVAL_SECONDS.get(interval, 86400)
    out = []
    for i, t in enumerate(ts):
        o, h, l, c, v = (q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i])
        if None in (o, h, l, c):        # Yahoo pads gaps with nulls
            continue
        out.append({
            "open_time": int(t) * 1000,
            "open": float(o), "high": float(h), "low": float(l), "close": float(c),
            "volume": float(v or 0.0),
            "close_time": int(t) * 1000 + step * 1000 - 1,
        })
    out.sort(key=lambda r: r["open_time"])
    return out


def equity_kline_path(data_dir, symbol, interval):
    d = os.path.join(data_dir, "equities")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{symbol}_{interval}.csv")


def save_bars(data_dir, symbol, interval, rows):
    path = equity_kline_path(data_dir, symbol, interval)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("open_time,open,high,low,close,volume,close_time\n")
        for r in rows:
            f.write(f"{r['open_time']},{r['open']},{r['high']},{r['low']},"
                    f"{r['close']},{r['volume']},{r['close_time']}\n")
    return path, len(rows)


def load_bars(data_dir, symbol, interval):
    path = equity_kline_path(data_dir, symbol, interval)
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        next(f, None)
        for line in f:
            p = line.strip().split(",")
            if len(p) != 7:
                continue
            rows.append({"open_time": int(p[0]), "open": float(p[1]), "high": float(p[2]),
                         "low": float(p[3]), "close": float(p[4]), "volume": float(p[5]),
                         "close_time": int(p[6])})
    return rows


EM_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EM_MARKETS = ("105", "106", "107")   # 105 NASDAQ / 106 NYSE / 107 AMEX (probed)
EM_KLT = {"1d": "101", "1wk": "102", "1mo": "103", "1m": "1", "5m": "5",
          "15m": "15", "30m": "30", "1h": "60"}


def fetch_chart_eastmoney(symbol, interval="1d", limit=1500, proxy=None, timeout=30):
    """Fallback equity source (Eastmoney push2his) — zero auth, CN-friendly.

    Probes the market prefixes until one returns rows, so it works for both
    NASDAQ (ARM) and NYSE-listed ETFs (SOXL).
    """
    klt = EM_KLT.get(interval, "101")
    last_err = None
    for mkt in EM_MARKETS:
        q = urllib.parse.urlencode({
            "secid": f"{mkt}.{symbol.upper()}", "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57", "klt": klt, "fqt": "1",
            "end": "20500101", "lmt": str(limit),
        })
        req = urllib.request.Request(EM_KLINE + "?" + q, headers={"User-Agent": UA})
        try:
            with _opener(proxy).open(req, timeout=timeout) as r:
                payload = json.loads(r.read().decode())
        except Exception as e:
            last_err = e
            continue
        data = (payload or {}).get("data") or {}
        klines = data.get("klines") or []
        if not klines:
            continue
        step = INTERVAL_SECONDS.get(interval, 86400)
        out = []
        for row in klines:
            p = row.split(",")
            if len(p) < 6:
                continue
            # 日期,开,收,高,低,成交量
            day = p[0]
            ts = int(time.mktime(time.strptime(day[:10], "%Y-%m-%d")) - time.timezone) * 1000
            out.append({
                "open_time": ts, "open": float(p[1]), "close": float(p[2]),
                "high": float(p[3]), "low": float(p[4]), "volume": float(p[5]),
                "close_time": ts + step * 1000 - 1,
            })
        out.sort(key=lambda r: r["open_time"])
        return out
    if last_err:
        raise last_err
    return []


def fetch_chart_any(symbol, interval="1d", range_="5y", proxy=None):
    """Try Yahoo first, then Eastmoney. Returns (rows, source)."""
    try:
        rows = fetch_chart(symbol, interval, range_, proxy=proxy)
        if rows:
            return rows, "yahoo"
    except Exception as e:
        print(f"[warn] yahoo failed for {symbol} ({type(e).__name__}: {e}); trying eastmoney")
    rows = fetch_chart_eastmoney(symbol, interval, proxy=proxy)
    return rows, "eastmoney"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bnbot.usstock", description="US/HK equity data (zero-auth)")
    ap.add_argument("--fetch", help="comma-separated tickers, e.g. SOXL,ARM")
    ap.add_argument("--interval", default="1d", choices=sorted(INTERVAL_SECONDS))
    ap.add_argument("--range", dest="range_", default="5y")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--proxy", default=None)
    args = ap.parse_args(argv)
    if not args.fetch:
        ap.print_help()
        return 1

    for sym in [s.strip().upper() for s in args.fetch.split(",") if s.strip()]:
        try:
            bars, src = fetch_chart_any(sym, args.interval, args.range_, proxy=args.proxy)
            path, n = save_bars(args.data_dir, sym, args.interval, bars)
            if bars:
                print(f"[equity] {sym:6s} {args.interval:3s} via {src:9s}: {n:5d} bars  "
                      f"{time.strftime('%Y-%m-%d', time.gmtime(bars[0]['open_time'] / 1000))} .. "
                      f"{time.strftime('%Y-%m-%d', time.gmtime(bars[-1]['open_time'] / 1000))}"
                      f"  -> {path}")
            else:
                print(f"[equity] {sym:6s} no bars returned")
        except Exception as e:
            print(f"[equity] {sym:6s} FAILED: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
