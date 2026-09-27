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

from .data import INTERVAL_MS, MS_PER_DAY
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

    @classmethod
    def from_config(cls, config, overrides=None):
        merged = dict(config["strategy"])
        merged["target_vol"] = config.get("target_vol", 0.20)
        if overrides:
            merged.update(overrides)
        names = {f.name for f in fields(cls)}
        return cls(**{k: merged[k] for k in names})


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
                    raw = 1
                elif bs.close[j] < lo:
                    raw = -1
                s = raw
                if raw == 1 and ef[j] <= es[j]:
                    s = 0
                elif raw == -1 and ef[j] >= es[j]:
                    s = 0
                sig[j] = s
        self._trend[sym] = (bs.open_time, INTERVAL_MS["4h"], sig)

    def _precompute_mom_vol(self, sym):
        p = self.params
        ds = self.market.klines[(sym, "1d")]
        closes = ds.close
        n = len(closes)
        mom = [0] * n
        vol = [0.0] * n
        rets = [0.0] * n
        for d in range(1, n):
            rets[d] = closes[d] / closes[d - 1] - 1.0
        for d in range(n):
            if d >= p.mom_lookback_days:
                ret = closes[d] / closes[d - p.mom_lookback_days] - 1.0
                mom[d] = sign(ret) if abs(ret) > p.mom_deadband else 0
            if d >= p.vol_lookback_days:
                window = rets[d - p.vol_lookback_days + 1 : d + 1]
                sd = stdev(window)  # len(window) >= 2 required
                vol[d] = sd * (365.0 ** 0.5) if len(window) >= 2 else 0.0  # annualized
        self._mom[sym] = (ds.open_time, mom)
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

    def funding_event_at(self, sym, ts):
        return self.market.funding_event_at(sym, ts)

    def ann_funding_at(self, sym, ts):
        ev = self.funding_event_at(sym, ts)
        if ev is None:
            return 0.0
        return ev[1] * 3.0 * 365.0  # 8h rate -> annualized


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


class CompositeStrategy:
    """Combines trend + momentum + carry into target weights."""

    def __init__(self, config, market, overrides=None):
        self.symbols = list(config["symbols"])
        self.params = StrategyParams.from_config(config, overrides)
        self.engine = SignalEngine(market, self.symbols, self.params)

    def target_positions(self, ctx):
        p = self.params
        out = {}
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

            w = core * scale + carry
            out[sym] = w if abs(w) > 1e-6 else 0.0
        return out
