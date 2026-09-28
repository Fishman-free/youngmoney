"""Strategy signal correctness on synthetic series (offline)."""

import unittest

from bnbot.data import MS_PER_DAY, MS_PER_HOUR
from bnbot.quant import ema
from bnbot.strategy import CompositeStrategy, Context
from synth import T0, make_config, make_market

SYM = "TESTUSDT"


class TestEma(unittest.TestCase):
    def test_constant_series_seeded_and_flat(self):
        out = ema([5.0] * 10, 3)
        self.assertIsNone(out[0])
        self.assertIsNone(out[1])
        self.assertEqual(out[2:], [5.0] * 8)


class TestTrendSignal(unittest.TestCase):
    def _strategy(self, closes4h):
        md = make_market(SYM, closes4h=closes4h, closes1d=[100.0] * (len(closes4h) // 4 + 5))
        return CompositeStrategy(make_config("unused"), md)

    def test_breakout_up_gives_long(self):
        closes = [100.0] * 80 + [100.0 + 2.0 * (i + 1) for i in range(60)]
        strat = self._strategy(closes)
        eng = strat.engine
        # flat warmup: no signal yet
        self.assertEqual(eng.trend_at(SYM, T0 + 60 * 4 * MS_PER_HOUR), 0)
        # after sustained breakout: long
        self.assertEqual(eng.trend_at(SYM, T0 + 139 * 4 * MS_PER_HOUR + 4 * MS_PER_HOUR), 1)

    def test_breakdown_gives_short(self):
        closes = [100.0] * 80 + [100.0 - 2.0 * (i + 1) for i in range(60)]
        strat = self._strategy(closes)
        self.assertEqual(
            strat.engine.trend_at(SYM, T0 + 139 * 4 * MS_PER_HOUR + 4 * MS_PER_HOUR), -1
        )

    def test_ema_filter_blocks_counter_trend_breakout(self):
        # 100-bar decline -> 60-bar flat -> single breakout spike -> sustained rally
        decline = [220.0 - i for i in range(100)]
        flat = [121.0] * 60
        spike = [123.0]  # breaks the flat-phase donchian upper (122)
        rally = [123.0 + 2.0 * (i + 1) for i in range(40)]
        closes = decline + flat + spike + rally  # 161 bars
        strat = self._strategy(closes)
        eng = strat.engine
        step = 4 * MS_PER_HOUR
        ts_spike = T0 + 160 * step  # open time of the spike bar (index 160)
        # spike bar breaks the channel but EMA20 still below EMA50 -> flat
        self.assertLess(eng.trend_at(SYM, ts_spike + step), 1)
        self.assertEqual(eng.trend_at(SYM, ts_spike + step), 0)
        # sustained rally eventually flips EMA filter -> long
        self.assertEqual(eng.trend_at(SYM, T0 + 160 * step + 40 * step), 1)


class TestMomentum(unittest.TestCase):
    def _engine(self, closes1d):
        md = make_market(SYM, closes4h=[100.0] * (len(closes1d) * 6), closes1d=closes1d)
        return CompositeStrategy(make_config("unused"), md).engine

    def test_uptrend_long(self):
        eng = self._engine([100.0 + i for i in range(70)])
        self.assertEqual(eng.momentum_at(SYM, T0 + 70 * MS_PER_DAY), 1)

    def test_downtrend_short(self):
        eng = self._engine([200.0 - i for i in range(70)])
        self.assertEqual(eng.momentum_at(SYM, T0 + 70 * MS_PER_DAY), -1)


class TestCarryTilt(unittest.TestCase):
    def _weight(self, funding):
        md = make_market(
            SYM,
            closes4h=[100.0] * 200,
            closes1d=[100.0] * 60,
            funding=funding,
        )
        strat = CompositeStrategy(make_config("unused"), md)
        ctx = Context(strat.engine, T0 + 150 * 4 * MS_PER_HOUR)
        return strat.target_positions(ctx)[SYM]

    def test_positive_funding_shorts_the_perp(self):
        # 0.0003 per 8h -> 32.85% annualized, far above the 5% threshold
        self.assertAlmostEqual(self._weight([(100 * 4 * MS_PER_HOUR, 0.0003)]), -0.10)

    def test_negative_funding_longs_the_perp(self):
        self.assertAlmostEqual(self._weight([(100 * 4 * MS_PER_HOUR, -0.0003)]), 0.10)

    def test_no_funding_no_tilt(self):
        self.assertAlmostEqual(self._weight([]), 0.0)

    def test_funding_trailing_mean_smooths_spike(self):
        md = make_market(
            SYM, closes4h=[100.0] * 200, closes1d=[100.0] * 60,
            funding=[(40 * 4 * MS_PER_HOUR, 0.0),
                     (41 * 4 * MS_PER_HOUR, 0.0),
                     (42 * 4 * MS_PER_HOUR, 0.03)],
        )
        ts = T0 + 150 * 4 * MS_PER_HOUR
        strat = CompositeStrategy(make_config("unused"), md)
        self.assertAlmostEqual(strat.engine.ann_funding_at(SYM, ts), 0.01 * 3 * 365.0)
        strat1 = CompositeStrategy(
            make_config("unused"), md, overrides={"funding_smooth_events": 1}
        )
        self.assertAlmostEqual(strat1.engine.ann_funding_at(SYM, ts), 0.03 * 3 * 365.0)


class TestCrossSectional(unittest.TestCase):
    def _market(self):
        from bnbot.data import BarSeries, MS_PER_DAY
        from synth import T0, kline_rows, make_market
        md = make_market("AAAUSDT", closes4h=[100.0] * 200, closes1d=[100.0] * 60)
        # AAA: steady winner (up ~50%), BBB: mild winner, CCC: mild loser, DDD: deep loser
        paths = {
            "AAAUSDT": [100.0 * (1.01 ** i) for i in range(120)],
            "BBBUSDT": [100.0 * (1.003 ** i) for i in range(120)],
            "CCCUSDT": [100.0 * (0.998 ** i) for i in range(120)],
            "DDDUSDT": [100.0 * (0.985 ** i) for i in range(120)],
        }
        times1 = [T0 + i * MS_PER_DAY for i in range(120)]
        times4 = [T0 + i * 4 * MS_PER_HOUR for i in range(200)]
        for sym, closes in paths.items():
            rows = kline_rows(times1, closes, step_ms=MS_PER_DAY)
            md.klines[(sym, "1d")] = BarSeries(sym, "1d", rows)
            flat = kline_rows(times4, [closes[-1]] * 200)
            md.klines[(sym, "4h")] = BarSeries(sym, "4h", flat)
            md.funding[sym] = {"times": [], "rates": []}
        return md

    def test_xs_sleeve_long_winners_short_losers(self):
        md = self._market()
        cfg = make_config("unused", symbols=("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"))
        strat = CompositeStrategy(cfg, md, overrides={
            "weight_trend": 0.0, "weight_mom": 0.0, "carry_weight": 0.0,
            "xs_weight": 0.6, "xs_top_n": 2,
        })
        w = strat.target_positions(Context(strat.engine, T0 + 110 * 24 * MS_PER_HOUR))
        self.assertGreater(w["AAAUSDT"], 0.0)  # strongest -> long
        self.assertGreater(w["BBBUSDT"], 0.0)
        self.assertLess(w["CCCUSDT"], 0.0)
        self.assertLess(w["DDDUSDT"], 0.0)  # weakest -> short
        self.assertAlmostEqual(sum(w.values()), 0.0, places=6)  # market neutral
        self.assertAlmostEqual(sum(abs(v) for v in w.values()), 0.6, places=6)  # gross = xs_weight

    def test_xs_sleeve_disabled_by_default(self):
        md = self._market()
        cfg = make_config("unused", symbols=("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"))
        strat = CompositeStrategy(cfg, md, overrides={
            "weight_trend": 0.0, "weight_mom": 0.0, "carry_weight": 0.0,
        })
        w = strat.target_positions(Context(strat.engine, T0 + 110 * 24 * MS_PER_HOUR))
        for v in w.values():
            self.assertAlmostEqual(v, 0.0, places=6)


class TestInterface(unittest.TestCase):
    def test_target_positions_covers_all_symbols(self):
        from bnbot.data import BarSeries
        from synth import kline_rows

        cfg = make_config("unused", symbols=("AAAUSDT", "BBBUSDT"))
        md = make_market("AAAUSDT", closes4h=[100.0] * 200, closes1d=[100.0] * 60)
        times4 = [T0 + i * 4 * MS_PER_HOUR for i in range(200)]
        times1 = [T0 + i * MS_PER_DAY for i in range(60)]
        md.klines[("BBBUSDT", "4h")] = BarSeries("BBBUSDT", "4h", kline_rows(times4, [50.0] * 200))
        md.klines[("BBBUSDT", "1d")] = BarSeries(
            "BBBUSDT", "1d", kline_rows(times1, [50.0] * 60, step_ms=MS_PER_DAY)
        )
        md.funding["BBBUSDT"] = {"times": [], "rates": []}
        strat = CompositeStrategy(cfg, md)
        w = strat.target_positions(Context(strat.engine, T0 + 150 * 4 * MS_PER_HOUR))
        self.assertEqual(set(w), {"AAAUSDT", "BBBUSDT"})
        for v in w.values():
            self.assertIsInstance(v, float)


if __name__ == "__main__":
    unittest.main()
