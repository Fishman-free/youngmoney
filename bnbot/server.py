"""Read-only status server (stdlib only) — dashboard + JSON API.

    python -m bnbot.server --port 8787

Endpoints:
    GET /             JSON snapshot (equity, positions, counters, recent orders)
    GET /dashboard    HTML dashboard, auto-refresh 10s
    GET /history?n=20 last N audit blocks from state/STATE.md
    GET /health       {"ok": true}

Sleeve mode: when <state-dir>/sleeves/ holds per-sleeve accounts (the A/B/C
framework), the snapshot automatically aggregates them -- one row per sleeve with
equity read from that sleeve's own STATE.md, plus a reporting-only total. The
aggregate is never a trading pool. `--legacy` forces the old single-account view.

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
<h2 id="sleeveh" style="display:none">分仓（A 长线 / B 短线 / C 实验）</h2>
<table id="sleevetbl" style="display:none"></table>
<h2 id="sparkh">权益曲线（来自审计日志）</h2>
<div id="spark"></div>
<h2>计数器</h2><table id="counters"></table>
<h2>持仓</h2><table id="pos"></table>
<h2>最近成交</h2><table id="orders"></table>
<p class="muted" id="foot"></p>
</main>
<script>
function card(k,v,cls){return `<div class="card"><div class="k">${k}</div><div class="v ${cls||''}">${v}</div></div>`}
const PAL=['#58a6ff','#3fb950','#d29922','#f85149','#a371f7'];
function sgn(x,d){return (x>=0?'+':'')+x.toFixed(d==null?2:d)}
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
function sparkMulti(rows){
  const used=rows.filter(r=>r.series&&r.series.length>1&&r.capital);
  if(!used.length) return '<span class="muted">数据不足</span>';
  const w=880,h=170,padL=44,padR=12,padT=14,padB=18;
  const norm=r=>r.series.map(v=>v/r.capital*100);
  const all=[].concat(...used.map(norm)).concat([100]);
  const lo=Math.min(...all),hi=Math.max(...all),rng=(hi-lo)||1;
  const yOf=x=>h-padB-(x-lo)*(h-padT-padB)/rng;
  const xOf=(i,n)=>padL+i*(w-padL-padR)/Math.max(1,n-1);
  let s=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;max-width:900px;height:180px;display:block">`;
  s+=`<line x1="${padL}" y1="${yOf(100).toFixed(1)}" x2="${w-padR}" y2="${yOf(100).toFixed(1)}" stroke="#30363d" stroke-dasharray="4 4"/>`;
  s+=`<text x="${w-padR}" y="12" fill="#6e7681" font-size="12" text-anchor="end">指数 100 = 本金</text>`;
  s+=`<text x="4" y="${(yOf(hi)+4).toFixed(1)}" fill="#6e7681" font-size="12">${hi.toFixed(1)}</text>`;
  s+=`<text x="4" y="${yOf(lo).toFixed(1)}" fill="#6e7681" font-size="12">${lo.toFixed(1)}</text>`;
  used.forEach((r,k)=>{const xs=norm(r),c=PAL[k%PAL.length];
    s+=`<polyline fill="none" stroke="${c}" stroke-width="2" points="${xs.map((x,i)=>xOf(i,xs.length).toFixed(1)+','+yOf(x).toFixed(1)).join(' ')}"/>`;
    const lx=xOf(xs.length-1,xs.length),ly=yOf(xs[xs.length-1]);
    s+=`<circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.5" fill="${c}"/>`;});
  s+='</svg>';
  s+='<div class="muted" style="margin:6px 0 0">'+used.map((r,k)=>
      `<span style="color:${PAL[k%PAL.length]};margin-right:16px">&#9632; ${r.id} ${r.name||''} ${r.pnl_pct==null?'':sgn(r.pnl_pct)+'%'}</span>`).join('')+'</div>';
  return s;
}
function sleeveTable(rows){
  let h='<tr><th>仓</th><th>名称</th><th>资本</th><th>权益</th><th>盈亏</th><th>收益率</th>'
       +'<th>持仓</th><th>轮次</th><th>成交</th><th>拒绝</th><th>费用</th><th>状态</th></tr>';
  rows.forEach(r=>{const m=r.metrics||{};
    const rej=(m.rejected_verifier||0)+(m.rejected_judgment||0);
    const cls=r.pnl_pct==null?'':(r.pnl_pct>=0?'g':'r');
    h+=`<tr><td><b>${r.id}</b></td><td>${r.name||''}</td>`
      +`<td>${r.capital==null?'-':r.capital.toFixed(2)}</td>`
      +`<td>${r.equity==null?'-':r.equity.toFixed(2)}</td>`
      +`<td class="${cls}">${r.pnl==null?'-':sgn(r.pnl)}</td>`
      +`<td class="${cls}">${r.pnl_pct==null?'-':sgn(r.pnl_pct)+'%'}</td>`
      +`<td>${r.positions??0}</td><td>${m.cycles??0}</td><td>${m.fills??0}</td><td>${rej}</td>`
      +`<td>${(m.fees??0).toFixed(2)}</td>`
      +`<td class="${r.halted?'r':'g'}">${r.halted?'已熔断':'正常'}</td></tr>`;});
  return h;
}
async function tick(){
  try{
    const j=await (await fetch('/')).json(), m=j.metrics||{}, c=m.last_cycle||{};
    const sleeve=j.mode==='sleeves';
    if(sleeve){
      const cap=j.capital, eq=j.equity;
      const pnl=(cap&&eq!=null)?eq-cap:null, pct=(cap&&eq!=null)?(eq/cap-1)*100:null;
      const cls=pct==null?'':(pct>=0?'g':'r');
      document.getElementById('cards').innerHTML=
        card('总权益', eq==null?'-':eq.toFixed(2))+
        card('总资本', cap==null?'-':cap.toFixed(2))+
        card('总盈亏', pnl==null?'-':sgn(pnl), cls)+
        card('收益率', pct==null?'-':sgn(pct)+'%', cls)+
        card('持仓数', j.positions??0)+
        card('风控', j.kill_switch?'触发':'正常', j.kill_switch?'r':'g');
      document.getElementById('sleeveh').style.display='';
      const st=document.getElementById('sleevetbl'); st.style.display='';
      st.innerHTML=sleeveTable(j.sleeves||[]);
      document.getElementById('spark').innerHTML=sparkMulti(j.sleeves||[]);
      document.getElementById('sparkh').textContent='各仓收益指数（本金=100）';
    } else {
      const eq=j.equity!=null?j.equity:null;
      document.getElementById('cards').innerHTML=
        card('权益(现金)', eq==null?'-':eq.toFixed(2))+
        card('持仓数', j.positions??0)+
        card('总轮次', m.cycles??0)+
        card('成交', m.fills??0)+
        card('拒绝', (m.rejected_verifier??0)+(m.rejected_judgment??0))+
        card('累计费用', (m.fees??0).toFixed(2))+
        card('风控', j.kill_switch?'触发':'正常', j.kill_switch?'r':'g');
      document.getElementById('sleeveh').style.display='none';
      document.getElementById('sleevetbl').style.display='none';
      document.getElementById('spark').innerHTML=spark(j.equity_series||[]);
      document.getElementById('sparkh').textContent='权益曲线（来自审计日志）';
    }
    document.getElementById('counters').innerHTML=
      '<tr><th>指标</th><th>值</th></tr>'+Object.entries(m).filter(([k,v])=>typeof v!=='object')
      .map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('');
    const ps=j.position_list||[];
    document.getElementById('pos').innerHTML= ps.length?
      '<tr><th>标的</th><th>仓</th><th>数量</th><th>开仓价</th></tr>'+ps.map(p=>
        `<tr><td>${p.symbol}</td><td>${p.sleeve||'-'}</td><td>${p.qty}</td><td>${p.entry_price||'-'}</td></tr>`).join('')
      : '<tr><td class="muted">无持仓</td></tr>';
    const os=j.recent_orders||[];
    document.getElementById('orders').innerHTML= os.length?
      '<tr><th>时间</th><th>动作</th></tr>'+os.map(o=>`<tr><td class="muted">${o.ts||''}</td><td>${o.text}</td></tr>`).join('')
      : '<tr><td class="muted">暂无</td></tr>';
    const lc=sleeve ? (j.sleeves||[]).map(r=>`${r.id}@${r.last_ts||'-'}`).join(' · ') : (c.ts||'-');
    document.getElementById('foot').textContent =
      `最近一轮 ${lc} · 数据源 ${sleeve?'state/sleeves/{A,B,C}':'state'}/{portfolio,metrics}.json + STATE.md · 只读`;
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


def discover_sleeves(state_dir):
    """[{id, state_dir}] for every sleeve account under <state_dir>/sleeves/."""
    root = os.path.join(state_dir, "sleeves")
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        if os.path.exists(os.path.join(d, "portfolio.json")) or os.path.exists(os.path.join(d, "STATE.md")):
            out.append({"id": name, "state_dir": d})
    return out


def _sleeve_meta(state_dir):
    """{id: {name, share}} + total capital from config.json next to state_dir (best effort)."""
    base = os.path.dirname(os.path.abspath(state_dir))
    p = os.path.join(base, "config.json")
    meta, total = {}, None
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                cfg = json.load(f)
            total = float(cfg.get("capital", 0.0)) or None
            sec = cfg.get("sleeves") or {}
            spec = sec.get("list", []) if isinstance(sec, dict) else sec
            for s in spec:
                meta[str(s.get("id"))] = {"name": s.get("name", str(s.get("id"))),
                                          "share": float(s.get("share", 0.0))}
        except (ValueError, OSError, TypeError):
            pass
    return meta, total


def aggregate_snapshot(state_dir):
    """Sleeve-aware snapshot: one row per sleeve + a reporting-only aggregate.

    Equity per sleeve comes from that sleeve's STATE.md audit blocks (the value
    live.py marked at real prices), never from a recomputation here -- this
    server is offline and has no marks of its own.
    """
    meta, total_cap = _sleeve_meta(state_dir)
    rows = []
    for s in discover_sleeves(state_dir):
        sid = s["id"]
        sub = snapshot(s["state_dir"])
        m = meta.get(sid, {})
        cap = total_cap * m["share"] if (total_cap and "share" in m) else None
        row = {
            "id": sid,
            "name": m.get("name", sid),
            "capital": round(cap, 2) if cap else None,
            "cash": sub.get("cash", 0.0),
            "equity": sub.get("equity"),
            "positions": sub.get("positions", 0),
            "position_list": sub.get("position_list", []),
            "series": sub.get("equity_series", []),
            "metrics": sub.get("metrics", {}),
            "last_ts": ((sub.get("metrics") or {}).get("last_cycle") or {}).get("ts"),
            "halted": bool(sub.get("kill_switch")),
            "orders": sub.get("recent_orders", []),
        }
        if cap and row["equity"] is not None:
            row["pnl"] = round(row["equity"] - cap, 2)
            row["pnl_pct"] = round((row["equity"] / cap - 1.0) * 100, 2)
        rows.append(row)

    tot_equity = sum(r["equity"] for r in rows if r["equity"] is not None)
    tot_cash = sum(r["cash"] for r in rows if r["cash"] is not None)
    tot_metrics = {}
    for key in ("cycles", "decisions", "orders", "rejected_verifier", "rejected_judgment",
                "fills", "late", "fees"):
        vals = [r["metrics"].get(key) for r in rows if isinstance(r["metrics"], dict)
                and isinstance(r["metrics"].get(key), (int, float))]
        if vals:
            tot_metrics[key] = round(sum(vals), 6) if key == "fees" else sum(vals)
    recent = []
    for r in rows:
        for o in r["orders"]:
            recent.append({"ts": o.get("ts", ""), "text": f"[{r['id']}] {o.get('text', '')}"})
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "sleeves",
        "sleeves": rows,
        "equity": round(tot_equity, 2),
        "cash": round(tot_cash, 2),
        "capital": total_cap,
        "positions": sum(r["positions"] for r in rows),
        "position_list": [dict(p, sleeve=r["id"]) for r in rows for p in r["position_list"]],
        "kill_switch": any(r["halted"] for r in rows),
        "halted": [r["id"] for r in rows if r["halted"]],
        "metrics": tot_metrics,
        "recent_orders": recent[-10:][::-1],
    }


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
    # A kill switch that exists but is never reported is worse than none: the
    # dashboard said "风控 正常" no matter what. Sleeves put theirs at
    # <state_dir>/KILL_SWITCH; the legacy single account keeps it at the repo
    # root next to state/ (config risk.kill_switch_file defaults to "KILL_SWITCH").
    out["kill_switch"] = _kill_switch_present(state_dir)
    return out


def _kill_switch_present(state_dir):
    candidates = [os.path.join(state_dir, "KILL_SWITCH")]
    parent = os.path.dirname(os.path.normpath(state_dir))
    if parent:
        candidates.append(os.path.join(parent, "KILL_SWITCH"))
    return any(os.path.exists(p) for p in candidates)


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
    legacy = False

    def snapshot(self):
        """Sleeve aggregate when per-sleeve accounts exist, else the legacy view."""
        if not self.legacy and discover_sleeves(self.state_dir):
            return aggregate_snapshot(self.state_dir)
        return snapshot(self.state_dir)

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
            self._send(200, self.snapshot())
        elif u.path == "/dashboard":
            self._send(200, DASH_HTML, "text/html")
        elif u.path == "/history":
            q = parse_qs(u.query)
            n = int((q.get("n") or ["20"])[0])
            sd = self.state_dir
            sid = (q.get("sleeve") or [""])[0]
            if sid and re.fullmatch(r"[A-Za-z0-9_-]{1,16}", sid):
                sd = os.path.join(self.state_dir, "sleeves", sid)
            self._send(200, {"blocks": history(sd, n)})
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
    ap.add_argument("--legacy", action="store_true",
                    help="force the single-account view even when sleeves exist")
    args = ap.parse_args(argv)
    Handler.state_dir = args.state_dir
    Handler.legacy = args.legacy
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    n = len(discover_sleeves(args.state_dir))
    mode = "sleeves" if (n and not args.legacy) else "legacy"
    print(f"bnbot status: http://{args.host}:{args.port}/dashboard  (mode={mode}"
          + (f", sleeves={n}" if mode == "sleeves" else "") + ")")
    srv.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
