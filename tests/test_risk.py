"""Risk constraint enforcement (leverage cap, circuit breakers, kill switch)."""

import os
import tempfile
import unittest

from bnbot.risk import RiskManager
from synth import make_config


class TestRisk(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        cfg = make_config(self._tmp.name)
        self.rm = RiskManager(cfg["risk"])
        self.kill_file = cfg["risk"]["kill_switch_file"]

    def tearDown(self):
        self._tmp.cleanup()

    def test_symbol_weight_cap(self):
        w = self.rm.apply({"A": 1.2, "B": -0.8}, {}, 10000, 10000, 10000)
        self.assertAlmostEqual(w["A"], 0.35)
        self.assertAlmostEqual(w["B"], -0.35)

    def test_gross_leverage_cap(self):
        target = {s: 0.35 for s in "ABCDEFGH"}  # gross 2.8 after symbol cap
        w = self.rm.apply(target, {}, 10000, 10000, 10000)
        self.assertAlmostEqual(sum(abs(v) for v in w.values()), 2.0, places=9)

    def test_daily_loss_stop_blocks_new_and_increased_risk(self):
        eq, day = 9600.0, 10000.0  # -4% intraday -> breaker armed
        # existing 0.2 long: hold, don't increase
        self.assertEqual(self.rm.apply({"A": 0.4}, {"A": 0.2}, eq, 10000, day)["A"], 0.2)
        # reduction allowed
        self.assertEqual(self.rm.apply({"A": 0.1}, {"A": 0.2}, eq, 10000, day)["A"], 0.1)
        # new entry from flat blocked
        self.assertEqual(self.rm.apply({"B": 0.3}, {"B": 0.0}, eq, 10000, day)["B"], 0.0)
        # direction flip blocked -> flat
        self.assertEqual(self.rm.apply({"A": -0.3}, {"A": 0.2}, eq, 10000, day)["A"], 0.0)
        # breaker not armed when the day is not in loss
        w = self.rm.apply({"A": 0.35}, {"A": 0.2}, 9800.0, 10000.0, 9800.0)
        self.assertEqual(w["A"], 0.35)

    def test_drawdown_throttle_halves(self):
        w = self.rm.apply({"A": 0.4, "B": -0.2}, {}, 8400.0, 10000.0, 8400.0)  # dd 16%
        self.assertAlmostEqual(w["A"], 0.2)
        self.assertAlmostEqual(w["B"], -0.1)

    def test_drawdown_halt_flattens(self):
        w = self.rm.apply({"A": 0.3}, {}, 7400.0, 10000.0, 7400.0)  # dd 26%
        self.assertEqual(w, {"A": 0.0})

    def test_kill_switch_flattens_and_blocks(self):
        w = self.rm.apply({"A": 0.3, "B": -0.3}, {"A": 0.3, "B": -0.3}, 10000, 10000, 10000)
        self.assertEqual(w, {"A": 0.3, "B": -0.3})  # inactive: untouched
        with open(self.kill_file, "w", encoding="utf-8") as f:
            f.write("halt")
        self.assertTrue(self.rm.kill_switch_active())
        w = self.rm.apply({"A": 0.3, "B": -0.3}, {"A": 0.3, "B": -0.3}, 10000, 10000, 10000)
        self.assertEqual(w, {"A": 0.0, "B": 0.0})  # exists -> flatten, reject all
        os.remove(self.kill_file)
        self.assertFalse(self.rm.kill_switch_active())


if __name__ == "__main__":
    unittest.main()
