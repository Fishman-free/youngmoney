# Ad-hoc verification (NOT suite): Tokyo deployment artifacts (2026-09-30). KEEP.
# Covers: bootstrap script structural contract (no secrets, right services, balanced
# heredocs), latency checker behaviour, deployment doc sections, canonical suite.
import os
import re
import subprocess
import sys

fails = []
BIN = r"C:\Users\21560\Desktop\binance"
BOOT = os.path.join(BIN, "scripts", "vps-bootstrap.sh")
LAT = os.path.join(BIN, "scripts", "vps-latency-check.py")
DOC = os.path.join(BIN, "docs", "DEPLOY_TOKYO.md")

# 1. canonical suite
r = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True, cwd=BIN)
if r.returncode != 0:
    fails.append(f"pytest: {(r.stdout + r.stderr)[-260:]}")

# 2. bootstrap script: structure + must not carry credentials
if not os.path.exists(BOOT):
    fails.append("bootstrap script missing")
else:
    s = open(BOOT, encoding="utf-8").read()
    if not s.startswith("#!/usr/bin/env bash"):
        fails.append("bootstrap: missing bash shebang")
    if "set -euo pipefail" not in s:
        fails.append("bootstrap: missing strict mode")
    openers = re.findall(r"<<-?\s*['\"]?(\w+)['\"]?", s)
    terminators = [l.strip() for l in s.splitlines() if l.strip() in set(openers)]
    if len(openers) != len(terminators) or not openers:
        fails.append(f"bootstrap: heredoc markers unbalanced ({len(openers)} opens, "
                     f"{len(terminators)} closes)")
    for need in ("bnbot.live --sleeves", "bnbot.server --port 8787",
                 "systemctl enable --now", ".env", "chmod 600"):
        if need not in s:
            fails.append(f"bootstrap: missing {need!r}")
    # no literal key material
    if re.search(r"BN_API_(KEY|SECRET)\s*=\s*[A-Za-z0-9+/=]{12,}", s):
        fails.append("bootstrap: contains what looks like a real credential")

# 3. latency checker: runs and emits a verdict even when exchanges are unreachable
if not os.path.exists(LAT):
    fails.append("latency checker missing")
else:
    r2 = subprocess.run([sys.executable, LAT], capture_output=True, text=True, timeout=300, cwd=BIN)
    out = r2.stdout + r2.stderr
    if "VERDICT:" not in out:
        fails.append(f"latency checker produced no verdict: {out[-200:]}")
    if "location" not in out:
        fails.append("latency checker did not report location")

# 4. deployment doc covers the essentials
if not os.path.exists(DOC):
    fails.append("deploy doc missing")
else:
    d = open(DOC, encoding="utf-8").read()
    for need in ("ap-northeast-1", "systemd", "白名单", "Vultr", "ufw", "不得凭空造出 edge".replace("不得凭空造出 edge", "必要条件")):
        if need not in d:
            fails.append(f"deploy doc missing {need!r}")

print("FAIL:\n  " + "\n  ".join(fails) if fails else "ALL CHECKS PASSED")
sys.exit(1 if fails else 0)
