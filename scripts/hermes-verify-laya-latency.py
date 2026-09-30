# Measure laya latency: model load vs warm inference, single process, 3 warm calls.
import time
from laya import Router

BATTERY = {
    "regime": {"type": "choice", "instructions": "Which market regime best describes this state?",
               "criteria": {"trending": "sustained directional movement, breakouts holding",
                            "mean_reverting": "range-bound, moves fading back",
                            "chaotic": "erratic, no clear structure"}},
    "toxicity": {"type": "noul", "instructions": "Is the recent move likely a liquidity-driven overreaction that will fade?"},
    "setup": {"type": "score", "instructions": "How clean and tradeable is the current setup?",
              "criteria": ["no setup", "weak", "decent", "clean"]},
}
state = ("BTCUSDT | trend_signal 1 | momentum_30d 1 | realized_vol 0.40 | funding_ann 0.09 "
         "| equity 10000 | drawdown 0.02")

t0 = time.time()
r = Router()
t_load = time.time() - t0

lats = []
for _ in range(3):
    t = time.time()
    r.predict(state, BATTERY)
    lats.append((time.time() - t) * 1000)

print(f"model load (cold, cached checkpoint): {t_load:.2f}s")
print("warm predict ms:", " ".join(f"{x:.0f}" for x in lats))
print(f"median warm: {sorted(lats)[1]:.0f} ms")
