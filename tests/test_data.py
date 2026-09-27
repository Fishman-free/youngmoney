"""CSV cache round-trip, merge/dedupe, exchange filters, aligned grid."""

import json
import os
import tempfile
import unittest

from bnbot.data import (
    MS_PER_HOUR,
    AlignedBars,
    MarketData,
    load_klines_csv,
    round_step,
    symbol_filters,
    update_klines_cache,
)
from synth import T0


class FakeClient:
    """Offline stand-in for RestClient: returns pre-batched get_json replies."""

    def __init__(self, batches):
        self.batches = list(batches)

    def get_json(self, path):
        return self.batches.pop(0)


def raw_kline(t, close=100.0, step_ms=4 * MS_PER_HOUR):
    # REST array layout: [open_time, o, h, l, c, v, close_time, ...]
    return [t, str(close), str(close + 1), str(close - 1), str(close), "10.0", t + step_ms - 1]


class TestKlinesCache(unittest.TestCase):
    def test_fetch_merge_dedupe_resume(self):
        with tempfile.TemporaryDirectory() as data_dir:
            client = FakeClient([[raw_kline(T0), raw_kline(T0 + 4 * MS_PER_HOUR)]])
            n, first, last = update_klines_cache(client, data_dir, "TESTUSDT", "4h", T0)
            self.assertEqual((n, first, last), (2, T0, T0 + 4 * MS_PER_HOUR))

            # second run: fetches from last+step; overlapping/new rows dedupe
            client = FakeClient([[raw_kline(T0 + 4 * MS_PER_HOUR), raw_kline(T0 + 8 * MS_PER_HOUR)]])
            n, _, last = update_klines_cache(client, data_dir, "TESTUSDT", "4h", T0)
            self.assertEqual((n, last), (3, T0 + 8 * MS_PER_HOUR))

            rows = load_klines_csv(os.path.join(data_dir, "TESTUSDT_4h.csv"))
            self.assertEqual([r["open_time"] for r in rows],
                             [T0, T0 + 4 * MS_PER_HOUR, T0 + 8 * MS_PER_HOUR])
            self.assertAlmostEqual(rows[0]["close"], 100.0)

    def test_fetch_empty_batch_keeps_cache(self):
        with tempfile.TemporaryDirectory() as data_dir:
            client = FakeClient([[]])
            n, first, last = update_klines_cache(client, data_dir, "TESTUSDT", "4h", T0)
            self.assertEqual((n, first, last), (0, 0, 0))
            self.assertFalse(os.path.exists(os.path.join(data_dir, "TESTUSDT_4h.csv")))


class TestFilters(unittest.TestCase):
    def test_round_step_floors(self):
        self.assertAlmostEqual(round_step(0.12345, 0.001), 0.123)
        self.assertEqual(round_step(1.0, 0.5), 1.0)
        self.assertEqual(round_step(0.4, 0.5), 0.0)

    def test_symbol_filters_parse(self):
        with tempfile.TemporaryDirectory() as data_dir:
            info = {
                "symbols": [{
                    "symbol": "XYZUSDT",
                    "pricePrecision": 2,
                    "quantityPrecision": 3,
                    "filters": [
                        {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                        {"filterType": "MIN_NOTIONAL", "notional": "5.0"},
                    ],
                }]
            }
            with open(os.path.join(data_dir, "exchangeInfo.json"), "w", encoding="utf-8") as f:
                json.dump(info, f)
            flt = symbol_filters(data_dir, "XYZUSDT")
            self.assertEqual(flt["step_size"], 0.001)
            self.assertEqual(flt["min_notional"], 5.0)
            self.assertEqual(flt["price_precision"], 2)
            with self.assertRaises(KeyError):
                symbol_filters(data_dir, "NOSUCH")


class TestAlignedBars(unittest.TestCase):
    def test_union_grid_and_forward_fill(self):
        from synth import kline_rows

        md = MarketData()
        t = lambda i: T0 + i * 4 * MS_PER_HOUR
        from bnbot.data import BarSeries

        md.klines[("AUSDT", "4h")] = BarSeries(
            "AUSDT", "4h", kline_rows([t(0), t(1), t(2)], [1.0, 2.0, 3.0]))
        md.klines[("BUSDT", "4h")] = BarSeries(
            "BUSDT", "4h", kline_rows([t(1), t(2)], [10.0, 20.0]))
        md.funding["AUSDT"] = {"times": [], "rates": []}
        md.funding["BUSDT"] = {"times": [], "rates": []}

        ab = AlignedBars.build(md, ["AUSDT", "BUSDT"])
        self.assertEqual(ab.grid, [t(0), t(1), t(2)])
        self.assertEqual(ab.closes["AUSDT"], [1.0, 2.0, 3.0])
        self.assertEqual(ab.closes["BUSDT"], [None, 10.0, 20.0])


if __name__ == "__main__":
    unittest.main()
