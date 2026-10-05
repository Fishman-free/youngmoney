import unittest

from bnbot.verify import SignalVerifier
from bnbot.report import evaluate, max_drawdown, sharpe_ann

from synth import T0, MS_PER_HOUR, make_config, make_market


SYM = "TESTUSDT"


class TestVerifier(unittest.TestCase):
    def _ctx(self, strat):
        from bnbot.strategy import Context
        return Context(strat.engine, T0 + 110 * 24 * MS_PER_HOUR)

    def _setup(self, trend_mom_up=True):
        from bnbot.strategy import CompositeStrategy
        md = make_market(SYM, closes4h=[100.0] * 200, closes1d=[100.0] * 120)
        cfg = make_config("unused")
        strat = CompositeStrategy(cfg, md)
        ctx = self._ctx(strat)
        return md, ctx

    def test_reduce_only_always_passes(self):
        md, ctx = self._setup()
        v = SignalVerifier(md, {SYM: 100.0})
        ok, reason = v.verify({"symbol": SYM, "side": "SELL", "qty": 1, "reduce_only": True}, ctx)
        self.assertTrue(ok)
        self.assertEqual(reason, "reduce-only")

    def test_mark_deviation_rejected(self):
        md, ctx = self._setup()
        v = SignalVerifier(md, {SYM: 130.0})  # 30% above close -> dirty data
        ok, reason = v.verify({"symbol": SYM, "side": "BUY", "qty": 1, "reduce_only": False}, ctx)
        self.assertFalse(ok)
        self.assertIn("D1", reason)

    def test_signal_disagreement_rejected(self):
        from bnbot.strategy import CompositeStrategy
        # flat market: trend=0 mom=0, any opening order must be refused (D2)
        md = make_market(SYM, closes4h=[100.0] * 200, closes1d=[100.0] * 120)
        strat = CompositeStrategy(make_config("unused"), md)
        ctx = self._ctx(strat)
        v = SignalVerifier(md, {SYM: 100.0})
        ok, reason = v.verify({"symbol": SYM, "side": "BUY", "qty": 1, "reduce_only": False}, ctx)
        self.assertFalse(ok)
        self.assertIn("D2", reason)

    def test_agreeing_signals_pass(self):
        from bnbot.strategy import CompositeStrategy
        # 4h rises 0.5%/bar (drift beats the +0.5 high offset -> breakout fires),
        # 1d has varied positive returns (mom=1, vol in range for D3)
        closes4h = [100.0 * 1.005 ** i for i in range(800)]
        rets = [0.02, -0.01, 0.03, 0.0, -0.02, 0.025]
        closes1d = [100.0]
        for i in range(119):
            closes1d.append(closes1d[-1] * (1.0 + rets[i % 6]))
        md = make_market(SYM, closes4h=closes4h, closes1d=closes1d)
        strat = CompositeStrategy(make_config("unused"), md)
        ctx = self._ctx(strat)
        v = SignalVerifier(md, {SYM: closes4h[-1]})
        ok, reason = v.verify({"symbol": SYM, "side": "BUY", "qty": 1, "reduce_only": False}, ctx)
        self.assertTrue(ok, reason)


class TestD2Modes(unittest.TestCase):
    """D2 can be narrowed per sleeve.

    Sleeve C enters on fast momentum before the slow Donchian trend confirms, so
    under the default "all" every opening was vetoed: 24 rejects / 0 fills over
    10 rounds on 2026-10-05, making its 200-trade gate structurally unreachable.
    """

    def test_default_is_all(self):
        v = SignalVerifier(None, {})
        self.assertEqual(v.p["d2_mode"], "all")

    def test_mode_matrix(self):
        cases = {
            "all":   {  # trend AND momentum must agree
                (1, 1, 1): True, (1, 0, 1): False, (0, 1, 1): False, (0, 0, 1): False,
                (-1, -1, -1): True, (0, -1, -1): False,
            },
            "any":   {(1, 1, 1): True, (1, 0, 1): True, (0, 1, 1): True, (0, 0, 1): False},
            "mom":   {(0, 1, 1): True, (1, 0, 1): False, (0, -1, -1): True, (0, 1, -1): False},
            "trend": {(1, 0, 1): True, (0, 1, 1): False, (-1, 0, -1): True},
        }
        v = SignalVerifier(None, {})
        for mode, table in cases.items():
            v.p["d2_mode"] = mode
            for (trend, mom, want), expected in table.items():
                self.assertEqual(v.d2_agrees(trend, mom, want), expected,
                                 f"mode={mode} trend={trend} mom={mom} want={want}")

    def test_sleeve_c_case_momentum_only(self):
        """trend=0 mom=+1 (buy) and trend=0 mom=-1 (sell): C's actual rejections."""
        v = SignalVerifier(None, {}, {"d2_mode": "mom"})
        self.assertTrue(v.d2_agrees(0, 1, 1))     # BUY QNTUSDT
        self.assertTrue(v.d2_agrees(0, -1, -1))   # SELL XRPUSDT
        strict = SignalVerifier(None, {})
        self.assertFalse(strict.d2_agrees(0, 1, 1))
        self.assertFalse(strict.d2_agrees(0, -1, -1))

    def test_unknown_mode_falls_back_to_all(self):
        v = SignalVerifier(None, {}, {"d2_mode": "bogus"})
        self.assertTrue(v.d2_agrees(1, 1, 1))
        self.assertFalse(v.d2_agrees(0, 1, 1))

    def test_flat_market_still_rejected_under_mom(self):
        """Narrowing D2 must not open the door to a dead-flat market."""
        from bnbot.strategy import CompositeStrategy
        md = make_market(SYM, closes4h=[100.0] * 200, closes1d=[100.0] * 120)
        ctx = TestVerifier()._ctx(CompositeStrategy(make_config("unused"), md))
        v = SignalVerifier(md, {SYM: 100.0}, {"d2_mode": "mom"})
        ok, reason = v.verify({"symbol": SYM, "side": "BUY", "qty": 1, "reduce_only": False}, ctx)
        self.assertFalse(ok)
        self.assertIn("D2", reason)

    def test_reduce_only_still_passes_under_all_modes(self):
        for mode in ("all", "any", "mom", "trend"):
            v = SignalVerifier(None, {}, {"d2_mode": mode})
            ok, reason = v.verify({"symbol": SYM, "side": "SELL", "qty": 1,
                                   "reduce_only": True}, None)
            self.assertTrue(ok, mode)
            self.assertEqual(reason, "reduce-only")


class TestReportGates(unittest.TestCase):
    def test_drawdown_and_sharpe_helpers(self):
        self.assertAlmostEqual(max_drawdown([100, 110, 99, 120]), 1.0 - 99 / 110)
        rets = [0.02, -0.01, 0.03, 0.0, -0.02, 0.025] * 10  # varied, mean > 0
        self.assertGreater(sharpe_ann(rets), 0.0)
        self.assertEqual(sharpe_ann([0.0]), 0.0)

    def test_no_go_without_history(self, ):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            rep = evaluate(d)
            self.assertFalse(rep["go"])

    def test_gates_enforced(self):
        import json, os, tempfile
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as d:
            t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
            with open(os.path.join(d, "orders-20260101.log"), "w", encoding="utf-8") as f:
                # 70 days of gentle up rounds, 35 trades -> all gates pass
                for i in range(70):
                    ts = (t0 + timedelta(days=i)).isoformat(timespec="seconds")
                    f.write(json.dumps({"ts": ts, "action": "ROUND", "equity": 100 + i,
                                        "kill_switch": False, "orders": 0}) + "\n")
                for i in range(35):
                    f.write(json.dumps({"ts": t0.isoformat(timespec="seconds"),
                                        "symbol": "X", "side": "BUY", "qty": 1}) + "\n")
            rep = evaluate(d)
            self.assertTrue(rep["go"], rep["gates"])
            # kill switch flips verdict
            with open(os.path.join(d, "orders-20260101.log"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": t0.isoformat(timespec="seconds"), "action": "ROUND",
                                    "equity": 100, "kill_switch": True, "orders": 0}) + "\n")
            rep2 = evaluate(d)
            self.assertFalse(rep2["go"])
            self.assertFalse(rep2["gates"]["G5_kill_switch"]["pass"])
