"""Sleeve paper gate: machine-checkable promotion criteria (never "looks good").

    python -m bnbot.gate --sleeve C            # human report + verdict
    python -m bnbot.gate --sleeve C --json     # machine-readable

Reads only what the sleeve actually produced:
    logs/sleeves/<id>/orders-*.log   trade count + fees paid
    state/sleeves/<id>/STATE.md      equity series (one line per round)
    state/sleeves/<id>/KILL_SWITCH   halt marker

Gates (all must pass; thresholds here, not in prose):
    G1 trades      >= 200 executed orders
    G2 expectancy  > 0 net per trade (equity change / trades)
    G3 drawdown    <= 30% peak-to-trough on the round equity series
    G4 halts       == 0 kill-switch activations

A sleeve that fails any gate stays out of real money, no matter how it feels.
"""

import argparse
import glob
import json
import os
import re
import sys

DEFAULT_GATES = {"min_trades": 200, "min_expectancy": 0.0,
                 "max_drawdown": 0.30, "max_halts": 0}


def read_trades(log_dir):
    trades, fees, symbols = 0, 0.0, set()
    for path in sorted(glob.glob(os.path.join(log_dir, "orders-*.log"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("action") == "ROUND":
                    continue
                trades += 1
                fees += float(rec.get("fee", 0.0) or 0.0)
                if rec.get("symbol"):
                    symbols.add(rec["symbol"])
    return trades, fees, sorted(symbols)


def read_equity_series(state_dir):
    p = os.path.join(state_dir, "STATE.md")
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^## \S+\s+equity=([\d,\.]+)", line.strip())
            if m:
                try:
                    out.append(float(m.group(1).replace(",", "")))
                except ValueError:
                    pass
    return out


def max_drawdown(series):
    peak, mdd = None, 0.0
    for eq in series:
        peak = eq if peak is None else max(peak, eq)
        if peak and peak > 0:
            mdd = max(mdd, 1.0 - eq / peak)
    return mdd


def evaluate(sleeve_dir, log_dir, gates=None):
    g = dict(DEFAULT_GATES)
    g.update(gates or {})
    trades, fees, symbols = read_trades(log_dir)
    series = read_equity_series(sleeve_dir)
    mdd = max_drawdown(series)
    if series and trades:
        expectancy = (series[-1] - series[0]) / trades
    else:
        expectancy = 0.0
    halt_file = os.path.join(sleeve_dir, "KILL_SWITCH")
    halts = 1 if os.path.exists(halt_file) else 0

    checks = {
        "G1_trades": {"value": trades, "need": f">= {g['min_trades']}",
                      "pass": trades >= g["min_trades"]},
        "G2_expectancy": {"value": round(expectancy, 4), "need": f"> {g['min_expectancy']}",
                          "pass": expectancy > g["min_expectancy"]},
        "G3_max_drawdown": {"value": round(mdd, 4), "need": f"<= {g['max_drawdown']}",
                            "pass": mdd <= g["max_drawdown"]},
        "G4_halts": {"value": halts, "need": f"== {g['max_halts']}",
                     "pass": halts <= g["max_halts"]},
    }
    ok = all(c["pass"] for c in checks.values())
    return {
        "sleeve_dir": sleeve_dir, "log_dir": log_dir,
        "trades": trades, "fees_paid": round(fees, 4), "symbols": symbols,
        "equity_series_points": len(series),
        "equity_start": series[0] if series else None,
        "equity_now": series[-1] if series else None,
        "checks": checks,
        "verdict": "PASS (eligible for real money after a human sign-off)" if ok else "FAIL (keep in paper)",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bnbot.gate", description="sleeve paper gate")
    ap.add_argument("--sleeve", required=True, help="sleeve id, e.g. C")
    ap.add_argument("--base-dir", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min-trades", type=int, default=DEFAULT_GATES["min_trades"])
    ap.add_argument("--max-drawdown", type=float, default=DEFAULT_GATES["max_drawdown"])
    args = ap.parse_args(argv)

    sleeve_dir = os.path.join(args.base_dir, "state", "sleeves", args.sleeve)
    log_dir = os.path.join(args.base_dir, "logs", "sleeves", args.sleeve)
    rep = evaluate(sleeve_dir, log_dir,
                   {"min_trades": args.min_trades, "max_drawdown": args.max_drawdown})
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(f"sleeve {args.sleeve} gate")
        print(f"  trades={rep['trades']}  fees={rep['fees_paid']}  "
              f"equity {rep['equity_start']} -> {rep['equity_now']}  "
              f"points={rep['equity_series_points']}")
        for name, c in rep["checks"].items():
            print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {name}: {c['value']} (need {c['need']})")
        print(f"  verdict: {rep['verdict']}")
    return 0 if rep["verdict"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
