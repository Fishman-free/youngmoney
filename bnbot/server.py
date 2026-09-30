"""Read-only status server (stdlib only) — dashboard + JSON API.

    python -m bnbot.server --port 8787

Endpoints:
    GET /             JSON snapshot (equity, positions, counters, recent orders)
    GET /dashboard    HTML dashboard, auto-refresh 10s
    GET /history?n=20 last N audit blocks from state/STATE.md
    GET /health       {"ok": true}

Never writes anything, never exposes credentials.
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DASH_HTML = """<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>bnbot 量化平台状态</title>
<style>
 body{font-family:ui-monospace,Consolas,"Courier New",monospace;background:#0d1117;color:#c9d1d9;
      margin:0;padding:20px;line-height:1.6}
 h1{font-size:17px;margin:0 0 14px;font-weight:600;letter-spacing:.5px}
 h2{font-size:13px;margin:22px 0 8px;color:#8b949e;font-weight:600;text-transform:uppercase}
 .cards{display:flex;flex-wrap:wrap;gap:10px}
 .card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 16px;min-width:120px}
 .card .k{font-size:11px;color:#8b949e}
 .card .v{font-size:20px;font-weight:600}
 .g{color:#3fb950}.r{color:#f85149}.y{color:#d29922}
 table{border-collapse:collapse;width:100%;font-size:13px}
 td,th{padding:4px 10px;border-bottom:1px solid #21262d;text-align:left}
 th{color:#8b949e;font-weight:500}
 .muted{color:#6e7681;font-size:12px}
 main{max-width:900px}
 svg{background:#161b22;border:1px solid #30363d;border-radius:8px}
</style>
<main>
<h1>bnbot 量化平台状态 <span class="muted" id="ts"></span></h1>
<div class="cards" id="cards">加载中…</div>
<h2>权益曲线（来自审计日志）</h2>
<div id="spark"></div>
<h2>计数器</h2><table id="counters"></table>
<h2>持仓</h2><table id="pos"></table>
<h2>最近成交</h2><table id="orders"></table>
<p class="muted" id="foot"></p>
</main>
<script>
function card(k,v,cls){return `<div class="card"><div class="k">${k}</div><div class="v ${cls||''}">${v}</div></div>`}
function spark(xs){
  if(xs.length<2) return '<span class="muted">数据不足</span>';
  const w=880,h=140,p=18,lo=Math.min(...xs),hi=Math.max(...xs),rng=(hi-lo)||1;
  const pt=(i,x)=>[p+i*(w-2*p)/(xs.length-1), h-p-(x-lo)*(h-2*p)/rng];
  const d=xs.map((x,i)=>pt(i,x).join(',')).join(' ');
  const [lx,ly]=pt(xs.length-1,xs[xs.length-1]);
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"
    style="width:100%;max-width:900px;height:150px;display:block">
    <polyline fill="none" stroke="#58a6ff" stroke-width="2" points="${d}"/>
    <circle cx="${lx}" cy="${ly}" r="3.5" fill="#58a6ff"/>
    <text x="${w-p}" y="16" fill="#6e7681" font-size="12" text-anchor="end">${hi.toFixed(2)}</text>
    <text x="${p}" y="${h-6}" fill="#6e7681" font-size="12">${lo.toFixed(2)}</text></svg>`;
}
async function tick(){
  try{
    const j=await (await fetch('/')).json(), m=j.metrics||{}, c=m.last_cycle||{};
    const eq=j.equity!=null?j.equity:null;
    document.getElementById('cards').innerHTML=
      card('权益(现金)', eq==null?'-':eq.toFixed(2))+
      card('持仓数', j.positions??0)+
      card('总轮次', m.cycles??0)+
      card('成交', m.fills??0)+
      card('拒绝', (m.rejected_verifier??0)+(m.rejected_judgment??0))+
      card('累计费用', (m.fees??0).toFixed(2))+
      card('风控', j.kill_switch?'触发':'正常', j.kill_switch?'r':'g');
    document.getElementById('spark').innerHTML=spark(j.equity_series||[]);
    document.getElementById('counters').innerHTML=
      '<tr><th>指标</th><th>值</th></tr>'+Object.entries(m).filter(([k,v])=>typeof v!=='object')
      .map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('');
    const ps=j.position_list||[];
    document.getElementById('pos').innerHTML= ps.length?
      '<tr><th>标的</th><th>数量</th><th>开仓价</th></tr>'+ps.map(p=>
        `<tr><td>${p.symbol}</td><td>${p.qty}</td><td>${p.entry_price||'-'}</td></tr>`).join('')
      : '<tr><td class="muted">无持仓</td></tr>';
    const os=j.recent_orders||[];
    document.getElementById('orders').innerHTML= os.length?
      '<tr><th>时间</th><th>动作</th></tr>'+os.map(o=>`<tr><td class="muted">${o.ts||''}</td><td>${o.text}</td></tr>`).join('')
      : '<tr><td class="muted">暂无</td></tr>';
    document.getElementById('foot').textContent =
      `最近一轮 ${c.ts||'-'} · 单轮 orders=${c.orders??'-'} rejected=${(c.rejected_verifier||0)+(c.rejected_judgment||0)} · 数据源 state/{portfolio,metrics}.json + STATE.md`;
    document.getElementById('ts').textContent = new Date().toLocaleTimeString();
  }catch(e){ document.getElementById('foot').textContent='读取失败: '+e; }
}
tick(); setInterval(tick, 10000);
</script></html>"""


def _equity_series(state_dir, cap=200):
    """Parse equity=... from STATE.md audit blocks for the sparkline."""
    p = os.path.join(state_dir, "STATE.md")
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^## \S+\s+equity=([\d,\.]+)", line.strip())
            if m:
                try:
                    out.append(float(m.group(1).replace(",", "")))
                except ValueError:
                    pass
    return out[-cap:]


def _recent_orders(state_dir, cap=8):
    p = os.path.join(state_dir, "STATE.md")
    if not os.path.exists(p):
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s.startswith("EXEC ") or s.startswith("REJ "):
                rows.append({"ts": "", "text": s})
    return rows[-cap:][::-1]


def snapshot(state_dir):
    out = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    p = os.path.join(state_dir, "portfolio.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            st = json.load(f)
        out["cash"] = round(float(st.get("cash", 0)), 2)
        pos = st.get("positions", {})
        out["positions"] = len(pos)
        out["position_list"] = [{"symbol": s, "qty": round(float(v.get("qty", 0)), 6),
                                 "entry_price": round(float(v.get("entry_price", 0)), 6)}
                                for s, v in sorted(pos.items())]
        out["peak_equity"] = round(float(st.get("peak_equity", 0)), 2)
        out["equity"] = out["cash"]
    m = os.path.join(state_dir, "metrics.json")
    if os.path.exists(m):
        with open(m, encoding="utf-8") as f:
            out["metrics"] = json.load(f)
    out["equity_series"] = _equity_series(state_dir)
    if out["equity_series"]:
        out["equity"] = out["equity_series"][-1]
    out["recent_orders"] = _recent_orders(state_dir)
    out["kill_switch"] = False
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
        if isinstance(body, bytes):
            data = body
        elif isinstance(body, str):          # HTML/plain text: serve verbatim
            data = body.encode("utf-8")
        else:                                # dict/list -> JSON
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
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

    def log_message(self, *a):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bnbot.server", description="read-only status server")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--state-dir", default="state")
    args = ap.parse_args(argv)
    Handler.state_dir = args.state_dir
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"bnbot status: http://{args.host}:{args.port}/dashboard")
    srv.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
