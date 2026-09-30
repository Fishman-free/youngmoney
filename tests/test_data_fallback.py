import json
import os
import tempfile
import unittest

import bnbot.data as data


class TestSyntheticFilters(unittest.TestCase):
    def test_unknown_symbol_returns_flagged_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            with open(data.exchange_info_path(d), "w", encoding="utf-8") as f:
                json.dump({"symbols": [{"symbol": "BTCUSDT", "pricePrecision": 1,
                                        "quantityPrecision": 3,
                                        "filters": [{"filterType": "LOT_SIZE",
                                                     "stepSize": "0.001", "minQty": "0.001"}]}]}, f)
            known = data.symbol_filters(d, "BTCUSDT")
            self.assertEqual(known["step_size"], 0.001)
            self.assertNotIn("synthetic", known)

            unknown = data.symbol_filters(d, "QNTUSDT", allow_synthetic=True)
            self.assertTrue(unknown["synthetic"])          # flagged for real executors
            self.assertGreater(unknown["step_size"], 0)
            self.assertGreater(unknown["min_notional"], 0)

    def test_strict_by_default_for_real_mode(self):
        with tempfile.TemporaryDirectory() as d:
            with open(data.exchange_info_path(d), "w", encoding="utf-8") as f:
                json.dump({"symbols": []}, f)
            with self.assertRaises(KeyError):
                data.symbol_filters(d, "QNTUSDT")           # real mode must refuse


class TestMexcFallback(unittest.TestCase):
    def test_rows_normalised_like_binance(self):
        class FakeResp:
            def __init__(self, payload):
                self._p = json.dumps(payload).encode()

            def read(self):
                return self._p

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class FakeOpener:
            def __init__(self, payload):
                self.payload = payload
                self.calls = []

            def open(self, req, timeout=30):
                self.calls.append(req.full_url)
                return FakeResp(self.payload)

        # one closed bar, one still-open bar (must be filtered out)
        step = data.INTERVAL_MS["4h"]
        t0 = data.now_ms() - 10 * step
        payload = [[t0, "1.0", "2.0", "0.5", "1.5", "100", t0 + step - 1],
                   [t0 + step, "1.5", "3.0", "1.0", "2.5", "50",
                    data.now_ms() + 10 * step]]  # close_time in the future
        fake = FakeOpener(payload)
        orig = data.urllib.request.build_opener
        data.urllib.request.build_opener = lambda *a, **k: fake
        try:
            rows = data.fetch_klines_mexc("QNTUSDT", "4h", t0, t0 + 5 * step)
        finally:
            data.urllib.request.build_opener = orig
        self.assertEqual(len(rows), 1)                     # open bar dropped
        r = rows[0]
        self.assertEqual(set(r), {"open_time", "open", "high", "low", "close",
                                  "volume", "close_time"})
        self.assertEqual(r["close"], 1.5)
        self.assertIn("/api/v3/klines", fake.calls[0])
        self.assertIn("interval=4h", fake.calls[0])

    def test_interval_mapping(self):
        self.assertEqual(data.MEXC_INTERVAL["1h"], "60m")
        self.assertEqual(data.MEXC_INTERVAL["4h"], "4h")

    def test_cache_update_falls_back_when_binance_fails(self):
        with tempfile.TemporaryDirectory() as d:
            step = data.INTERVAL_MS["4h"]
            start = data.now_ms() - 100 * step
            row = {"open_time": start, "open": 1.0, "high": 2.0, "low": 0.5,
                   "close": 1.5, "volume": 10.0, "close_time": start + step - 1}

            def boom(*a, **k):
                raise RuntimeError("HTTP 451 restricted location")

            called = {}

            def fake_mexc(symbol, interval, frm, end=None, proxy=None):
                called["symbol"], called["proxy"] = symbol, proxy
                return [row]

            orig_kl, orig_mx = data.fetch_klines, data.fetch_klines_mexc
            data.fetch_klines, data.fetch_klines_mexc = boom, fake_mexc
            try:
                n, first, last = data.update_klines_cache(
                    type("C", (), {"proxy": "http://127.0.0.1:7890"})(),
                    d, "QNTUSDT", "4h", start)
            finally:
                data.fetch_klines, data.fetch_klines_mexc = orig_kl, orig_mx
            self.assertEqual(n, 1)
            self.assertEqual(called["symbol"], "QNTUSDT")
            self.assertEqual(called["proxy"], "http://127.0.0.1:7890")
            self.assertTrue(os.path.exists(data.kline_path(d, "QNTUSDT", "4h")))


if __name__ == "__main__":
    unittest.main()
