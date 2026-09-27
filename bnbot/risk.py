"""Risk layer: hard constraints applied to target weights before any order.

Order of enforcement (most lethal first):
1. KILL_SWITCH file exists      -> flatten everything, reject all new risk
2. total drawdown >= halt (25%) -> flatten, stand aside
3. total drawdown >= throttle (15%) -> halve every weight
4. intraday loss >= daily_loss_stop (3%) -> no risk increases this UTC day
   (reductions allowed, sign flips clamp to flat, flat stays flat)
5. per-symbol |weight| <= max_symbol_weight (0.35)
6. gross sum(|weight|) <= max_gross_leverage (2.0) via proportional scale
"""

import os

from .quant import clamp, sign


class RiskManager:
    def __init__(self, risk_cfg):
        self.max_gross_leverage = float(risk_cfg.get("max_gross_leverage", 2.0))
        self.max_symbol_weight = float(risk_cfg.get("max_symbol_weight", 0.35))
        self.daily_loss_stop = float(risk_cfg.get("daily_loss_stop", 0.03))
        self.drawdown_throttle = float(risk_cfg.get("drawdown_throttle", 0.15))
        self.drawdown_halt = float(risk_cfg.get("drawdown_halt", 0.25))
        self.kill_switch_file = risk_cfg.get("kill_switch_file", "KILL_SWITCH")

    def kill_switch_active(self):
        return os.path.exists(self.kill_switch_file)

    def apply(self, target, current, equity, peak_equity, day_start_equity):
        """Adjust target weights {symbol: weight} under all hard constraints.

        current: current weights {symbol: weight} (same key set expected;
                 missing keys treated as flat).
        """
        w = {k: float(v) for k, v in target.items()}
        cur = {k: float(v) for k, v in current.items()}

        # 1. kill switch: all flat, nothing new
        if self.kill_switch_active():
            return {k: 0.0 for k in w}

        peak = max(peak_equity, equity) if peak_equity > 0 else equity
        dd = 1.0 - equity / peak if peak > 0 else 0.0

        # 2. deep drawdown: flatten and wait
        if dd >= self.drawdown_halt:
            return {k: 0.0 for k in w}

        # 3. drawdown throttle: halve exposure
        if dd >= self.drawdown_throttle:
            w = {k: v * 0.5 for k, v in w.items()}

        # 4. intraday loss circuit breaker: no new / no increased risk today
        if day_start_equity > 0 and equity <= day_start_equity * (1.0 - self.daily_loss_stop):
            for k in w:
                cw = cur.get(k, 0.0)
                tw = w[k]
                if cw == 0.0:
                    w[k] = 0.0  # no new entries
                elif sign(tw) != sign(cw):
                    w[k] = 0.0  # flip would open new-direction risk; go flat instead
                elif abs(tw) > abs(cw):
                    w[k] = cw  # hold, never increase

        # 5. per-symbol cap
        for k in w:
            w[k] = clamp(w[k], -self.max_symbol_weight, self.max_symbol_weight)

        # 6. gross leverage cap
        gross = sum(abs(v) for v in w.values())
        if gross > self.max_gross_leverage > 0:
            f = self.max_gross_leverage / gross
            w = {k: v * f for k, v in w.items()}

        return w
