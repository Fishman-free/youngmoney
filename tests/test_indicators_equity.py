import json
import os
import tempfile
import unittest

from bnbot import indicators as ind
from bnbot.data import MarketData
from bnbot.usstock import save_bars


class TestIndicators(unittest.TestCase):
    def test_sma_and_ema_warmup(self):
        vals = [float(i) for i in range(1, 11)]
        s = ind.sma(vals, 3)
        self.assertIsNone(s[0])
        self.assertIsNone(s[1])
        self.assertAlmostEqual(s[2], 2.0)
        self.assertAlmostEqual(s[-1], 9.0)
        e = ind.ema(vals, 3)
        self.assertIsNone(e[1])
        self.assertAlmostEqual(e[2], 2.0)
        self.assertGreater(e[-1], 0)

    def test_rsi_bounds_and_monotonic(self):
        up = [float(i) for i in range(1, 40)]
        r = ind.rsi(up, 14)
        self.assertIsNone(r[13])
        self.assertAlmostEqual(r[-1], 100.0)          # all gains -> 100
        down = [float(i) for i in range(40, 1, -1)]
        rd = ind.rsi(down, 14)
        self.assertAlmostEqual(rd[-1], 0.0)           # all losses -> 0

    def test_macd_alignment(self):
        vals = [100 + (i % 7) * 0.5 for i in range(80)]
        m = ind.macd(vals)
        self.assertEqual(len(m["dif"]), 80)
        self.assertEqual(len(m["dea"]), 80)
        self.assertEqual(len(m["hist"]), 80)
        self.assertIsNone(m["dif"][0])
        self.assertIsNotNone(m["hist"][-1])

    def test_bollinger_ordering(self):
        vals = [10.0 + (i % 5) for i in range(40)]
        b = ind.bollinger(vals, 20, 2.0)
        i = 30
        self.assertLess(b["lower"][i], b["mid"][i])
        self.assertLess(b["mid"][i], b["upper"][i])

    def test_kdj_and_atr(self):
        highs = [10.0 + i * 0.5 for i in range(30)]
        lows = [9.0 + i * 0.5 for i in range(30)]
        closes = [9.5 + i * 0.5 for i in range(30)]
        k = ind.kdj(highs, lows, closes)
        self.assertIsNone(k["k"][0])
        self.assertIsNotNone(k["k"][-1])
        a = ind.atr(highs, lows, closes, 14)
        self.assertIsNone(a[5])
        self.assertGreater(a[-1], 0)


class TestEquityBridge(unittest.TestCase):
    def _write_equity(self, d, sym, interval, rows):
        save_bars(d, sym, interval, rows)

    def test_marketdata_loads_equity_without_funding(self):
        with tempfile.TemporaryDirectory() as d:
            rows4 = [{"open_time": 1000 * i, "open": 1.0, "high": 1.2, "low": 0.9,
                      "close": 1.1, "volume": 5.0, "close_time": 1000 * i + 999}
                     for i in range(1, 30)]
            self._write_equity(d, "SOXL", "4h", rows4)
            self._write_equity(d, "SOXL", "1d", rows4)
            md = MarketData.load(d, ["SOXL"], ["4h", "1d"])
            self.assertIn(("SOXL", "4h"), md.klines)
            self.assertIn(("SOXL", "1d"), md.klines)
            self.assertEqual(md.funding["SOXL"], {"times": [], "rates": []})
            self.assertIn("SOXL", md.equities)
            self.assertIsNone(md.funding_event_at("SOXL", 10 ** 12))

    def test_missing_symbol_still_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                MarketData.load(d, ["NOPE"], ["4h", "1d"])

    def test_allow_equities_false_is_strict(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_equity(d, "ARM", "4h", [{"open_time": 1, "open": 1.0, "high": 1.0,
                                                 "low": 1.0, "close": 1.0, "volume": 1.0,
                                                 "close_time": 2}])
            with self.assertRaises(FileNotFoundError):
                MarketData.load(d, ["ARM"], ["4h"], allow_equities=False)


if __name__ == "__main__":
    unittest.main()
