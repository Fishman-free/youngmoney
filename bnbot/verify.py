"""Signal verifier (maker-checker separation).

Loops lesson (RohOnChain 2026): the agent that generated the signal is the
worst possible judge of whether it is real alpha or noise. Every order the
strategy (maker) produces passes through this independent verifier (checker)
BEFORE execution. The verifier never sees the maker's reasoning; it applies
its own deterministic rules and returns (ok, reason). Rejected orders are
recorded to the STATE.md audit log with the reason.

Design note: in this system the checker is deterministic statistics rather
than a second LLM -- same separation principle, but reproducible and free.

Checks (new positions only; risk-reducing orders always pass):
  D1 data sanity     mark price > 0, within `mark_dev` of the last 4h close
  D2 signal agreement new-direction orders need trend and momentum to agree
  D3 volatility sanity realized vol in (0, vol_cap) annualized
"""

DEFAULTS = {
    "mark_dev": 0.05,        # mark may deviate at most 5% from cached close
    "vol_cap": 2.0,          # annualized vol above 200% -> data/sanity reject
}


class SignalVerifier:
    def __init__(self, market, marks, cfg_verify=None):
        self.market = market
        self.marks = marks
        self.p = dict(DEFAULTS)
        if cfg_verify:
            self.p.update(cfg_verify)

    def verify(self, order, ctx):
        """Return (ok, reason). Called per order, before execution."""
        s = order["symbol"]
        px = self.marks.get(s, 0.0)

        # risk-reducing orders (closing/reducing an existing position) never blocked
        if order.get("reduce_only"):
            return True, "reduce-only"

        # D1 data sanity
        if px <= 0:
            return False, "D1 mark price invalid"
        bs = self.market.klines.get((s, "4h"))
        if bs is None or len(bs) < 30:
            return False, "D1 insufficient 4h history"
        last_close = bs.close[-1]
        if last_close > 0 and abs(px / last_close - 1.0) > self.p["mark_dev"]:
            return False, f"D1 mark deviates {px / last_close - 1.0:+.2%} from close"

        # D2 signal agreement: opening in a direction requires trend AND momentum
        # to agree with the order side. (The maker may still hold conflicts --
        # the checker simply refuses to fund them with new exposure.)
        trend = ctx.trend(s)
        mom = ctx.momentum(s)
        want = 1 if order["side"] == "BUY" else -1
        if not (trend == want and mom == want):
            return False, f"D2 signal disagreement (trend={trend} mom={mom} side={want})"

        # D3 volatility sanity
        vol = ctx.realized_vol(s)
        if not (0.0 < vol <= self.p["vol_cap"]):
            return False, f"D3 vol {vol:.2f} out of range"

        return True, "ok"
