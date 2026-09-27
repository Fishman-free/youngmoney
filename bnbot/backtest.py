"""Event-driven backtest over the aligned 4h grid.

Accounting rules
----------------
- Decisions happen at bar open using only bars closed strictly before that
  moment (no lookahead); fills are at the bar-open price (approximated by
  weight-based accounting, slippage folded into the fee rate).
- Fee model: taker 5bp + slippage 2bp = 7bp of traded notional (config).
- Funding: at each 8h boundary, positions pay -notional * funding_rate
  (longs pay when the rate is positive), matching exchange mechanics.
- Weights are always passed through bnbot.risk.RiskManager before execution.

Walk-forward validation: parameters (donchian_window, mom_lookback_days) are
selected on the in-sample segment by Sharpe; the out-of-sample segment is
evaluated once with the chosen parameters and never influences selection.

CLI:
    python -m bnbot.backtest --walk-forward
    python -m bnbot.backtest                # full period, config params
"""

import argparse
import bisect
from dataclasses import dataclass, field

from .config import load_config
from .data import MS_PER_DAY, MS_PER_YEAR, AlignedBars, MarketData, fmt_dt, parse_dt_ms
from .quant import mean, stdev
from .risk import RiskManager
from .strategy import CompositeStrategy, Context

WF_SPLIT = 0.70  # fraction of time used for in-sample parameter selection
WF_DONCHIAN_GRID = (24, 48, 96)  # 4h bars
WF_MOM_GRID = (15, 30, 60)  # days


@dataclass
class BTResult:
    title: str
    params_tag: str
    start_ms: int
    end_ms: int
    curve: list = field(default_factory=list)  # [(ts, equity)]
    ntrades: int = 0
    fees: float = 0.0
    traded_notional: float = 0.0
    metrics: dict = field(default_factory=dict)


class Backtester:
    def __init__(self, config, market):
        self.config = config
        self.market = market
        self.symbols = list(config["symbols"])
        self.aligned = AlignedBars.build(market, self.symbols)
        self.risk = RiskManager(config["risk"])
        self.fee_rate = (
            float(config["fees"].get("taker_bps", 5.0)) + float(config["fees"].get("slippage_bps", 2.0))
        ) / 10_000.0
        self.band = float(config["strategy"].get("rebalance_band", 0.05))
        self.capital = float(config["capital"])

    def run(self, start_ms, end_ms, strategy, title=""):
        """Replay [start_ms, end_ms) on the grid. `strategy` must expose
        target_positions(ctx); tests may inject a stub strategy here."""
        grid = self.aligned.grid
        closes = self.aligned.closes
        i0 = bisect.bisect_left(grid, start_ms)
        fee_rate = self.fee_rate
        band = self.band
        funding_every = 8 * 3_600_000

        equity = self.capital
        peak = equity
        day_start = equity
        cur_day = None
        pos = {s: 0.0 for s in self.symbols}  # marked notional USD, signed
        last_funding_ts = {s: None for s in self.symbols}
        fees = 0.0
        traded = 0.0
        ntrades = 0
        gross_sum = 0.0
        steps = 0
        curve = []

        for i in range(i0, len(grid)):
            ts = grid[i]
            if ts >= end_ms:
                break

            # day rollover (UTC)
            day = ts // MS_PER_DAY
            if day != cur_day:
                cur_day = day
                day_start = equity

            # 1) funding settlement at 8h boundaries (each event charged once)
            if ts % funding_every == 0:
                for s in self.symbols:
                    if pos[s] == 0.0:
                        continue
                    ev = self.market.funding_event_at(s, ts)
                    if ev is None or ev[0] == last_funding_ts[s]:
                        continue
                    last_funding_ts[s] = ev[0]
                    equity -= pos[s] * ev[1]  # long pays positive rate

            # 2) mark-to-market on the bar-open price move
            for s in self.symbols:
                px = closes[s][i]
                if px is None or pos[s] == 0.0:
                    continue
                prev = self._prev_px(s, i)
                if prev:
                    ratio = px / prev
                    equity += pos[s] * (ratio - 1.0)
                    pos[s] *= ratio

            if equity <= 0:
                break  # account blown; stop replay

            # 3) decision at bar open (signals from bars closed before ts)
            ctx = Context(strategy.engine, ts)
            cur_w = {s: pos[s] / equity for s in self.symbols}
            target = self.risk.apply(
                strategy.target_positions(ctx),
                cur_w,
                equity=equity,
                peak_equity=peak,
                day_start_equity=day_start,
            )
            peak = max(peak, equity)

            # 4) rebalance with band; flatten (target 0) is never banded
            for s in self.symbols:
                tw = target.get(s, 0.0)
                cw = cur_w[s]
                if closes[s][i] is None:
                    continue  # symbol not trading on this grid slot
                if tw == 0.0 and cw == 0.0:
                    continue
                if tw != 0.0 and abs(tw - cw) <= band:
                    continue  # inside rebalance band
                delta = (tw - cw) * equity
                fee = abs(delta) * fee_rate
                equity -= fee
                fees += fee
                traded += abs(delta)
                ntrades += 1
                pos[s] = tw * equity

            gross_sum += sum(abs(v) for v in pos.values()) / equity
            steps += 1
            curve.append((ts, equity))

        m = compute_metrics(curve, self.capital, traded, fees, ntrades, gross_sum / steps if steps else 0.0)
        return BTResult(
            title=title or f"{fmt_dt(start_ms)} .. {fmt_dt(min(end_ms, grid[-1] + 1))}",
            params_tag=self._tag(strategy),
            start_ms=start_ms,
            end_ms=min(end_ms, grid[-1] + 1) if grid else end_ms,
            curve=curve,
            ntrades=ntrades,
            fees=fees,
            traded_notional=traded,
            metrics=m,
        )

    def _prev_px(self, s, i):
        return self.aligned.closes[s][i - 1] if i > 0 else None

    @staticmethod
    def _tag(strategy):
        p = getattr(strategy, "params", None)
        if p is None:
            return "custom"
        return f"donchian={p.donchian_window} mom={p.mom_lookback_days}d"


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def compute_metrics(curve, initial_equity, traded, fees, ntrades, avg_gross):
    m = {}
    if len(curve) < 2:
        return {
            "ann_return": 0.0, "ann_vol": 0.0, "sharpe": None, "sortino": None,
            "max_dd": 0.0, "calmar": None, "win_rate": None, "turnover_ann": 0.0,
            "avg_gross": avg_gross, "final_equity": curve[-1][1] if curve else initial_equity,
            "total_return": 0.0,
        }
    start_ms, end_ms = curve[0][0], curve[-1][0]
    eqs = [e for _, e in curve]
    rets = [eqs[i] / eqs[i - 1] - 1.0 for i in range(1, len(eqs))]
    years = max((end_ms - start_ms) / MS_PER_YEAR, 1e-9)

    step_ms = (curve[-1][0] - curve[0][0]) / (len(curve) - 1)
    ppy = MS_PER_YEAR / step_ms if step_ms > 0 else 2190.0

    final = eqs[-1]
    m["final_equity"] = final
    m["total_return"] = final / initial_equity - 1.0
    m["ann_return"] = (final / eqs[0]) ** (1.0 / years) - 1.0 if years > 0 else 0.0

    sd = stdev(rets)
    m["ann_vol"] = sd * ppy ** 0.5
    m["sharpe"] = (mean(rets) / sd) * ppy ** 0.5 if sd > 0 else None

    downside = (sum(min(r, 0.0) ** 2 for r in rets) / len(rets)) ** 0.5
    m["sortino"] = (mean(rets) / downside) * ppy ** 0.5 if downside > 0 else None

    peak = eqs[0]
    max_dd = 0.0
    for e in eqs:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)
    m["max_dd"] = -max_dd
    m["calmar"] = m["ann_return"] / max_dd if max_dd > 0 else None

    # daily win rate from last equity of each UTC day
    day_eq = {}
    for ts, e in curve:
        day_eq[ts // MS_PER_DAY] = e
    days = sorted(day_eq)
    if len(days) >= 2:
        drets = [day_eq[days[i]] / day_eq[days[i - 1]] - 1.0 for i in range(1, len(days))]
        m["win_rate"] = sum(1 for r in drets if r > 0) / len(drets)
    else:
        m["win_rate"] = None

    m["turnover_ann"] = traded / initial_equity / years
    m["avg_gross"] = avg_gross
    return m


def format_report(r):
    m = r.metrics
    lines = []
    lines.append(f"== {r.title}  [{r.params_tag}] ==")
    rows = [
        ("Period", f"{fmt_dt(r.start_ms)} -> {fmt_dt(r.end_ms)}"),
        ("Final equity", f"{m['final_equity']:,.2f}"),
        ("Total return", f"{m['total_return'] * 100:.2f}%"),
        ("Annual return", f"{m['ann_return'] * 100:.2f}%"),
        ("Annual vol", f"{m['ann_vol'] * 100:.2f}%"),
        ("Sharpe", f"{m['sharpe']:.2f}" if m["sharpe"] is not None else "n/a"),
        ("Sortino", f"{m['sortino']:.2f}" if m["sortino"] is not None else "n/a"),
        ("Max drawdown", f"{m['max_dd'] * 100:.2f}%"),
        ("Calmar", f"{m['calmar']:.2f}" if m["calmar"] is not None else "n/a"),
        ("Win rate (daily)", f"{m['win_rate'] * 100:.1f}%" if m["win_rate"] is not None else "n/a"),
        ("Turnover (annualized)", f"{m['turnover_ann']:.1f}x equity"),
        ("Avg gross exposure", f"{m['avg_gross']:.2f}"),
        ("Trades / fees", f"{r.ntrades} / {r.fees:,.2f}"),
    ]
    width = max(len(k) for k, _ in rows)
    for k, v in rows:
        lines.append(f"  {k.ljust(width)} : {v}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# walk-forward
# ---------------------------------------------------------------------------


def walk_forward(bt):
    """Parameter selection on IS, single evaluation on OOS.

    Returns (is_result, oos_result, selection_table_lines).
    """
    grid = bt.aligned.grid
    t0, t1 = grid[0], grid[-1]
    tsplit = grid[bisect.bisect_left(grid, t0 + int((t1 - t0) * WF_SPLIT))]

    lines = [f"Walk-forward split at {fmt_dt(tsplit)} (IS 70% / OOS 30%)", ""]
    lines.append(f"{'donchian':>8} {'mom_d':>6} | {'IS annR':>8} {'IS Sharpe':>9} {'IS maxDD':>9}")
    scored = []
    for d in WF_DONCHIAN_GRID:
        for m_ in WF_MOM_GRID:
            strat = CompositeStrategy(bt.config, bt.market, {"donchian_window": d, "mom_lookback_days": m_})
            r = bt.run(t0, tsplit, strat)
            scored.append((r, d, m_))
            sharpe = r.metrics["sharpe"]
            sharpe_str = f"{sharpe:>9.2f}" if sharpe is not None else f"{'n/a':>9}"
            lines.append(
                f"{d:>8} {m_:>6} | {r.metrics['ann_return'] * 100:>7.2f}% "
                f"{sharpe_str} {r.metrics['max_dd'] * 100:>8.2f}%"
            )
    # selection: highest IS Sharpe (fall back to ann_return if undefined)
    best = max(scored, key=lambda t: (
        t[0].metrics["sharpe"] if t[0].metrics["sharpe"] is not None else -1e9,
        t[0].metrics["ann_return"],
    ))
    r_is, bd, bm = best
    lines.append("")
    lines.append(f"selected on IS: donchian={bd} mom={bm}d")

    strat_best = CompositeStrategy(bt.config, bt.market, {"donchian_window": bd, "mom_lookback_days": bm})
    r_oos = bt.run(tsplit, t1 + 1, strat_best)
    r_is = bt.run(t0, tsplit, strat_best)  # rerun for identical tag/params
    return r_is, r_oos, lines


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bnbot.backtest", description="Backtest on cached data")
    ap.add_argument("--config", default=None)
    ap.add_argument("--walk-forward", action="store_true", help="IS parameter selection + OOS evaluation")
    ap.add_argument("--start", default=None, help="override start date (UTC)")
    ap.add_argument("--end", default=None, help="override end date (UTC, exclusive)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    market = MarketData.load(cfg["data"]["data_dir"], cfg["symbols"], cfg["data"].get("intervals", ["4h", "1d"]))
    bt = Backtester(cfg, market)
    grid = bt.aligned.grid
    if not grid:
        raise SystemExit("no data: run `python -m bnbot.data --fetch` first")
    start_ms = parse_dt_ms(args.start) if args.start else grid[0]
    end_ms = parse_dt_ms(args.end) if args.end else grid[-1] + 1

    if args.walk_forward:
        r_is, r_oos, table = walk_forward(bt)
        print("\n".join(table))
        print()
        print(format_report(r_is))
        print()
        print(format_report(r_oos))
    else:
        strat = CompositeStrategy(cfg, market)
        r = bt.run(start_ms, end_ms, strat)
        print(format_report(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
