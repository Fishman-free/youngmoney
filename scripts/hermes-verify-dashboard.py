"""Diagnose the served dashboard: is the JS clean, and does the running server match the file?"""
import io
import re
import subprocess
import sys
import urllib.request

OUT = r"C:\Users\21560\AppData\Local\Temp\bnbot_diag"
url = "http://127.0.0.1:8787/dashboard"
html = urllib.request.urlopen(url, timeout=10).read().decode("utf-8")
m = re.search(r"<script>([\s\S]*)</script>", html)
js = m.group(1) if m else ""

print("served html bytes:", len(html))
print("served js bytes:", len(js))
print("literal backslash-n in served js:", js.count("\\n"))
print("literal backslash-quote in served js:", js.count('\\"'))
print("real newlines in served js:", js.count("\n"))

# compare against the source file's own JS section
src = io.open(r"C:\Users\21560\Desktop\binance\bnbot\server.py", encoding="utf-8").read()
ms = re.search(r"<script>([\s\S]*)</script>", src)
srcjs = ms.group(1) if ms else ""
print("source js bytes:", len(srcjs), " identical to served:", srcjs == js)

io.open(OUT + ".js", "w", encoding="utf-8", newline="").write(js)
r = subprocess.run(["node", "--check", OUT + ".js"], capture_output=True, text=True, shell=True)
print("node --check rc:", r.returncode)
print((r.stdout + r.stderr)[:300])
sys.exit(0)
