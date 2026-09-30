"""Per-cycle counters and cost accounting (jev-trader's `totals` block).

Persisted to state/metrics.json so the status server, STATE.md and report.py
all read one source. Counters only ever increase; `reset_cycle()` clears the
per-cycle fields.
"""

import json
import os
from datetime import datetime, timezone

FIELDS = ("cycles", "decisions", "orders", "rejected_verifier", "rejected_judgment",
          "fills", "late", "fees", "realized_pnl")


class Metrics:
    def __init__(self, path=None, data=None):
        self.path = path
        d = data or {}
        for f in FIELDS:
            setattr(self, f, d.get(f, 0.0 if f == "fees" else 0))
        self.last_cycle = d.get("last_cycle", {})

    def cycle(self, *, orders=0, rejected_verifier=0, rejected_judgment=0,
              fills=0, late=False, fees=0.0, equity=None, realized_pnl=0.0):
        self.cycles += 1
        self.decisions += 1
        self.orders += orders
        self.rejected_verifier += rejected_verifier
        self.rejected_judgment += rejected_judgment
        self.fills += fills
        self.late += 1 if late else 0
        self.fees += fees
        self.realized_pnl += realized_pnl
        self.last_cycle = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "orders": orders, "rejected_verifier": rejected_verifier,
            "rejected_judgment": rejected_judgment, "fills": fills,
            "late": bool(late), "fees": round(fees, 6),
            "equity": equity if equity is not None else self.last_cycle.get("equity"),
        }
        return self

    def to_dict(self):
        d = {f: getattr(self, f) for f in FIELDS}
        d["fees"] = round(d["fees"], 6)
        d["realized_pnl"] = round(d["realized_pnl"], 6)
        d["last_cycle"] = self.last_cycle
        return d

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        os.replace(tmp, self.path)

    @classmethod
    def load(cls, path):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return cls(path=path, data=json.load(f))
        return cls(path=path)
