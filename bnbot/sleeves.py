"""Three-sleeve capital framework: independent capital, risk limits and kill switch.

Design (user-approved 2026-09-30):
    A  long      the validated 7-symbol trend/carry/XS engine, <=2x
    B  short      major symbols, faster lookbacks, <=3x
    C  experimental  alt high-leverage, isolated, DISABLED until the paper gate passes

Isolation guarantees (what makes this safe):
  * separate capital accounting        state/sleeves/<id>/portfolio.json
  * separate counters + audit log      state/sleeves/<id>/{metrics.json,STATE.md}
  * separate order logs                logs/sleeves/<id>/orders-*.log
  * separate KILL_SWITCH file          state/sleeves/<id>/KILL_SWITCH
  * separate risk limits               per-sleeve override of cfg["risk"]
One sleeve hitting halt or being killed cannot touch another's money, and the
aggregate is only ever a *sum for reporting*, never a shared trading pool.
"""

import copy
import os

# hard caps per sleeve id: leverage and drawdown halt cannot be relaxed by config
SLEEVE_CEILINGS = {
    "A": {"max_gross_leverage": 2.0, "drawdown_halt": 0.25, "max_symbol_weight": 0.35},
    "B": {"max_gross_leverage": 3.0, "drawdown_halt": 0.20, "max_symbol_weight": 0.50},
    "C": {"max_gross_leverage": 10.0, "drawdown_halt": 0.30, "max_symbol_weight": 1.00},
}

DEFAULT_SLEEVES = [
    {"id": "A", "name": "长线", "share": 0.6, "enabled": True},
    {"id": "B", "name": "短线", "share": 0.3, "enabled": True,
     "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
     "strategy": {"donchian_window": 24, "mom_lookback_days": 7, "xs_weight": 0.3,
                  "rebalance_band": 0.08},
     "risk": {"max_gross_leverage": 3.0, "max_symbol_weight": 0.5,
              "daily_loss_stop": 0.04, "drawdown_halt": 0.20}},
    {"id": "C", "name": "实验", "share": 0.1, "enabled": False,
     "symbols": ["DOGEUSDT", "XRPUSDT", "AVAXUSDT", "LINKUSDT"],
     "strategy": {"donchian_window": 12, "mom_lookback_days": 3, "xs_weight": 0.0,
                  "rebalance_band": 0.05, "max_vol_scale": 4.0},
     "risk": {"max_gross_leverage": 10.0, "max_symbol_weight": 1.0,
              "daily_loss_stop": 0.06, "drawdown_throttle": 0.10,
              "drawdown_halt": 0.30}},
]


def _clamp_risk(sid, risk):
    """Apply per-sleeve ceilings so config can tighten but never loosen them."""
    ceil = SLEEVE_CEILINGS.get(sid, SLEEVE_CEILINGS["C"])
    for k, cap in ceil.items():
        if k in ("max_gross_leverage", "max_symbol_weight"):
            risk[k] = min(float(risk.get(k, cap)), cap)
        else:  # drawdown_halt: a *smaller* halt is stricter
            risk[k] = min(float(risk.get(k, cap)), cap)
    return risk


def build_sleeves(cfg, base_dir=None):
    """Expand `cfg['sleeves']` into full per-sleeve config dicts.

    With no `sleeves` section the function returns [] and callers keep the
    legacy single-account behaviour.
    """
    sec = cfg.get("sleeves")
    if not sec:
        return []
    spec = sec.get("list", DEFAULT_SLEEVES) if isinstance(sec, dict) else sec
    root = base_dir or os.getcwd()
    total = float(cfg.get("capital", 10000.0))

    out = []
    for s in spec:
        sid = str(s["id"])
        state_dir = os.path.join(root, "state", "sleeves", sid)
        sleeve = copy.deepcopy(cfg)
        sleeve.pop("sleeves", None)
        sleeve["capital"] = total * float(s.get("share", 0.0))
        sleeve["symbols"] = list(s.get("symbols", cfg["symbols"]))
        sleeve["strategy"].update(s.get("strategy", {}))
        risk = dict(cfg.get("risk", {}))
        risk.update(s.get("risk", {}))
        risk["kill_switch_file"] = os.path.join(state_dir, "KILL_SWITCH")
        sleeve["risk"] = _clamp_risk(sid, risk)
        sleeve["live"] = dict(cfg["live"])
        sleeve["live"]["state_file"] = os.path.join(state_dir, "portfolio.json")
        sleeve["live"]["log_dir"] = os.path.join(root, "logs", "sleeves", sid)
        sleeve["sleeve"] = {"id": sid, "name": s.get("name", sid),
                            "share": float(s.get("share", 0.0)),
                            "enabled": bool(s.get("enabled", True)),
                            "state_dir": state_dir}
        out.append(sleeve)
    return out


def aggregate(sleeves):
    """Sum equity/cash across sleeves for reporting. Never a trading pool."""
    tot = {"sleeves": [], "capital": 0.0, "cash": 0.0, "positions": 0, "halted": []}
    for s in sleeves:
        path = s["live"]["state_file"]
        row = {"id": s["sleeve"]["id"], "name": s["sleeve"]["name"],
               "capital": s["capital"], "state_file": path}
        if os.path.exists(path):
            import json
            with open(path, encoding="utf-8") as f:
                st = json.load(f)
            row["cash"] = round(float(st.get("cash", 0.0)), 2)
            row["positions"] = len(st.get("positions", {}))
            row["peak_equity"] = round(float(st.get("peak_equity", 0.0)), 2)
            tot["cash"] += row["cash"]
            tot["positions"] += row["positions"]
        if os.path.exists(s["risk"]["kill_switch_file"]):
            tot["halted"].append(s["sleeve"]["id"])
        tot["capital"] += s["capital"]
        tot["sleeves"].append(row)
    tot["cash"] = round(tot["cash"], 2)
    tot["capital"] = round(tot["capital"], 2)
    return tot


def main(argv=None):
    """Inspect sleeves, or export one sleeve's full config for backtesting.

    python -m bnbot.sleeves --list
    python -m bnbot.sleeves --export C --out state/sleeves/C/backtest-config.json
    """
    import argparse
    import json as _json

    from .config import load_config

    ap = argparse.ArgumentParser(prog="bnbot.sleeves", description="sleeve inspector/exporter")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--export", metavar="ID", help="sleeve id to export as a full config")
    ap.add_argument("--out", default=None, help="write export here (default: stdout)")
    ap.add_argument("--base-dir", default=".")
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    sleeves = build_sleeves(cfg, base_dir=args.base_dir)
    if not sleeves:
        print("no `sleeves` section in config")
        return 1

    if args.list or not args.export:
        print(f"{'id':3s} {'name':6s} {'share':>6s} {'capital':>10s} {'maxLev':>7s} "
              f"{'ddHalt':>7s} {'symbols':<28s} enabled")
        for s in sleeves:
            m = s["sleeve"]
            print(f"{m['id']:3s} {m['name']:6s} {m['share']:6.2f} {s['capital']:10,.0f} "
                  f"{s['risk']['max_gross_leverage']:7.1f} {s['risk']['drawdown_halt']:7.2f} "
                  f"{','.join(s['symbols']):<28s} {m['enabled']}")
        return 0

    sel = [s for s in sleeves if s["sleeve"]["id"] == args.export]
    if not sel:
        print(f"unknown sleeve id: {args.export}")
        return 1
    out = sel[0]
    out.pop("sleeve", None)          # keep the exported file a plain trading config
    text = _json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        import os as _os
        _os.makedirs(_os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"exported sleeve {args.export} -> {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
