"""Sleeve-aware observability.

The dashboard snapshot and the readiness report must read what each sleeve
actually produced (state/sleeves/<id>/, logs/sleeves/<id>/). Before 2026-10-05
both read only the top-level single-account files, which stopped updating when
the A/B/C framework landed on 2026-09-30 -- so the dashboard showed a 6-day-old
equity and the readiness report judged a portfolio nobody was trading.
"""

import json
import os
import tempfile
import unittest

from bnbot.report import evaluate_all
from bnbot.server import aggregate_snapshot, discover_sleeves, snapshot


def build_fixture(root, sleeves):
    """Write config.json + per-sleeve state/logs.

    sleeves = {id: (name, share, equity, trades)}
    """
    cfg = {"capital": 10000.0, "sleeves": {"enabled": True, "list": []}}
    for sid, (name, share, equity, trades) in sleeves.items():
        cfg["sleeves"]["list"].append({"id": sid, "name": name, "share": share})
        sd = os.path.join(root, "state", "sleeves", sid)
        ld = os.path.join(root, "logs", "sleeves", sid)
        os.makedirs(sd, exist_ok=True)
        os.makedirs(ld, exist_ok=True)
        with open(os.path.join(sd, "portfolio.json"), "w", encoding="utf-8") as f:
            json.dump({"cash": equity, "positions": {"BTCUSDT": {"qty": 1.0, "entry_price": 1.0}},
                       "peak_equity": equity}, f)
        with open(os.path.join(sd, "STATE.md"), "w", encoding="utf-8") as f:
            f.write(f"## 2026-10-01T00:00:00+00:00  equity={equity:,.2f}  orders=1  rejected=0\n")
        with open(os.path.join(ld, "orders-20261001.log"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "2026-10-01T00:00:00+00:00", "action": "ROUND",
                                "equity": equity, "kill_switch": False, "orders": 1}) + "\n")
            for _ in range(trades):
                f.write(json.dumps({"ts": "2026-10-01T00:00:00+00:00", "symbol": "BTCUSDT",
                                    "side": "BUY", "qty": 1, "fee": 0.1}) + "\n")
    with open(os.path.join(root, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return cfg


class TestServerSleeveView(unittest.TestCase):
    def test_aggregate_reads_each_sleeve(self):
        with tempfile.TemporaryDirectory() as d:
            build_fixture(d, {"A": ("长线", 0.6, 6100.0, 3), "C": ("实验", 0.1, 990.0, 0)})
            agg = aggregate_snapshot(os.path.join(d, "state"))
            self.assertEqual(agg["mode"], "sleeves")
            self.assertAlmostEqual(agg["equity"], 7090.0)
            self.assertAlmostEqual(agg["capital"], 10000.0)
            self.assertEqual(agg["positions"], 2)
            self.assertFalse(agg["kill_switch"])
            by = {r["id"]: r for r in agg["sleeves"]}
            self.assertAlmostEqual(by["A"]["capital"], 6000.0)
            self.assertAlmostEqual(by["A"]["equity"], 6100.0)
            self.assertAlmostEqual(by["A"]["pnl"], 100.0)
            self.assertAlmostEqual(by["A"]["pnl_pct"], 1.67, places=2)
            self.assertAlmostEqual(by["C"]["capital"], 1000.0)
            self.assertAlmostEqual(by["C"]["pnl"], -10.0)
            self.assertEqual(by["C"]["name"], "实验")

    def test_sleeve_halt_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            build_fixture(d, {"A": ("长线", 0.6, 6000.0, 1), "B": ("短线", 0.4, 3000.0, 1)})
            open(os.path.join(d, "state", "sleeves", "B", "KILL_SWITCH"), "w").close()
            agg = aggregate_snapshot(os.path.join(d, "state"))
            self.assertTrue(agg["kill_switch"])
            self.assertEqual(agg["halted"], ["B"])
            by = {r["id"]: r for r in agg["sleeves"]}
            self.assertFalse(by["A"]["halted"])
            self.assertTrue(by["B"]["halted"])

    def test_legacy_kill_switch_next_to_state_is_reported(self):
        """The panel hard-coded kill_switch=False, so it always claimed 风控正常."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "state"))
            with open(os.path.join(d, "state", "portfolio.json"), "w", encoding="utf-8") as f:
                json.dump({"cash": 100.0, "positions": {}}, f)
            self.assertFalse(snapshot(os.path.join(d, "state"))["kill_switch"])
            open(os.path.join(d, "KILL_SWITCH"), "w").close()   # repo root, next to state/
            self.assertTrue(snapshot(os.path.join(d, "state"))["kill_switch"])

    def test_discover_ignores_dirs_without_products(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "state", "sleeves", "empty"))
            self.assertEqual(discover_sleeves(os.path.join(d, "state")), [])

    def test_legacy_snapshot_still_works(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "state"))
            with open(os.path.join(d, "state", "portfolio.json"), "w", encoding="utf-8") as f:
                json.dump({"cash": 123.0, "positions": {}}, f)
            self.assertEqual(snapshot(os.path.join(d, "state"))["cash"], 123.0)


class TestReportSleeveView(unittest.TestCase):
    def test_each_sleeve_judged_separately(self):
        with tempfile.TemporaryDirectory() as d:
            build_fixture(d, {"A": ("长线", 0.6, 6100.0, 40), "C": ("实验", 0.1, 990.0, 5)})
            rep = evaluate_all(d)
            self.assertEqual(rep["mode"], "sleeves")
            self.assertFalse(rep["go"])
            by = {r["sleeve"]: r for r in rep["sleeves"]}
            self.assertTrue(by["A"]["gates"]["G2_trades"]["pass"])    # 40 >= 30
            self.assertFalse(by["C"]["gates"]["G2_trades"]["pass"])   # 5  <  30

    def test_ignores_stale_top_level_logs(self):
        """Regression: the old report globbed logs/orders-*.log and counted 99
        phantom trades, ignoring every real sleeve round after 2026-09-30."""
        with tempfile.TemporaryDirectory() as d:
            build_fixture(d, {"A": ("长线", 1.0, 6000.0, 2)})
            with open(os.path.join(d, "logs", "orders-20260930.log"), "w", encoding="utf-8") as f:
                for _ in range(99):
                    f.write(json.dumps({"ts": "2026-09-30T00:00:00+00:00", "symbol": "STALE",
                                        "side": "BUY", "qty": 1}) + "\n")
            rep = evaluate_all(d)
            self.assertEqual(rep["mode"], "sleeves")
            by = {r["sleeve"]: r for r in rep["sleeves"]}
            self.assertEqual(by["A"]["trades"], 2)   # not 101

    def test_falls_back_to_legacy_without_sleeves(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "logs"))
            rep = evaluate_all(d)
            self.assertEqual(rep["mode"], "legacy")
            self.assertFalse(rep["go"])


if __name__ == "__main__":
    unittest.main()
