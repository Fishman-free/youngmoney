"""Probabilistic judgment layer (auxiliary decision support).

Architecture rule (RohOnChain 2101311813908652069, the Jev blueprint):
    Code calculates the state.  The judgment engine interprets the state.
    Code applies policy.          Execution places the order.

Everything computable stays in deterministic code (strategy/risk/verify).
This module owns only the fuzzy judgments: regime, overreaction risk, setup
quality -- asked as ATOMIC questions in one battery call, combined with fixed
weights in code. Thresholds live here, never in the model. The hard risk layer
and SignalVerifier always win; this gate can only veto NEW exposure.

Engine: laya (open-source non-autoregressive System-1 decision engine, the
same species as TypeSafe Jev). Optional dependency -- if laya is missing or
errors, the layer degrades to pass-through (fallback ladder) and says so.

Load discipline (2026-10-06): "the auxiliary layer must never paralyse the main
loop" is easy to satisfy for a missing or throwing import, but a *hang* is not
an exception and cannot be caught. Measured failure, twice:

  1. `laya.Router()` construction returns instantly -- the model load is LAZY
     and happens inside the first `predict()` (laya/router.py `load()` ->
     `Agent.__init__` -> `snapshot_download`). Bounding the constructor guards
     nothing.
  2. huggingface_hub >= 1.x pulls checkpoints through the Xet backend (hf_xet,
     a Rust client) that ignores HTTPS_PROXY. On this proxy-only network the
     fetch stalled at 0 bytes for 12+ minutes with the process idle on I/O
     (thread dump: httpx -> httpcore -> ssl.read), while the same file came down
     fine over plain HTTPS through the proxy (HTTP 206, 3.7s).

So every battery call now runs in a daemon thread with a hard bound --
`load_timeout_s` for the first (model-loading) call, `battery_timeout_s`
afterwards. Exceeding it marks the engine dead for the rest of the round and the
layer degrades to pass-through. HF_HUB_DISABLE_XET=1 is set below, before any
import, to keep the classic HTTP path.

Every call logs (snapshot, questions, answers) plus later outcome to
state/judgment-log.jsonl as calibration triples (Brier/ECE once enough
outcomes accumulate). Timestamp discipline: the snapshot is built ONLY from
information strictly before the decision time.
"""

import json
import os
import threading
import time
from datetime import datetime, timezone

# Must be set before huggingface_hub is imported anywhere (laya imports it).
# Without this the checkpoint download hangs instead of failing, which stalls
# the entire paper round. See the "Load discipline" note above.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# policy thresholds live in code (edit a coefficient, not a prompt)
POLICY = {
    "min_confidence": 0.50,     # abstain (veto new exposure) below answer_confidence
    "min_setup": 1.5,           # score 0-3 rubric
    "max_toxicity": 0.70,       # noul: P(overreaction) too high -> veto
    "max_risk_elevated": 0.75,  # risk analyst: P(downside elevated) too high -> veto
    "battery_timeout_s": 10.0,  # warm-call bound; on exceed -> hold (veto)
    "load_timeout_s": 300.0,    # first call also pays the lazy model load
    "on_missing": "pass",       # auxiliary layer: degrade to pass-through
}

BATTERY = {
    "regime": {
        "type": "choice",
        "instructions": "Which market regime best describes this state?",
        "criteria": {
            "trending": "sustained directional movement, breakouts holding",
            "mean_reverting": "range-bound, moves fading back",
            "chaotic": "erratic, no clear structure",
        },
    },
    "toxicity": {
        "type": "noul",
        "instructions": "Is the recent move likely a liquidity-driven overreaction that will fade?",
    },
    "setup": {
        "type": "score",
        "instructions": "How clean and tradeable is the current setup?",
        "criteria": ["no setup", "weak", "decent", "clean"],
    },
    # analyst roles, adopted from TradingAgents-astock's multi-analyst layout:
    # each role answers one narrow question, and the policy in code weighs them.
    "trend_analyst": {
        "type": "choice",
        "instructions": "As a trend analyst: what is the prevailing trend?",
        "criteria": {"strong_up": "clear higher highs and higher lows",
                     "weak_up": "drifting up, momentum fading",
                     "sideways": "no direction",
                     "weak_down": "drifting down, selling easing",
                     "strong_down": "clear lower highs and lower lows"},
    },
    "risk_analyst": {
        "type": "noul",
        "instructions": "As a risk analyst: is downside risk elevated right now?",
    },
    "flow_analyst": {
        "type": "noul",
        "instructions": "As a flow analyst: is the participation behind this move supportive?",
    },
}


def build_state_snapshot(sym, ctx, equity=None, drawdown=None, closes=None,
                         highs=None, lows=None):
    """Compact numeric state text from info strictly before ctx.ts.

    When OHLC arrays are supplied, the classic indicators (RSI/MACD/布林/ATR,
    adopted from global-stock-data's indicator layer) are folded into the
    snapshot, so the judgment engine reasons over the same numbers the strategy
    does instead of only the composite signals.
    """
    trend = ctx.trend(sym)
    mom = ctx.momentum(sym)
    vol = ctx.realized_vol(sym)
    ann = ctx.ann_funding(sym)
    parts = [
        f"symbol {sym}",
        f"trend_signal {trend}",
        f"momentum_30d {mom}",
        f"realized_vol {vol:.3f}",
        f"funding_ann {ann:.4f}",
    ]
    if closes and len(closes) >= 30:
        from .indicators import macd, rsi, sma
        r14 = rsi(closes, 14)
        m = macd(closes)
        last = closes[-1]
        ma20 = sma(closes, 20)[-1]
        hist = m["hist"][-1]
        if r14[-1] is not None:
            parts.append(f"rsi14 {r14[-1]:.1f}")
        if hist is not None:
            parts.append(f"macd_hist {'pos' if hist > 0 else 'neg'}")
        if ma20:
            parts.append(f"price_vs_ma20 {'above' if last > ma20 else 'below'}")
    if equity is not None:
        parts.append(f"equity {equity:.0f}")
    if drawdown is not None:
        parts.append(f"drawdown {drawdown:.3f}")
    return " | ".join(parts)


class JudgmentLayer:
    def __init__(self, log_path, policy=None):
        self.p = dict(POLICY)
        if policy:
            self.p.update(policy)
        self.log_path = log_path
        self._router = None
        self._engine = "none"
        self._warm = False     # a predict has returned -> the model is loaded
        self._dead = False     # engine hung once -> stop paying the bound per order

    def _get_router(self):
        """Construct the router.

        Cheap: laya loads the model LAZILY inside the first predict(), so this
        only exercises the import. Bounding it would guard nothing.
        """
        if self._router is None:
            from laya import Router   # optional dependency
            self._router = Router()
            self._engine = "laya"
        return self._router

    def ask(self, snapshot):
        """Run the atomic battery on one snapshot, hard-bounded.

        Returns the answers dict, or None to degrade to pass-through. The work
        runs in a daemon thread because a HANG (stuck checkpoint download) is not
        an exception and cannot be caught -- unbounded it blocks the paper round
        and the 4h loop behind it forever. The first call also pays the lazy
        model load, so it gets `load_timeout_s`; warm calls get
        `battery_timeout_s`.
        """
        if self._dead:
            return None
        bound = self.p["battery_timeout_s"] if self._warm else self.p["load_timeout_s"]
        box = {}

        def _work():
            try:
                router = self._get_router()
                t0 = time.time()  # deadline applies to the decision, not model load
                box["result"] = router.predict(snapshot, BATTERY)
                box["elapsed"] = time.time() - t0
            except BaseException as e:    # noqa: BLE001 - never kill the main loop
                box["error"] = type(e).__name__

        t = threading.Thread(target=_work, daemon=True, name="laya-ask")
        t.start()
        t.join(float(bound))
        if t.is_alive():
            # Hung, not failing: give up on the engine for the rest of this round
            # instead of paying the bound again for every remaining order.
            self._dead = True
            self._log(snapshot, None, "timeout")
            return None
        if "error" in box:
            self._log(snapshot, None, f"error:{box['error']}")
            return None
        self._warm = True
        if box.get("elapsed", 0.0) > self.p["battery_timeout_s"]:
            self._log(snapshot, None, "timeout")
            return None
        answers = (box.get("result") or {}).get("answers", {})
        self._log(snapshot, answers, "ok")
        return answers

    def gate(self, answers, side=None):
        """Policy gate in code: (allow_new_exposure, reason).
        None answers follow policy on_missing: 'hold' (deadline rule) or
        'pass' (auxiliary layer degrades to pass-through).

        `side` (BUY/SELL) lets the analyst roles vote on direction; they can only
        veto, never amplify.
        """
        if not answers:
            allow = self.p.get("on_missing", "pass") == "pass"
            return allow, f"J1 no judgment (on_missing={self.p.get('on_missing', 'pass')})"
        # laya semantics: answer_confidence = P(selected answer); the bare
        # 'confidence' field is a calibrated margin and is often far lower.
        reg = answers.get("regime", {})
        conf = reg.get("answer_confidence", reg.get("confidence", 0.0))
        setup = answers.get("setup", {}).get("score", 0.0)
        tox = answers.get("toxicity", {}).get("noul", 0.0)
        if conf < self.p["min_confidence"]:
            return False, f"J2 low confidence {conf:.2f}"
        if setup < self.p["min_setup"]:
            return False, f"J3 weak setup {setup:.2f}"
        if tox > self.p["max_toxicity"]:
            return False, f"J4 toxicity {tox:.2f}"

        # analyst roles (TradingAgents-inspired), composed with coefficients here
        trend_view = (answers.get("trend_analyst") or {}).get("choice")
        if side and trend_view:
            if side == "BUY" and trend_view in ("strong_down", "weak_down"):
                return False, f"J5 trend analyst disagrees ({trend_view})"
            if side == "SELL" and trend_view in ("strong_up", "weak_up"):
                return False, f"J5 trend analyst disagrees ({trend_view})"
        risk_hi = (answers.get("risk_analyst") or {}).get("noul", 0.0)
        if risk_hi > self.p["max_risk_elevated"]:
            return False, f"J6 downside risk elevated {risk_hi:.2f}"
        return True, "ok"

    def _log(self, snapshot, answers, status):
        """Calibration triples: snapshot + answers now, outcome appended later."""
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "engine": self._engine, "status": status,
            "snapshot": snapshot, "answers": answers,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
