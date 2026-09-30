"""Paper-trading loop (phase 1) with a deliberately unimplemented real executor.

Paper round:
    refresh cached data (incremental fetch; falls back to cache on network
    failure) -> compute target weights -> apply risk constraints -> diff
    against state/portfolio.json -> round quantities by exchangeInfo LOT_SIZE
    -> simulate fills -> append logs/orders-YYYYMMDD.log -> persist state.

State (state/portfolio.json):
    {"cash", "positions": {symbol: {"qty", "entry_price"}},
     "peak_equity", "day_start_equity", "day_key", "updated_at"}

Real-money mode: RealExecutor reads BN_API_KEY / BN_API_SECRET from the
environment (never hard-coded) and raises NotImplementedError - signing and
order placement are phase-2 work by design (paper-first).

CLI:
    python -m bnbot.live --paper --once --proxy http://127.0.0.1:7890
    python -m bnbot.live --paper          # loop every live.paper_interval_hours
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone

from .config import load_config
from .data import (
    MarketData,
    RestClient,
    fetch_premium_index,
    now_ms,
    round_step,
    symbol_filters,
    update_funding_cache,
    update_klines_cache,
)
from .risk import RiskManager
from .strategy import CompositeStrategy, Context
from .verify import SignalVerifier
from .metrics import Metrics
from .orders import mark_sim_filled, new_intent


class RealExecutor:
    """Phase-2 placeholder. Real order placement is intentionally NOT implemented.

    Credentials come from environment variables BN_API_KEY / BN_API_SECRET.
    This class never signs or sends orders in phase 1.
    """

    def __init__(self):
        self.api_key = os.environ.get("BN_API_KEY")
        self.api_secret = os.environ.get("BN_API_SECRET")

    def place_order(self, order):
        if not self.api_key or not self.api_secret:
            raise RuntimeError("BN_API_KEY / BN_API_SECRET not set in environment")
        raise NotImplementedError(
            "real-money execution is not implemented (paper-first phase 1); "
            "signed order placement is scheduled for phase 2"
        )


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------


def load_state(path, capital):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "cash": float(capital),
        "positions": {},
        "peak_equity": float(capital),
        "day_start_equity": float(capital),
        "day_key": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def save_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def mark_prices(client, symbols):
    """Live mark prices from premiumIndex; falls back to last cached 4h close."""
    out = {}
    for s in symbols:
        try:
            out[s] = fetch_premium_index(client, s)["mark_price"]
        except Exception as e:  # network hiccup -> degrade to cached close
            print(f"[warn] premiumIndex failed for {s} ({e}); using cached close")
    return out


def refresh_data(cfg, client):
    """Incrementally refresh klines + funding caches; tolerate network failure."""
    data_dir = cfg["data"]["data_dir"]
    intervals = cfg["data"].get("intervals", ["4h", "1d"])
    start_ms = now_ms() - 400 * 86_400_000  # refetch window guard for empty cache
    for sym in cfg["symbols"]:
        try:
            for itv in intervals:
                update_klines_cache(client, data_dir, sym, itv, start_ms)
            update_funding_cache(client, data_dir, sym, start_ms)
        except Exception as e:
            print(f"[warn] data refresh failed for {sym} ({e}); continuing with cache")


def append_order_log(log_dir, records):
    os.makedirs(log_dir, exist_ok=True)
    fname = os.path.join(log_dir, f"orders-{datetime.now(timezone.utc).strftime('%Y%m%d')}.log")
    with open(fname, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return fname

STATE_MD_MAX_LINES = 400  # loop lesson: state file is the audit log, keep ~400 lines


def append_state_log(path, block):
    """Append an audit block to STATE.md, rolling to ~400 lines.
    When the loop loses money this file is the only debugging surface."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    prev = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            prev = f.read().splitlines()
    lines = prev + block.splitlines() + [""]
    if len(lines) > STATE_MD_MAX_LINES:
        lines = ["(earlier history truncated; full log in logs/orders-*.log)"] + lines[-(STATE_MD_MAX_LINES - 1):]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# one paper round
# ---------------------------------------------------------------------------


def paper_round(cfg, client, mode="paper"):
    symbols = list(cfg["symbols"])
    risk = RiskManager(cfg["risk"])
    state_path = cfg["live"]["state_file"]
    log_dir = cfg["live"]["log_dir"]
    fee_rate = (float(cfg["fees"]["taker_bps"]) + float(cfg["fees"]["slippage_bps"])) / 10_000.0
    band = float(cfg["strategy"].get("rebalance_band", 0.05))

    refresh_data(cfg, client)
    market = MarketData.load(cfg["data"]["data_dir"], symbols, cfg["data"].get("intervals", ["4h", "1d"]))
    marks = mark_prices(client, symbols)
    for s in symbols:
        if s not in marks:
            marks[s] = market.klines[(s, "4h")].close[-1]

    strategy = CompositeStrategy(cfg, market)
    ctx = Context(strategy.engine, now_ms())
    raw_target = strategy.target_positions(ctx)

    state = load_state(state_path, cfg["capital"])
    positions = state.get("positions", {})

    # account equity marked at live prices
    equity = float(state["cash"]) + sum(p["qty"] * marks[s] for s, p in positions.items() if s in marks)
    day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.get("day_key") != day_key:
        state["day_key"] = day_key
        state["day_start_equity"] = equity
    cur_w = {s: (positions.get(s, {}).get("qty", 0.0) * marks[s] / equity if equity > 0 else 0.0) for s in symbols}
    target = risk.apply(raw_target, cur_w, equity=equity, peak_equity=state.get("peak_equity", equity),
                        day_start_equity=state.get("day_start_equity", equity))
    state["peak_equity"] = max(state.get("peak_equity", equity), equity)

    orders = []
    rb_mode = str(cfg["strategy"].get("rebalance_mode", "full"))
    for s in symbols:
        tw = target.get(s, 0.0)
        cur_qty = positions.get(s, {}).get("qty", 0.0)
        px = marks[s]
        filters = symbol_filters(cfg["data"]["data_dir"], s)
        cw = cur_w[s]
        flatten = tw == 0.0 and abs(cur_qty) > 0
        if not flatten and abs(tw - cw) <= band:
            continue  # inside rebalance band (parity with backtest)
        eff = tw
        if tw != 0.0 and rb_mode == "edge":
            eff = tw + (band if cw > tw else -band)  # nearest band edge
        target_qty = eff * equity / px if px > 0 else 0.0
        delta_qty = target_qty - cur_qty
        notional = abs(delta_qty) * px
        if not flatten and notional < filters["min_notional"]:
            continue
        qty = round_step(abs(delta_qty), filters["step_size"])
        if qty <= 0:
            continue
        if flatten:
            qty = abs(cur_qty)  # close the whole position
        side = "BUY" if delta_qty > 0 else "SELL"
        orders.append({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": mode, "symbol": s, "side": side, "qty": qty, "price": px,
            "notional": qty * px, "fee": qty * px * fee_rate,
            "weight_target": tw, "weight_current": cur_w[s],
            "signals": {"trend": ctx.trend(s), "mom": ctx.momentum(s),
                        "ann_funding": round(ctx.ann_funding(s), 6)},
            "reduce_only": flatten or (cur_qty != 0.0 and delta_qty * cur_qty < 0),
        })

    # maker-checker: the strategy made these orders; the verifier judges them.
    # Rejected orders never reach the simulated fills below.
    verifier = SignalVerifier(market, marks, cfg["verify"] if "verify" in cfg else None)
    accepted, rejected = [], []
    for o in orders:
        ok, reason = verifier.verify(o, ctx)
        if ok:
            accepted.append(o)
        else:
            rejected.append((o, reason))
    orders = accepted

    # probabilistic judgment gate (auxiliary): atomic battery on the state
    # snapshot; vetoes NEW exposure only. Deterministic layers outrank it.
    jcfg = cfg.get("judgment", {})
    if jcfg.get("enabled", True):
        from .judgment import JudgmentLayer, build_state_snapshot
        jlayer = JudgmentLayer(os.path.join(os.path.dirname(state_path), "judgment-log.jsonl"),
                               policy=jcfg.get("policy"))
        still_ok = []
        for o in orders:
            if o.get("reduce_only"):
                still_ok.append(o)  # risk-reducing orders never gated
                continue
            snap = build_state_snapshot(o["symbol"], ctx, equity=equity)
            allow, jreason = jlayer.gate(jlayer.ask(snap))
            if allow:
                still_ok.append(o)
            else:
                rejected.append((o, jreason))
        orders = still_ok

    # simulated fills: cash moves by signed delta notional + fee
    for o in orders:
        s = o["symbol"]
        signed = o["qty"] if o["side"] == "BUY" else -o["qty"]
        state["cash"] = float(state["cash"]) - signed * o["price"] - o["fee"]
        pos = state["positions"].setdefault(s, {"qty": 0.0, "entry_price": 0.0})
        new_qty = pos["qty"] + signed
        if abs(new_qty) < 1e-12:
            state["positions"].pop(s, None)
        else:
            pos["qty"] = new_qty
            if pos["entry_price"] == 0.0 or (pos["qty"] == 0.0):
                pos["entry_price"] = o["price"]

    summary = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode, "action": "ROUND",
        "equity": round(equity, 2), "cash": round(float(state["cash"]), 2),
        "kill_switch": risk.kill_switch_active(),
        "target_weights": {s: round(target.get(s, 0.0), 4) for s in symbols},
        "orders": len(orders), "rejected": len(rejected),
    }
    log_path = append_order_log(log_dir, orders + [summary])
    save_state(state_path, state)

    # per-cycle counters (jev-trader's `totals` block)
    rej_v = sum(1 for _, r in rejected if r.startswith("D"))
    rej_j = sum(1 for _, r in rejected if r.startswith("J"))
    records = [mark_sim_filled(new_intent(o, i)) for i, o in enumerate(orders, 1)]
    fees = sum(o["fee"] for o in orders)
    metrics = Metrics.load(os.path.join(os.path.dirname(state_path), "metrics.json"))
    metrics.cycle(orders=len(orders), rejected_verifier=rej_v, rejected_judgment=rej_j,
                  fills=len(records), late=any(r.startswith("J1") for _, r in rejected),
                  fees=fees, equity=round(equity, 2))
    metrics.save()
    summary["totals"] = metrics.to_dict()
    # STATE.md audit block (the loop's debugging surface when it loses money)
    lines = [f"## {summary['ts']}  equity={summary['equity']:,.2f}  "
             f"orders={summary['orders']}  rejected={summary['rejected']}"]
    t = summary["totals"]
    lines.append(f"totals: cycles={t['cycles']} orders={t['orders']} fills={t['fills']} "
                 f"rej_v={t['rejected_verifier']} rej_j={t['rejected_judgment']} "
                 f"late={t['late']} fees={t['fees']:.2f}")
    lines.append(f"orders: {json.dumps(records, ensure_ascii=False)[:900]}")
    lines.append("targets: " + "  ".join(f"{s}={target.get(s, 0.0):+.3f}" for s in symbols))
    for o in orders:
        lines.append(f"  EXEC {o['side']} {o['symbol']} qty={o['qty']} @ {o['price']:,.2f}"
                     f" (trend={o['signals']['trend']} mom={o['signals']['mom']})")
    for o, reason in rejected:
        lines.append(f"  REJ  {o['side']} {o['symbol']} qty={o['qty']} -> {reason}")
        if not o.get("reduce_only"):
            lines.append(f"  LESSON {summary['ts'][:10]}: new {o['side']} {o['symbol']} blocked by"
                         f" verifier ({reason.split()[0]}); check signal quality before re-entry")
    append_state_log(os.path.join(os.path.dirname(state_path), "STATE.md"), "\n".join(lines))
    return summary, orders, log_path


def run_paper(cfg, proxy, once):
    client = RestClient(proxy=proxy)
    interval_h = float(cfg["live"].get("paper_interval_hours", 4))
    while True:
        summary, orders, log_path = paper_round(cfg, client, mode="paper")
        print(f"[paper] equity={summary['equity']:,.2f} cash={summary['cash']:,.2f} "
              f"orders={summary['orders']} log={log_path}")
        for o in orders:
            print(f"  {o['side']:4} {o['symbol']} qty={o['qty']} @ {o['price']} notional={o['notional']:,.2f}")
        if once:
            return 0
        time.sleep(interval_h * 3600)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bnbot.live", description="Paper trading loop (real mode is a stub)")
    ap.add_argument("--paper", action="store_true", help="run paper trading")
    ap.add_argument("--once", action="store_true", help="single round then exit")
    ap.add_argument("--real", action="store_true", help="attempt real execution (raises NotImplementedError)")
    ap.add_argument("--proxy", default=None, help="explicit proxy, e.g. http://127.0.0.1:7890")
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.real:
        executor = RealExecutor()
        print("real mode: attempting order -> expected failure in phase 1")
        executor.place_order({"symbol": "BTCUSDT", "side": "BUY", "qty": 0.0})
        return 0
    if args.paper:
        return run_paper(cfg, args.proxy, args.once)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
