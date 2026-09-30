"""Read-only status server (jev-trader's snapshot/history endpoints, stdlib only).

    python -m bnbot.server --port 8787

Endpoints:
    GET /             JSON snapshot: equity, positions, counters, last cycle
    GET /dashboard    minimal HTML view of the same (auto-refresh)
    GET /history?n=20 last N audit blocks from state/STATE.md
    GET /health       {"ok": true}

Never writes anything and never exposes credentials.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DASH_HTML = """<!doctype html><meta charset="utf-8"><title>bnbot status</title>
<style>body{font-family:ui-monospace,Consolas,monospace;background:#111;color:#ddd;padding:24px}
h1{font-size:18px}table{border-collapse:collapse}td,th{padding:4px 12px;border-bottom:1px solid #333;text-align:left}
.g{color:#6c6}.r{color:#e66}</style>
<h1>bnbot status <span id="ts"></span></h1><div id="root">loading…</div>
<script>
async function tick(){
  const r = await fetch('/'); const j = await r.json();
  const m = j.metrics||{}, c = m.last_cycle||{};
  let rows = Object.entries(m).filter(([k,v])=>typeof v!=='object')
      .map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('');
  document.getElementById('root').innerHTML =
    `<p>equity <b>${j.equity??'-'}</b> · cash ${j.cash??'-'} · positions ${j.positions??0}
      · kill_switch <span class="${j.kill_switch?'r':'g'}">${j.kill_switch}</span></p>
     <p>last cycle: ${c.ts||'-'} orders=${c.orders??'-'} rejected=${(c.rejected_verifier||0)+(c.rejected_judgment||0)}</p>
     <table><tr><th>counter</th><th>value</th></tr>${rows}</table>`;
  document.getElementById('ts').textContent = new Date().toLocaleTimeString();
}
tick(); setInterval(tick, 10000);
</script>"""


def snapshot(state_dir):
    out = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    p = os.path.join(state_dir, "portfolio.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            st = json.load(f)
        out["cash"] = round(float(st.get("cash", 0)), 2)
        out["positions"] = len(st.get("positions", {}))
        out["peak_equity"] = round(float(st.get("peak_equity", 0)), 2)
        out["equity"] = out["cash"]  # exact mark-to-market lives in STATE.md blocks
    m = os.path.join(state_dir, "metrics.json")
    if os.path.exists(m):
        with open(m, encoding="utf-8") as f:
            out["metrics"] = json.load(f)
    out["kill_switch"] = bool(out.get("metrics", {}).get("kill_switch", False))
    return out


def history(state_dir, n=20):
    p = os.path.join(state_dir, "STATE.md")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        lines = f.read().splitlines()
    heads = [i for i, l in enumerate(lines) if l.startswith("## ")]
    blocks = []
    for idx, i in enumerate(heads):
        end = heads[idx + 1] if idx + 1 < len(heads) else len(lines)
        blocks.append("\n".join(lines[i:end]).rstrip())
    return blocks[-n:]


class Handler(BaseHTTPRequestHandler):
    state_dir = "state"

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._send(200, snapshot(self.state_dir))
        elif u.path == "/dashboard":
            self._send(200, DASH_HTML, "text/html")
        elif u.path == "/history":
            n = int((parse_qs(u.query).get("n") or ["20"])[0])
            self._send(200, {"blocks": history(self.state_dir, n)})
        elif u.path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *a):  # quiet
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bnbot.server", description="read-only status server")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--state-dir", default="state")
    args = ap.parse_args(argv)
    Handler.state_dir = args.state_dir
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"bnbot status: http://127.0.0.1:{args.port}/  (dashboard: /dashboard)")
    srv.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
