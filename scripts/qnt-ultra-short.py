"""QNT ultra-short strategy: definition + honest backtest on real data.

Data: CoinGecko hourly (30d, ~720 points) — reachable from this network.
Tests three rule-based ultra-short styles with real fees:
  R1 1h 动量延续  : 1h 涨幅 > +1.0% 追多，止损 -1.5%，止盈 +2.0%，最长持仓 6h
  R2 1h 均值回归  : 1h 跌幅 < -1.5% 抄底，止损 -2.5%，止盈 +1.5%，最长持仓 4h
  R3 通道突破     : 突破过去 24h 高点追多，止损 -2%，用 1.5 倍 ATR 跟踪止盈
全部按 taker 5bps + 滑点 2bps（单边）计费；杠杆只影响保证金，不影响期望。
"""
import json
import statistics
import time
import urllib.request

PROXY = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
opener = urllib.request.build_opener(urllib.request.ProxyHandler(PROXY))

with opener.open("https://api.coingecko.com/api/v3/coins/quant-network/market_chart"
                 "?vs_currency=usd&days=30", timeout=40) as r:
    mc = json.loads(r.read().decode())
prices = [p for _, p in mc["prices"]]
vols = [v for _, v in mc["total_volumes"]]
n = len(prices)
print(f"QNT 小时数据 {n} 根（约 {n/24:.0f} 天）")

ret = [prices[i] / prices[i - 1] - 1 for i in range(1, n)]
hr_vol = statistics.pstdev(ret[-168:]) if n > 168 else statistics.pstdev(ret)
ann_vol = hr_vol * (24 * 365) ** 0.5
atr = statistics.mean(abs(prices[i] - prices[i - 1]) for i in range(n - 24, n))

print(f"现价 {prices[-1]:.2f} USDT")
print(f"24h {prices[-1]/prices[-25]-1:+.1%}   7d {prices[-1]/prices[-169]-1:+.1%}" if n > 169
      else f"24h {prices[-1]/prices[-25]-1:+.1%}")
print(f"小时波动率 {hr_vol:.2%}  ->  年化 {ann_vol:.0%}")
print(f"24h 平均振幅(ATR代理) {atr:.2f} USDT = {atr/prices[-1]:.2%}")

FEE = (5 + 2) / 10_000.0  # 单边


def sim(entry_sig, stop_pct, take_pct, max_hold, trail_atr=0.0):
    trades, pnls, i, held = [], [], 1, 0
    while i < n - 1:
        if entry_sig(i):
            entry = prices[i]
            exit_px = None
            for j in range(i + 1, min(i + 1 + max_hold, n)):
                lo, hi = prices[j], prices[j]
                if lo <= entry * (1 - stop_pct):
                    exit_px = entry * (1 - stop_pct)
                elif take_pct and hi >= entry * (1 + take_pct):
                    exit_px = entry * (1 + take_pct)
                elif trail_atr and held >= 1:
                    if hi < entry + trail_atr * atr * 0.5:
                        exit_px = hi
                if exit_px:
                    break
            exit_px = exit_px or prices[min(i + max_hold, n - 1)]
            gross = exit_px / entry - 1
            pnls.append(gross - 2 * FEE)
            trades.append(1)
            i += max(1, min(max_hold, 6))
        else:
            i += 1
    if not pnls:
        return 0, 0.0, 0.0, 0.0
    wins = sum(1 for p in pnls if p > 0)
    return len(pnls), sum(pnls) / len(pnls) * 10_000, sum(pnls) * 100, wins / len(pnls) * 100


RULES = {
    "R1 1h动量延续(+1%→追多)": (lambda i: ret[i - 1] > 0.010, 0.015, 0.020, 6, 0.0),
    "R2 1h均值回归(-1.5%→抄底)": (lambda i: ret[i - 1] < -0.015, 0.025, 0.015, 4, 0.0),
    "R3 24h通道突破": (lambda i: prices[i] > max(prices[max(0, i - 24):i]), 0.02, 0.0, 12, 1.0),
}

print(f"\n{'规则':26s} {'笔数':>5s} {'单笔净bps':>10s} {'累计%':>8s} {'胜率':>7s}")
print("-" * 62)
for name, (sig, stop, take, hold, trail) in RULES.items():
    t, avg, tot, wr = sim(sig, stop, take, hold, trail)
    print(f"{name:26s} {t:5d} {avg:10.2f} {tot:8.2f} {wr:6.1f}%")

# leverage survival math on the measured volatility
print("\n杠杆生存线（按当前小时波动率推演，单日 24 根的最坏波动约 "
      f"{hr_vol * 24**0.5:.1%}）：")
for lev in (2, 3, 5, 10, 20, 50):
    liq = 1 / lev * 0.95
    print(f"  {lev:2d}x -> 强平距离约 {liq:6.1%}", end="")
    print("   （单日波动即可触及）" if liq <= hr_vol * 24 ** 0.5 else "")
