"""Backtest accounting invariants (offline, synthetic data)."""

import tempfile
import unittest

from bnbot.backtest import Backtester
from bnbot.data import MS_PER_HOUR
from synth import T0, make_config, make_market

SYM = "TESTUSDT"
FEE_RATE = (5.0 + 2.0) / 10_000.0  # taker + slippage


class FixedStrategy:
    """Test seam: returns constant weights, ignores market context."""

    def __init__(self, weights):
        self.weights = dict(weights)
        self.engine = None

    def target_positions(self, ctx):
        return dict(self.weights)


class TestBacktestInvariants(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cfg = make_config(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, market, weights, bars=30):
        bt = Backtester(self.cfg, market)
        return bt.run(T0, T0 + bars * 4 * MS_PER_HOUR, FixedStrategy(weights))

    def test_no_trade_equity_stays_at_initial(self):
        md = make_market(SYM, closes4h=[100.0] * 60, closes1d=[100.0] * 15)
        r = self._run(md, {SYM: 0.0})
        self.assertEqual(r.ntrades, 0)
        self.assertEqual(r.fees, 0.0)
        for ts, eq in r.curve:
            self.assertAlmostEqual(eq, 10000.0, places=6)
        self.assertAlmostEqual(r.metrics["final_equity"], 10000.0, places=6)
        self.assertEqual(r.metrics["ann_vol"], 0.0)

    def test_fee_is_deducted_exactly_once_per_trade(self):
        md = make_market(SYM, closes4h=[100.0] * 60, closes1d=[100.0] * 15)
        r = self._run(md, {SYM: 0.3})
        expected_fee = 10000.0 * 0.3 * FEE_RATE  # single entry, flat prices
        self.assertEqual(r.ntrades, 1)
        self.assertAlmostEqual(r.fees, expected_fee, places=6)
        self.assertAlmostEqual(r.curve[-1][1], 10000.0 - expected_fee, places=6)
        self.assertAlmostEqual(r.traded_notional, 3000.0, places=6)

    def test_funding_long_pays_positive_rate(self):
        md = make_market(
            SYM, closes4h=[100.0] * 60, closes1d=[100.0] * 15,
            funding=[(8 * MS_PER_HOUR, 0.01)],
        )
        r = self._run(md, {SYM: 0.3})
        eq_after_fee = 10000.0 * (1.0 - 0.3 * FEE_RATE)
        expected = eq_after_fee - 0.3 * eq_after_fee * 0.01  # long pays 1%
        self.assertAlmostEqual(r.curve[-1][1], expected, places=6)

    def test_funding_short_receives_positive_rate(self):
        md = make_market(
            SYM, closes4h=[100.0] * 60, closes1d=[100.0] * 15,
            funding=[(8 * MS_PER_HOUR, 0.01)],
        )
        r = self._run(md, {SYM: -0.3})
        eq_after_fee = 10000.0 * (1.0 - 0.3 * FEE_RATE)
        expected = eq_after_fee + 0.3 * eq_after_fee * 0.01  # short receives 1%
        self.assertAlmostEqual(r.curve[-1][1], expected, places=6)

    def test_funding_charged_once_per_event(self):
        md = make_market(
            SYM, closes4h=[100.0] * 60, closes1d=[100.0] * 15,
            funding=[(8 * MS_PER_HOUR, 0.01), (16 * MS_PER_HOUR, -0.005)],
        )
        r = self._run(md, {SYM: 0.3})
        eq1 = 10000.0 * (1.0 - 0.3 * FEE_RATE)
        pos = 0.3 * eq1
        expected = eq1 - pos * 0.01 + pos * 0.005  # +1% paid, then -0.5% received
        self.assertAlmostEqual(r.curve[-1][1], expected, places=6)


if __name__ == "__main__":
    unittest.main()
