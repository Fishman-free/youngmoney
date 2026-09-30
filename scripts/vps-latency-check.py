#!/usr/bin/env python3
"""VPS-side latency check: is this machine actually close to the exchange?

Run it ON the Tokyo VPS (no proxy — the whole point is the direct route):

    python3 scripts/vps-latency-check.py

Reports min/avg/p99 round-trip per endpoint and a verdict against what
ultra-short-horizon trading needs (< 10 ms). Also prints where the machine
thinks it is, so a "fast" result from the wrong city cannot fool you.
"""

import json
import socket
import ssl
import statistics
import sys
import time
import urllib.request

SAMPLES = 12
ENDPOINTS = [
    ("binance-fapi", "https://fapi.binance.com/fapi/v1/time"),
    ("binance-spot", "https://api.binance.com/api/v3/time"),
    ("binance-ws", "wss://fstream.binance.com/ws"),        # TCP reachability only
    ("okx", "https://www.okx.com/api/v5/public/time"),
    ("bybit", "https://api.bybit.com/v5/market/time"),
]


def http_rtt(url, n=SAMPLES):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                r.read()
            out.append((time.perf_counter() - t) * 1000)
        except Exception as e:
            return None, f"{type(e).__name__}"
        time.sleep(0.05)
    return out, None


def tcp_rtt(host, port=443, n=SAMPLES):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        try:
            s = socket.create_connection((host, port), timeout=8)
        except Exception as e:
            return None, f"{type(e).__name__}"
        out.append((time.perf_counter() - t) * 1000)
        s.close()
        time.sleep(0.05)
    return out, None


def whereami():
    try:
        with urllib.request.urlopen("http://ipinfo.io/json", timeout=8) as r:
            d = json.loads(r.read().decode())
        return f"{d.get('city')}, {d.get('country')} ({d.get('org')})"
    except Exception as e:
        return f"unknown ({type(e).__name__})"


def main():
    print(f"location : {whereami()}")
    results = {}
    for name, url in ENDPOINTS:
        if url.startswith("wss://"):
            host = url.split("//")[1].split("/")[0]
            lats, err = tcp_rtt(host)
        else:
            lats, err = http_rtt(url)
        if lats is None:
            print(f"{name:14s} FAILED ({err})")
            results[name] = None
            continue
        p99 = sorted(lats)[max(0, int(len(lats) * 0.99) - 1)]
        print(f"{name:14s} min {min(lats):6.1f}  avg {statistics.mean(lats):6.1f}  "
              f"p99 {p99:6.1f}  ms   (n={len(lats)})")
        results[name] = statistics.mean(lats)

    binance = [v for k, v in results.items() if k.startswith("binance") and v is not None]
    print()
    if not binance:
        print("VERDICT: binance unreachable from this host — do not trade here")
        return 1
    best = min(binance)
    if best < 10:
        print(f"VERDICT: {best:.1f} ms to Binance -> eligible for ultra-short horizons")
        return 0
    if best < 60:
        print(f"VERDICT: {best:.1f} ms to Binance -> fine for 1s-1m horizons, not HFT")
        return 0
    print(f"VERDICT: {best:.1f} ms to Binance -> too far; check the region (want Tokyo/ap-northeast-1)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
