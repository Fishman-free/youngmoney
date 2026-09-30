# Latency reality check: exchange reachability + RTT for HFT feasibility.
# Measures connect/TLS/total time to Binance and a few alternates (3 samples each).
import json
import ssl
import time
import socket
import urllib.request

PROXY = "http://127.0.0.1:7890"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))

TARGETS = [
    ("binance-fapi", "https://fapi.binance.com/fapi/v1/time"),
    ("binance-spot", "https://api.binance.com/api/v3/time"),
    ("okx", "https://www.okx.com/api/v5/public/time"),
    ("bybit", "https://api.bybit.com/v5/market/time"),
    ("gate", "https://api.gateio.ws/api/v4/spot/time"),
    ("kucoin", "https://api.kucoin.com/api/v1/timestamp"),
    ("mexc", "https://api.mexc.com/api/v3/time"),
]

print("== HTTP round trip via proxy (3 samples) ==")
for name, url in TARGETS:
    lats, code = [], None
    for _ in range(3):
        t = time.time()
        try:
            with opener.open(url, timeout=15) as r:
                r.read()
                code = r.status
            lats.append((time.time() - t) * 1000)
        except Exception as e:
            code = type(e).__name__
            break
    if lats:
        print(f"{name:14s} {code}  min {min(lats):6.0f} ms   avg {sum(lats)/len(lats):6.0f} ms")
    else:
        print(f"{name:14s} unreachable ({code})")

print("\n== raw TCP connect time to exchange hosts (proxy aside) ==")
for host in ("fapi.binance.com", "api.binance.com", "www.okx.com"):
    try:
        t = time.time()
        s = socket.create_connection((host, 443), timeout=8)
        dt = (time.time() - t) * 1000
        s.close()
        print(f"{host:22s} direct connect {dt:6.0f} ms")
    except Exception as e:
        print(f"{host:22s} direct blocked ({type(e).__name__})")
