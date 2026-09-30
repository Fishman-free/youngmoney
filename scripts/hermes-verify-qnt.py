# Ad-hoc verification (NOT suite): QNT ultra-short analyser (2026-09-30). KEEP.
# Contract: the analyser runs clean on live data and prints the three rule rows plus
# the leverage-survival table; the canonical suite stays green.
import os
import re
import subprocess
import sys

fails = []
BIN = r"C:\Users\21560\Desktop\binance"
SUBJ = os.path.join(BIN, "scripts", "qnt-ultra-short.py")

r = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True, cwd=BIN)
if r.returncode != 0:
    fails.append(f"pytest: {(r.stdout + r.stderr)[-260:]}")

if not os.path.exists(SUBJ):
    fails.append("analyser missing")
else:
    r2 = subprocess.run([sys.executable, SUBJ], capture_output=True, text=True, timeout=300, cwd=BIN)
    out = r2.stdout + r2.stderr
    if r2.returncode != 0:
        fails.append(f"analyser crashed: {out[-240:]}")
    for tag in ("QNT 小时数据", "小时波动率", "R1 ", "R2 ", "R3 ", "杠杆生存线"):
        if tag not in out:
            fails.append(f"analyser output missing {tag!r}")
    if len(re.findall(r"^  +?\d+x -> 强平距离", out, re.M)) < 5:
        fails.append("leverage table incomplete")
    for line in open(os.path.join(BIN, ".env"), encoding="utf-8"):
        if line.startswith(("BN_API_KEY=", "BN_API_SECRET=", "XAI_API_KEY=")):
            sec = line.split("=", 1)[1].strip()
            if sec and sec in out:
                fails.append("secret leaked into analyser output")

print("FAIL:\n  " + "\n  ".join(fails) if fails else "ALL CHECKS PASSED")
sys.exit(1 if fails else 0)
