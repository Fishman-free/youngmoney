"""Micro-horizon honest backtest: can 1-minute strategies survive fees?

Data: MEXC 1m klines (reachable from this network; ~550-880ms RTT).
Fees modelled BOTH ways: taker 5bps + slippage 2bps each side, and a
maker-rebate-ish best case of 2bps + 0 slippage.

Strategies tested (all long-only, 1 contract, no leverage):
  S1 1m mean reversion : buy after a -0.3% 1m candle, exit after +0.15% or 5 min
  S2 1m momentum       : buy after a +0.3% 1m candle, exit after +0.15% or 5 min
  S3 taker-flow fade   : buy when taker-buy share < 0.35 (seller exhaustion), exit 3 min

Every trade pays fees on entry and exit; expectancy is reported net of fees.
"""
import json
import time
import urllib.request

PROXY = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
opener = urllib.request.build_opener(urllib.request.ProxyHandler(PROXY))
BASE = "https://api.mexc.com/api/v3/klines"


def klines(symbol="BTCUSDT", interval="1m", limit=1000, end=None):
    q = f"?symbol={symbol}&interval={interval}&limit={limit}"
    if end:
        q += f"&endTime={end}"
    with opener.open(BASE + q, timeout=30) as r:
        return json.loads(r.read().decode())


bars = []
end = None
for _ in range(6):  # ~6000 minutes ≈ 4 days
    batch = klines(end=end)
    if not batch:
        break
    bars = batch + bars
    end = batch[0][0] - 1
    time.sleep(0.3)
bars = [b for b in bars if isinstance(b, list) and len(b) >= 6]
print(f"1m bars: {len(bars)}  span {time.strftime('%m-%d %H:%M', time.gmtime(bars[0][0]/1000))} -> "
      f"{time.strftime('%m-%d %H:%M', time.gmtime(bars[-1][0]/1000))} UTC")

if len(bars) < 500:
    raise SystemExit("not enough bars")

o = [float(b[1]) for b in bars]
h = [float(b[2]) for b in bars]
l = [float(b[3]) for b in bars]
c = [float(b[4]) for b in bars]
vol = [float(b[5]) for b in bars]
tb = [float(b[9]) if len(b) > 9 and b[9] not in (None, "") else vol[i] * 0.5
      for i, b in enumerate(bars)]  # taker buy base volume


def backtest(signal, exit_rule, fee_bps_side, slippage_bps_side=0.0):
    cost = 2 * (fee_bps_side + slippage_bps_side) / 10_000.0
    trades, pnls = 0, []
    i = 1
    while i < len(c) - 1:
        if signal(i):
            entry = c[i]
            j = i + 1
            while j < min(i + 60, len(c)):
                if exit_rule(i, j, entry):
                    break
                j += 1
            if j >= len(c):
                break
            gross = c[j] / entry - 1.0
            pnls.append(gross - cost)
            trades += 1
            i = j + 1
        else:
            i += 1
    if not trades:
        return 0, 0.0, 0.0, 0.0
    wins = sum(1 for p in pnls if p > 0)
    avg = sum(pnls) / trades
    tot = sum(pnls)
    return trades, avg * 10_000, tot * 100, wins / trades


SIGS = {
    "S1 1m均值回归(-0.3%)": (lambda i: c[i] / c[i - 1] - 1 < -0.003,
                             lambda i, j, e: c[j] / e - 1 >= 0.0015 or c[j] / e - 1 <= -0.004),
    "S2 1m动量(+0.3%)": (lambda i: c[i] / c[i - 1] - 1 > 0.003,
                         lambda i, j, e: c[j] / e - 1 >= 0.0015 or c[j] / e - 1 <= -0.004),
    "S3 taker卖压衰竭": (lambda i: tb[i] / max(vol[i], 1e-9) < 0.35,
                         lambda i, j, e: j >= i + 3),
}

print(f"\n{'策略':22s} {'笔数':>5s} {'单笔净bps':>10s} {'累计%':>8s} {'胜率':>7s}")
print("-" * 60)
for name, (sig, ex) in SIGS.items():
    for label, fee, slip in (("taker 5+2bps", 5.0, 2.0), ("maker 2+0bps", 2.0, 0.0)):
        t, avg_bps, tot_pct, wr = backtest(sig, ex, fee, slip)
        print(f"{name+' ['+label+']':22s} {t:5d} {avg_bps:10.2f} {tot_pct:8.2f} {wr*100:6.1f}%")

print("\n判读：单笔净 bps 为正才有意义；累计% 是该窗口全仓单倍杠杆的结果（未计复利）。")
