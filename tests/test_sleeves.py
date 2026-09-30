import json
import os
import tempfile
import unittest

from bnbot.risk import RiskManager
from bnbot.sleeves import SLEEVE_CEILINGS, aggregate, build_sleeves


def base_cfg(tmp):
    return {
        "capital": 10000.0,
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "strategy": {"donchian_window": 48, "xs_weight": 0.6, "rebalance_band": 0.12},
        "risk": {"max_gross_leverage": 2.0, "max_symbol_weight": 0.35,
                 "daily_loss_stop": 0.03, "drawdown_halt": 0.25},
        "live": {"paper_interval_hours": 4,
                 "state_file": os.path.join(tmp, "state", "portfolio.json"),
                 "log_dir": os.path.join(tmp, "logs")},
        "sleeves": {"enabled": True, "list": [
            {"id": "A", "name": "长线", "share": 0.6, "enabled": True},
            {"id": "B", "name": "短线", "share": 0.3, "enabled": True,
             "symbols": ["BTCUSDT"],
             "strategy": {"donchian_window": 24},
             "risk": {"max_gross_leverage": 3.0, "daily_loss_stop": 0.04}},
            {"id": "C", "name": "实验", "share": 0.1, "enabled": False,
             "risk": {"max_gross_leverage": 25.0}},   # asks for 25x -> clamped
        ]},
    }


class TestSleeveBuild(unittest.TestCase):
    def test_no_section_returns_empty(self):
        self.assertEqual(build_sleeves({"capital": 1.0, "symbols": [],
                                        "strategy": {}, "risk": {},
                                        "live": {}}), [])

    def test_capital_split_and_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            sl = build_sleeves(base_cfg(d), base_dir=d)
            self.assertEqual([s["sleeve"]["id"] for s in sl], ["A", "B", "C"])
            self.assertAlmostEqual(sl[0]["capital"], 6000.0)
            self.assertAlmostEqual(sl[1]["capital"], 3000.0)
            self.assertAlmostEqual(sl[2]["capital"], 1000.0)
            paths = [s["live"]["state_file"] for s in sl]
            self.assertEqual(len(set(paths)), 3)                      # separate accounts
            ks = [s["risk"]["kill_switch_file"] for s in sl]
            self.assertEqual(len(set(ks)), 3)                         # separate kill switches
            logs = [s["live"]["log_dir"] for s in sl]
            self.assertEqual(len(set(logs)), 3)

    def test_overrides_merge(self):
        with tempfile.TemporaryDirectory() as d:
            sl = build_sleeves(base_cfg(d), base_dir=d)
            a, b = sl[0], sl[1]
            self.assertEqual(a["strategy"]["donchian_window"], 48)     # inherited
            self.assertEqual(b["strategy"]["donchian_window"], 24)     # overridden
            self.assertEqual(b["strategy"]["xs_weight"], 0.6)          # inherited
            self.assertEqual(b["symbols"], ["BTCUSDT"])
            self.assertEqual(a["symbols"], ["BTCUSDT", "ETHUSDT"])

    def test_ceilings_cannot_be_loosened(self):
        with tempfile.TemporaryDirectory() as d:
            sl = build_sleeves(base_cfg(d), base_dir=d)
            self.assertLessEqual(sl[0]["risk"]["max_gross_leverage"], 2.0)
            self.assertLessEqual(sl[1]["risk"]["max_gross_leverage"], 3.0)
            self.assertEqual(sl[2]["risk"]["max_gross_leverage"],
                             SLEEVE_CEILINGS["C"]["max_gross_leverage"])   # 25 -> 10


class TestSleeveIsolation(unittest.TestCase):
    def test_kill_switch_is_per_sleeve(self):
        with tempfile.TemporaryDirectory() as d:
            sl = build_sleeves(base_cfg(d), base_dir=d)
            a, b = sl[0], sl[1]
            os.makedirs(os.path.dirname(a["risk"]["kill_switch_file"]), exist_ok=True)
            open(a["risk"]["kill_switch_file"], "w").close()
            self.assertTrue(RiskManager(a["risk"]).kill_switch_active())
            self.assertFalse(RiskManager(b["risk"]).kill_switch_active())

    def test_daily_stop_is_per_sleeve(self):
        with tempfile.TemporaryDirectory() as d:
            sl = build_sleeves(base_cfg(d), base_dir=d)
            a, b = sl[0], sl[1]
            ra, rb = RiskManager(a["risk"]), RiskManager(b["risk"])
            tgt = {"BTCUSDT": 0.5}
            cur = {"BTCUSDT": 0.0}
            # A: -3.5% day -> no new entries; B: same day -> still allowed
            self.assertEqual(ra.apply(tgt, cur, equity=9650.0, peak_equity=10000.0,
                                      day_start_equity=10000.0)["BTCUSDT"], 0.0)
            self.assertGreater(rb.apply(tgt, cur, equity=9650.0, peak_equity=10000.0,
                                        day_start_equity=10000.0)["BTCUSDT"], 0.0)


class TestAggregate(unittest.TestCase):
    def test_sums_cash_and_reports_halted(self):
        with tempfile.TemporaryDirectory() as d:
            sl = build_sleeves(base_cfg(d), base_dir=d)
            for s, cash in zip(sl, (5000.0, 2500.0, 900.0)):
                p = s["live"]["state_file"]
                os.makedirs(os.path.dirname(p), exist_ok=True)
                json.dump({"cash": cash, "positions": {"BTCUSDT": {"qty": 1.0}},
                           "peak_equity": cash}, open(p, "w"))
            os.makedirs(os.path.dirname(sl[2]["risk"]["kill_switch_file"]), exist_ok=True)
            open(sl[2]["risk"]["kill_switch_file"], "w").close()
            tot = aggregate(sl)
            self.assertAlmostEqual(tot["cash"], 8400.0)
            self.assertAlmostEqual(tot["capital"], 10000.0)
            self.assertEqual(tot["positions"], 3)
            self.assertEqual(tot["halted"], ["C"])


if __name__ == "__main__":
    unittest.main()
