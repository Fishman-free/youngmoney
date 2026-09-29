"""Strategy layer.

Interface (see CompositeStrategy.target_positions):
    target_positions(ctx) -> {symbol: weight}
where weight is a fraction of account equity, signed (positive = long,
negative = short). Weights are later bounded by bnbot.risk before orders.

Three additive sub-signals, weights tunable in config:
1. Trend (4h): Donchian channel breakout state machine + EMA(fast/slow) filter.
   A close above the previous N-bar high arms long (below N-bar low arms
   short); the position persists until the opposite breakout. The EMA filter
   flattens counter-trend arms (long only allowed when EMA_fast > EMA_slow).
2. Time-series momentum (1d): sign of the trailing N-day return.
3. Funding carry (8h events): annualized funding above a threshold tilts the
   weight against the paying side (positive funding -> shorts earn -> negative
   weight offset). Expressed as a pure weight offset, no dual-leg accounting.

Trend and momentum are scaled by realized volatility (target_vol / realized
annualized vol, capped). Carry keeps its own fixed magnitude (carry_weight).
"""

import bisect
from dataclasses import dataclass, fields

from .data import FUNDING_GRACE_MS, INTERVAL_MS, MS_PER_DAY
from .quant import clamp, ema, sign, stdev


@dataclass
class StrategyParams:
    weight_trend: float
    weight_mom: float
    donchian_window: int
    ema_fast: int
    ema_slow: int
    mom_lookback_days: int
    mom_deadband: float
    funding_ann_threshold: float
    carry_weight: float
    target_vol: float
    vol_lookback_days: int
    max_vol_scale: float
    funding_smooth_events: int = 3
    xs_weight: float = 0.0
    xs_top_n: int = 2
    xs_mom_lookback_days: int = 30
    xs_mom_share: float = 0.6
    xs_high52_share: float = 0.4
    vol_confirm_min: float = 0.0
    xs_carry_weight: float = 0.0

    @classmethod
    def from_config(cls, config, overrides=None):
        merged = dict(config["strategy"])
        merged["target_vol"] = config.get("target_vol", 0.20)
        merged.setdefault("funding_smooth_events", 3)
        if overrides:
            merged.update(overrides)
        names = {f.name for f in fields(cls)}
        return cls(**{k: merged[k] for k in names if k in merged})


class SignalEngine:
    """Precomputes per-symbol signal series on their native timeframes and
    answers as-of queries (only bars fully closed at the query time are used).

    Lookup rule for a query ts: the last bar whose open_time + interval <= ts
    is the newest visible bar.
    """

    def __init__(self, market, symbols, params):
        self.market = market
        self.symbols = list(symbols)
        self.params = params
        self._trend = {}  # symbol -> (open_times, step_ms, signals)
        self._mom = {}  # symbol -> (day_times, signals)
        self._mom_raw = {}  # symbol -> (day_times, trailing returns)
        self._h52 = {}  # symbol -> (day_times, close/365d-high ratios)
        self._vol = {}  # symbol -> (day_times, ann_vols)
        self._precompute()

    # -- precomputation ----------------------------------------------------

    def _precompute(self):
        p = self.params
        for sym in self.symbols:
            self._precompute_trend(sym)
            self._precompute_mom_vol(sym)

    def _precompute_trend(self, sym):
        p = self.params
        bs = self.market.klines[(sym, "4h")]
        n = len(bs)
        ef = ema(bs.close, p.ema_fast)
        es = ema(bs.close, p.ema_slow)
        win = p.donchian_window
        sig = [0] * n
        raw = 0
        for j in range(n):
            if j >= win and ef[j] is not None and es[j] is not None:
                hi = max(bs.high[j - win : j])  # previous `win` bars, current excluded
                lo = min(bs.low[j - win : j])
                if bs.close[j] > hi:
                    if self._volume_confirm(bs, j):
                        raw = 1
                elif bs.close[j] < lo:
                    if self._volume_confirm(bs, j):
                        raw = -1
                s = raw
                if raw == 1 and ef[j] <= es[j]:
                    s = 0
                elif raw == -1 and ef[j] >= es[j]:
                    s = 0
                sig[j] = s
        self._trend[sym] = (bs.open_time, INTERVAL_MS["4h"], sig)

    def _volume_confirm(self, bs, j):
        """Breakout-on-volume: only accept a NEW trend direction when the
        breakout bar's own volume is >= vol_confirm_min z-scores above its
        trailing 20-bar mean. vol_confirm_min<=0 disables (legacy semantics).
        The breakout bar is closed at signal time, so its volume is as-of safe.
        """
        p = self.params
        if p.vol_confirm_min <= 0:
            return True
        window = bs.volume[max(0, j - 20) : j]
        if len(window) < 10:
            return True
        m = sum(window) / len(window)
        if m <= 0:
            return True
        sd = stdev(window) if len(window) >= 2 else 0.0
        if sd <= 0:
            return True  # flat volume series -> no disconfirmation
        z = (bs.volume[j] - m) / sd
        return z >= p.vol_confirm_min

    def _precompute_mom_vol(self, sym):
        p = self.params
        ds = self.market.klines[(sym, "1d")]
        closes = ds.close
        highs = ds.high
        n = len(closes)
        mom = [0] * n
        raw = [None] * n
        h52 = [None] * n
        vol = [0.0] * n
        rets = [0.0] * n
        for d in range(1, n):
            rets[d] = closes[d] / closes[d - 1] - 1.0
        for d in range(n):
            if d >= p.mom_lookback_days:
                ret = closes[d] / closes[d - p.mom_lookback_days] - 1.0
                mom[d] = sign(ret) if abs(ret) > p.mom_deadband else 0
            if d >= p.xs_mom_lookback_days:
                raw[d] = closes[d] / closes[d - p.xs_mom_lookback_days] - 1.0
            win_high = max(highs[max(0, d - 364) : d + 1]) if highs else 0.0
            if win_high > 0:
                h52[d] = closes[d] / win_high
            if d >= p.vol_lookback_days:
                window = rets[d - p.vol_lookback_days + 1 : d + 1]
                sd = stdev(window)  # len(window) >= 2 required
                vol[d] = sd * (365.0 ** 0.5) if len(window) >= 2 else 0.0  # annualized
        self._mom[sym] = (ds.open_time, mom)
        self._mom_raw[sym] = (ds.open_time, raw)
        self._h52[sym] = (ds.open_time, h52)
        self._vol[sym] = (ds.open_time, vol)

    # -- as-of queries -------------------------------------------------------

    def trend_at(self, sym, ts):
        times, step, sig = self._trend[sym]
        i = bisect.bisect_right(times, ts - step) - 1  # bar fully closed at ts
        return sig[i] if i >= 0 else 0

    def momentum_at(self, sym, ts):
        times, sig = self._mom[sym]
        i = bisect.bisect_right(times, ts - MS_PER_DAY) - 1  # day fully closed
        return sig[i] if i >= 0 else 0

    def realized_vol_at(self, sym, ts):
        times, vol = self._vol[sym]
        i = bisect.bisect_right(times, ts - MS_PER_DAY) - 1
        return vol[i] if i >= 0 else 0.0

    def mom_raw_at(self, sym, ts):
        times, raw = self._mom_raw[sym]
        i = bisect.bisect_right(times, ts - MS_PER_DAY) - 1
        return raw[i] if i >= 0 and raw[i] is not None else None

    def high52_ratio_at(self, sym, ts):
        times, ratios = self._h52[sym]
        i = bisect.bisect_right(times, ts - MS_PER_DAY) - 1
        return ratios[i] if i >= 0 and ratios[i] is not None else None

    def funding_event_at(self, sym, ts):
        return self.market.funding_event_at(sym, ts)

    def ann_funding_at(self, sym, ts):
        f = self.market.funding.get(sym)
        if not f or not f["times"]:
            return 0.0
        i = bisect.bisect_right(f["times"], ts + FUNDING_GRACE_MS) - 1
        if i < 0:
            return 0.0
        n = max(1, int(self.params.funding_smooth_events))
        rates = f["rates"][max(0, i - n + 1) : i + 1]
        return (sum(rates) / len(rates)) * 3.0 * 365.0  # 8h rate -> annualized


class Context:
    """Decision-time market view handed to strategies (as-of ts)."""

    def __init__(self, engine, ts):
        self.engine = engine
        self.ts = ts

    def trend(self, symbol):
        return self.engine.trend_at(symbol, self.ts)

    def momentum(self, symbol):
        return self.engine.momentum_at(symbol, self.ts)

    def ann_funding(self, symbol):
        return self.engine.ann_funding_at(symbol, self.ts)

    def realized_vol(self, symbol):
        return self.engine.realized_vol_at(symbol, self.ts)

    def mom_raw(self, symbol):
        return self.engine.mom_raw_at(symbol, self.ts)

    def high52_ratio(self, symbol):
        return self.engine.high52_ratio_at(symbol, self.ts)


class CompositeStrategy:
    """Combines trend + momentum + carry into target weights."""

    def __init__(self, config, market, overrides=None):
        self.symbols = list(config["symbols"])
        self.params = StrategyParams.from_config(config, overrides)
        self.engine = SignalEngine(market, self.symbols, self.params)

    def target_positions(self, ctx):
        p = self.params
        out = {}
        xs = self._xs_sleeve(ctx)
        xsc = self._xs_carry_sleeve(ctx)
        for sym in self.symbols:
            trend = ctx.trend(sym)
            mom = ctx.momentum(sym)
            ann = ctx.ann_funding(sym)

            core = p.weight_trend * trend + p.weight_mom * mom

            vol = ctx.realized_vol(sym)
            scale = min(p.max_vol_scale, p.target_vol / vol) if vol > 1e-9 else 1.0

            # positive funding pays longs -> shorts earn the carry -> short tilt
            carry = 0.0
            if p.funding_ann_threshold > 0 and p.carry_weight > 0:
                carry = -clamp(ann / p.funding_ann_threshold, -1.0, 1.0) * p.carry_weight

            w = core * scale + carry + xs.get(sym, 0.0) + xsc.get(sym, 0.0)
            out[sym] = w if abs(w) > 1e-6 else 0.0
        return out

    def _xs_carry_sleeve(self, ctx):
        """Cross-sectional carry. Ranks the universe on trailing annualized
        funding, goes LONG the cheapest funding (collects/keeps funding) and
        SHORT the richest funding (pays funding to shorts), market-neutral.
        Evidence: funding/basis carry is the institutional-grade strategy
        (Bitwise carry fund); this is the AQR-style cross-sectional version,
        complementary to the per-symbol absolute-threshold tilt above.
        """
        p = self.params
        out = {s: 0.0 for s in self.symbols}
        if p.xs_carry_weight <= 0:
            return out
        fund = {}
        for s in self.symbols:
            fund[s] = ctx.ann_funding(s)
        n_sym = len(fund)
        if n_sym < 2 * p.xs_top_n:
            return out
        order = sorted(fund, key=lambda k: (fund[k], k))
        n = min(p.xs_top_n, n_sym // 2)
        leg = p.xs_carry_weight / (2.0 * n)
        for s in order[:n]:  # lowest funding -> long (earn/keep funding)
            out[s] += leg
        for s in order[-n:]:  # highest funding -> short (shorts collect funding)
            out[s] -= leg
        return out

    def _xs_sleeve(self, ctx):
        """Cross-sectional sleeve. Ranks the universe on two unit-free scores
        (30d trailing return and close/365d-high proximity), goes long the top
        N and short the bottom N, market-neutral by construction. Evidence:
        crypto cross-section is momentum-dominated (AQR-style factor migration);
        the 52-week-high effect is the stronger documented momentum variant;
        short-term reversal in crypto is documented as weak -> not included.
        """
        p = self.params
        out = {s: 0.0 for s in self.symbols}
        if p.xs_weight <= 0:
            return out
        mom, h52 = {}, {}
        for s in self.symbols:
            m = ctx.mom_raw(s)
            h = ctx.high52_ratio(s)
            if m is not None:
                mom[s] = m
            if h is not None:
                h52[s] = h
        if len(mom) < 2 * p.xs_top_n and len(h52) < 2 * p.xs_top_n:
            return out

        def ranks(d):
            n = len(d)
            if n <= 1:
                return {k: 0.5 for k in d}
            order = sorted(d, key=d.get)
            return {k: i / (n - 1) for i, k in enumerate(order)}

        rm, rh = ranks(mom), ranks(h52)
        scores = {}
        for s in self.symbols:
            if s not in rm and s not in rh:
                continue
            scores[s] = p.xs_mom_share * rm.get(s, 0.5) + p.xs_high52_share * rh.get(s, 0.5)
        ranked = sorted(scores, key=lambda k: (scores[k], k))
        n = min(p.xs_top_n, len(ranked) // 2)
        if n == 0:
            return out
        leg = p.xs_weight / (2.0 * n)
        for s in ranked[-n:]:
            out[s] += leg
        for s in ranked[:n]:
            out[s] -= leg
        return out
