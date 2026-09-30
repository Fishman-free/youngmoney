"""Walk-forward backtest for US equities on DAILY bars.

Equities enter the platform through bnbot/usstock.py (zero-auth sources). Their
highest reliable frequency is 1d, so this runs the same factor recipe the crypto
engine uses — Donchian breakout, time-series momentum, volatility targeting,
rebalance band — but on the daily grid, with an honest IS/OOS split.

    python -m scripts.equity_backtest --symbols SOXL,ARM --capital 10000
"""

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bnbot.usstock import load_bars  # noqa: E402

TRADING_DAYS = 252


def donchian_signal(bars, window, i):
    """+1 above the prior `window` highs, -1 below the prior lows, else 0."""
    if i < window + 1:
        return 0
    hi = max(b["high"] for b in bars[i - window:i])
    lo = min(b["low"] for b in bars[i - window:i])
    if bars[i]["close"] > hi:
        return 1
    if bars[i]["close"] < lo:
        return -1
    return 0


def run(bars, donchian=48, mom_days=30, target_vol=0.20, band=0.12,
        fee_bps=5.0, slip_bps=2.0, capital=10000.0, max_vol_scale=2.0):
    cost = (fee_bps + slip_bps) / 10_000.0
    equity, pos_w, prev_w = capital, 0.0, 0.0
    peak, mdd = capital, 0.0
    curve, trades, fees_paid = [], 0, 0.0
    rets = []
    for i in range(1, len(bars)):
        px, prev_px = bars[i]["close"], bars[i - 1]["close"]
        equity *= 1.0 + pos_w * (px / prev_px - 1.0)
        rets.append(px / prev_px - 1.0)

        trend = donchian_signal(bars, donchian, i)
        mom = 0
        if i > mom_days:
            mom = 1 if px > bars[i - mom_days]["close"] else -1
        raw = 0.5 * trend + 0.3 * mom

        lookback = rets[-30:] if len(rets) >= 30 else rets
        vol = statistics.pstdev(lookback) * (TRADING_DAYS ** 0.5) if len(lookback) > 2 else target_vol
        scale = min(max_vol_scale, target_vol / vol) if vol > 1e-9 else 1.0
        target = raw * scale

        if abs(target - pos_w) > band:
            traded = abs(target - pos_w)
            fee = traded * equity * cost
            equity -= fee
            fees_paid += fee
            trades += 1
            pos_w = target
        peak = max(peak, equity)
        mdd = max(mdd, 1.0 - equity / peak)
        curve.append(equity)
        prev_w = pos_w
    total = equity / capital - 1.0
    days = len(curve) or 1
    ann = (1 + total) ** (TRADING_DAYS / days) - 1 if total > -1 else -1.0
    daily = [curve[i] / curve[i - 1] - 1 for i in range(1, len(curve)) if curve[i - 1] > 0]
    mu = statistics.mean(daily) if daily else 0.0
    sd = statistics.pstdev(daily) if len(daily) > 1 else 0.0
    sharpe = (mu / sd) * (TRADING_DAYS ** 0.5) if sd > 0 else 0.0
    return {"final": equity, "total": total, "ann": ann, "sharpe": sharpe,
            "mdd": mdd, "trades": trades, "fees": fees_paid,
            "vol": sd * (TRADING_DAYS ** 0.5) if sd else 0.0, "days": days}


def report(name, r, label):
    print(f"  {label:26s} final {r['final']:9,.0f}  ann {r['ann']:+7.2%}  "
          f"vol {r['vol']:6.2%}  Sharpe {r['sharpe']:5.2f}  maxDD {r['mdd']:6.2%}  "
          f"trades {r['trades']:4d}  fees {r['fees']:8,.0f}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scripts.equity_backtest")
    ap.add_argument("--symbols", default="SOXL,ARM")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--capital", type=float, default=10000.0)
    ap.add_argument("--split", type=float, default=0.7, help="IS fraction (walk-forward)")
    args = ap.parse_args(argv)

    for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        bars = load_bars(args.data_dir, sym, "1d")
        if len(bars) < 120:
            print(f"{sym}: not enough daily bars ({len(bars)}); run "
                  f"`python -m bnbot.usstock --fetch {sym}` first")
            continue
        cut = int(len(bars) * args.split)
        print(f"\n== {sym}  {len(bars)} daily bars  "
              f"{'-'.join(str(x) for x in [1970])if False else ''}"
              f"(IS {cut} / OOS {len(bars) - cut}) ==")
        report(sym, run(bars[:cut], capital=args.capital), "IS  (in-sample)")
        report(sym, run(bars[cut:], capital=args.capital), "OOS (out-of-sample)")
        report(sym, run(bars, capital=args.capital), "FULL period")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
