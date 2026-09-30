import json
import os
import tempfile
import time
import unittest

import bnbot.usstock as us


class FakeResp:
    def __init__(self, payload):
        self._b = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def patch_opener(monkeypatch_target, payloads):
    """Return an opener stub that pops payloads in order (or raises)."""
    calls = []

    class Opener:
        def open(self, req, timeout=30):
            calls.append(req.full_url)
            p = payloads.pop(0) if payloads else {"chart": {"result": [{}], "error": None}}
            if isinstance(p, Exception):
                raise p
            return FakeResp(p)

    orig = monkeypatch_target._opener
    monkeypatch_target._opener = lambda proxy=None: Opener()
    return calls, orig


class TestYahooParsing(unittest.TestCase):
    def test_chart_normalised_and_nulls_skipped(self):
        payload = {"chart": {"error": None, "result": [{
            "timestamp": [1000, 2000, 3000],
            "indicators": {"quote": [{
                "open": [1.0, None, 3.0], "high": [2.0, 5.0, 4.0],
                "low": [0.5, 4.0, 2.5], "close": [1.5, 4.5, 3.5],
                "volume": [10, 20, None]}]}}]}}
        orig = us._opener
        us._opener = lambda proxy=None: type("O", (), {
            "open": lambda self, req, timeout=30: FakeResp(payload)})()
        try:
            bars = us.fetch_chart("SOXL", "1d", "5y")
        finally:
            us._opener = orig
        self.assertEqual(len(bars), 2)                       # null row dropped
        self.assertEqual(bars[0]["open"], 1.0)
        self.assertEqual(bars[1]["close"], 3.5)
        self.assertEqual(bars[1]["volume"], 0.0)             # None -> 0.0
        self.assertLess(bars[0]["open_time"], bars[1]["open_time"])

    def test_chart_error_raises(self):
        payload = {"chart": {"error": {"code": "Not Found"}, "result": None}}
        orig = us._opener
        us._opener = lambda proxy=None: type("O", (), {
            "open": lambda self, req, timeout=30: FakeResp(payload)})()
        try:
            with self.assertRaises(RuntimeError):
                us.fetch_chart("NOPE", "1d", "5y")
        finally:
            us._opener = orig


class TestEastmoneyParsing(unittest.TestCase):
    def test_kline_field_order(self):
        # 日期,开,收,高,低,成交量  (note: close BEFORE high/low)
        payload = {"data": {"klines": ["2026-09-28,10.0,10.5,10.8,9.9,12345,1",
                                       "2026-09-29,10.6,11.0,11.2,10.4,23456,1"]}}
        orig = us._opener
        us._opener = lambda proxy=None: type("O", (), {
            "open": lambda self, req, timeout=30: FakeResp(payload)})()
        try:
            bars = us.fetch_chart_eastmoney("ARM", "1d")
        finally:
            us._opener = orig
        self.assertEqual(len(bars), 2)
        b = bars[0]
        self.assertEqual((b["open"], b["close"], b["high"], b["low"]), (10.0, 10.5, 10.8, 9.9))
        self.assertEqual(b["volume"], 12345.0)
        self.assertLess(bars[0]["open_time"], bars[1]["open_time"])


class TestSourceFallback(unittest.TestCase):
    def test_yahoo_failure_falls_back_to_eastmoney(self):
        em = {"data": {"klines": ["2026-09-29,1.0,1.1,1.2,0.9,100,1"]}}
        seq = [RuntimeError("HTTP Error 429: Too Many Requests"), em]
        orig = us._opener

        class Opener:
            def open(self, req, timeout=30):
                p = seq.pop(0)
                if isinstance(p, Exception):
                    raise p
                return FakeResp(p)

        us._opener = lambda proxy=None: Opener()
        try:
            rows, src = us.fetch_chart_any("SOXL", "1d", "5y")
        finally:
            us._opener = orig
        self.assertEqual(src, "eastmoney")
        self.assertEqual(len(rows), 1)


class TestEquityCache(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [{"open_time": 1000, "open": 1.0, "high": 2.0, "low": 0.5,
                     "close": 1.5, "volume": 10.0, "close_time": 1999},
                    {"open_time": 2000, "open": 1.5, "high": 2.5, "low": 1.0,
                     "close": 2.0, "volume": 20.0, "close_time": 2999}]
            path, n = us.save_bars(d, "SOXL", "1d", rows)
            self.assertEqual(n, 2)
            self.assertTrue(path.endswith(os.path.join("equities", "SOXL_1d.csv")))
            back = us.load_bars(d, "SOXL", "1d")
            self.assertEqual(back, rows)
            self.assertEqual(us.load_bars(d, "MISSING", "1d"), [])

    def test_interval_map_covers_engine_intervals(self):
        for itv in ("1d", "1h", "4h"):
            self.assertIn(itv, us.INTERVAL_SECONDS)

    def test_resample_1h_to_4h(self):
        hour = 3600 * 1000
        bars = [{"open_time": i * hour, "open": 1.0 + i, "high": 2.0 + i,
                 "low": 0.5 + i, "close": 1.5 + i, "volume": 10.0,
                 "close_time": (i + 1) * hour - 1} for i in range(9)]  # 9h -> two 4h, 1h dropped
        out = us.resample(bars, 4)
        self.assertEqual(len(out), 2)                        # partial bucket dropped
        self.assertEqual(out[0]["open"], 1.0)
        self.assertEqual(out[0]["close"], 1.5 + 3)
        self.assertEqual(out[0]["high"], 2.0 + 3)
        self.assertEqual(out[0]["low"], 0.5)
        self.assertEqual(out[0]["volume"], 40.0)
        self.assertEqual(out[1]["open"], 1.0 + 4)


if __name__ == "__main__":
    unittest.main()
