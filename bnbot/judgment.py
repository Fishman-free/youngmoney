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

Every call logs (snapshot, questions, answers) plus later outcome to
state/judgment-log.jsonl as calibration triples (Brier/ECE once enough
outcomes accumulate). Timestamp discipline: the snapshot is built ONLY from
information strictly before the decision time.
"""

import json
import os
import time
from datetime import datetime, timezone

# policy thresholds live in code (edit a coefficient, not a prompt)
POLICY = {
    "min_confidence": 0.50,     # abstain (veto new exposure) below answer_confidence
    "min_setup": 1.5,           # score 0-3 rubric
    "max_toxicity": 0.70,       # noul: P(overreaction) too high -> veto
    "battery_timeout_s": 10.0,  # deadline rule: on timeout, hold (veto)
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
}


def build_state_snapshot(sym, ctx, equity=None, drawdown=None):
    """Compact numeric state text from info strictly before ctx.ts."""
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

    def _get_router(self):
        if self._router is None:
            from laya import Router  # optional dependency (fallback if missing)
            self._router = Router()
            self._engine = "laya"
        return self._router

    def ask(self, snapshot):
        """Run the atomic battery on one snapshot. Returns answers dict or None
        on any failure (fallback ladder: degrade to pass-through)."""
        try:
            router = self._get_router()
            t0 = time.time()  # deadline applies to the decision, not model load
            result = router.predict(snapshot, BATTERY)
            if time.time() - t0 > self.p["battery_timeout_s"]:
                self._log(snapshot, None, "timeout")
                return None
            answers = result.get("answers", {})
            self._log(snapshot, answers, "ok")
            return answers
        except Exception as e:
            self._log(snapshot, None, f"error:{type(e).__name__}")
            return None

    def gate(self, answers):
        """Policy gate in code: (allow_new_exposure, reason).
        None answers follow policy on_missing: 'hold' (deadline rule) or
        'pass' (auxiliary layer degrades to pass-through)."""
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
