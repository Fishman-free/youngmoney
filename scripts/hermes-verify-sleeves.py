# Ad-hoc verification (NOT suite): three-sleeve framework (2026-09-30). KEEP.
# Covers: capital split, per-sleeve isolation (state/kill switch/log dirs), leverage
# ceilings that config cannot loosen, aggregate reporting, and the 66-test suite.
import json
import os
import subprocess
import sys
import tempfile

fails = []
BIN = r"C:\Users\21560\Desktop\binance"
os.chdir(BIN)
sys.path.insert(0, BIN)

# 1. canonical suite (66 tests incl. tests/test_sleeves.py)
r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                   capture_output=True, text=True, cwd=BIN)
out = r.stderr + r.stdout
if r.returncode != 0 or "Ran 66 tests" not in out or "OK" not in out:
    fails.append(f"suite: {out[-300:]}")

# 2. real config expands into three isolated sleeves with capped leverage
from bnbot.config import load_config  # noqa: E402
from bnbot.risk import RiskManager  # noqa: E402
from bnbot.sleeves import SLEEVE_CEILINGS, aggregate, build_sleeves  # noqa: E402

cfg = load_config(os.path.join(BIN, "config.json"))
sl = build_sleeves(cfg, base_dir=BIN)
ids = [s["sleeve"]["id"] for s in sl]
if ids != ["A", "B", "C"]:
    fails.append(f"sleeve ids {ids}")
if abs(sum(s["capital"] for s in sl) - float(cfg["capital"])) > 0.01:
    fails.append("capital shares do not sum to total")
for key in ("state_file", "kill_switch_file", "log_dir"):
    vals = {json.dumps(s["live"][key]) if key != "kill_switch_file" else s["risk"][key] for s in sl}
    if len(vals) != 3:
        fails.append(f"{key} not isolated across sleeves")
for s in sl:
    sid = s["sleeve"]["id"]
    cap = SLEEVE_CEILINGS[sid]["max_gross_leverage"]
    if s["risk"]["max_gross_leverage"] > cap:
        fails.append(f"sleeve {sid} leverage {s['risk']['max_gross_leverage']} exceeds ceiling {cap}")

# 3. kill switch isolation against the REAL config paths
a, b = sl[0], sl[1]
os.makedirs(os.path.dirname(a["risk"]["kill_switch_file"]), exist_ok=True)
with open(a["risk"]["kill_switch_file"], "w"):
    pass
if not RiskManager(a["risk"]).kill_switch_active():
    fails.append("A kill switch not detected")
if RiskManager(b["risk"]).kill_switch_active():
    fails.append("A kill switch leaked into B")
os.unlink(a["risk"]["kill_switch_file"])

# 4. C is disabled until the paper gate is met
if sl[2]["sleeve"]["enabled"]:
    fails.append("sleeve C must stay disabled until its gate passes")

# 5. aggregate never invents shared capital
tot = aggregate(sl)
if abs(tot["capital"] - float(cfg["capital"])) > 0.01 or len(tot["sleeves"]) != 3:
    fails.append(f"aggregate wrong: {tot}")

# 6. live sleeve state dirs exist for enabled sleeves after the earlier run
for sid in ("A", "B"):
    p = os.path.join(BIN, "state", "sleeves", sid, "portfolio.json")
    if not os.path.exists(p):
        fails.append(f"missing sleeve state: {p}")

print("FAIL:\n  " + "\n  ".join(fails) if fails else "ALL CHECKS PASSED")
sys.exit(1 if fails else 0)
