"""Paper-trading report with CHECKABLE go/no-go gates for real money.

Loop lesson (RohOnChain 2026): "a loop without a real stopping condition
fails quietly... never 'the agent says it is done'." Real-money readiness is
therefore judged by this script against hard, machine-checkable conditions.

Usage:
    python -m bnbot.report            # human summary + GO/NO-GO
    python -m bnbot.report --json     # machine-readable verdict

Gates (all must pass; thresholds live here, not in prose):
    G1 paper age        >= 60 days since first logged round
    G2 trade count      >= 30 executed orders
    G3 max drawdown     <= 25% (peak-to-trough on the round equity series)
    G4 Sharpe (ann.)    >= 0 on daily round returns
    G5 kill switch      never activated
"""

import argparse
import glob
import json
import math
import os
from datetime import datetime, timezone

GATES = {
    "min_days": 60,
    "min_trades": 30,
    "max_drawdown": 0.25,
    "min_sharpe": 0.0,
}


def load_rounds(log_dir):
    """Read all orders-*.log files -> (rounds, trades, kill_hits)."""
    rounds, trades, kill_hits = [], 0, 0
    for path in sorted(glob.glob(os.path.join(log_dir, "orders-*.log"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("action") == "ROUND":
                    rounds.append(rec)
                    if rec.get("kill_switch"):
                        kill_hits += 1
                else:
                    trades += 1
    return rounds, trades, kill_hits


def max_drawdown(equities):
    peak, mdd = None, 0.0
    for eq in equities:
        peak = eq if peak is None else max(peak, eq)
        if peak > 0:
            mdd = max(mdd, 1.0 - eq / peak)
    return mdd


def sharpe_ann(returns):
    n = len(returns)
    if n < 2:
        return 0.0
    mu = sum(returns) / n
    var = sum((r - mu) ** 2 for r in returns) / (n - 1)
    sd = math.sqrt(var)
    return (mu / sd) * math.sqrt(365.0 * 6) if sd > 0 else 0.0  # ~6 rounds/day


def evaluate(log_dir):
    rounds, trades, kill_hits = load_rounds(log_dir)
    if not rounds:
        return {"go": False, "reason": "no paper rounds logged yet", "gates": {}}
    ts0 = datetime.fromisoformat(rounds[0]["ts"].replace("Z", "+00:00"))
    ts1 = datetime.fromisoformat(rounds[-1]["ts"].replace("Z", "+00:00"))
    age_days = (ts1 - ts0).total_seconds() / 86400.0
    equities = [r["equity"] for r in rounds]
    rets = [equities[i] / equities[i - 1] - 1.0 for i in range(1, len(equities)) if equities[i - 1] > 0]
    mdd = max_drawdown(equities)
    sh = sharpe_ann(rets)

    gates = {
        "G1_paper_days": {"value": round(age_days, 1), "need": f">= {GATES['min_days']}",
                          "pass": age_days >= GATES["min_days"]},
        "G2_trades": {"value": trades, "need": f">= {GATES['min_trades']}",
                      "pass": trades >= GATES["min_trades"]},
        "G3_max_drawdown": {"value": round(mdd, 4), "need": f"<= {GATES['max_drawdown']}",
                            "pass": mdd <= GATES["max_drawdown"]},
        "G4_sharpe": {"value": round(sh, 2), "need": f">= {GATES['min_sharpe']}",
                      "pass": sh >= GATES["min_sharpe"]},
        "G5_kill_switch": {"value": kill_hits, "need": "== 0", "pass": kill_hits == 0},
    }
    go = all(g["pass"] for g in gates.values())
    return {
        "go": go,
        "verdict": "GO (verify with a human before wiring real money)" if go else "NO-GO",
        "equity_now": equities[-1], "equity_start": equities[0],
        "rounds": len(rounds), "trades": trades,
        "gates": gates,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bnbot.report", description="paper readiness report (checkable gates)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log-dir", default="logs")
    args = ap.parse_args(argv)
    rep = evaluate(args.log_dir)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    print(f"paper report  ({rep.get('checked_at', '')})")
    if "gates" not in rep:
        print("  " + rep["reason"])
        return 1
    print(f"  equity {rep['equity_start']:,.2f} -> {rep['equity_now']:,.2f}   "
          f"rounds={rep['rounds']} trades={rep['trades']}")
    for name, g in rep["gates"].items():
        print(f"  [{'PASS' if g['pass'] else 'FAIL'}] {name}: {g['value']} (need {g['need']})")
    print(f"  verdict: {rep['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
