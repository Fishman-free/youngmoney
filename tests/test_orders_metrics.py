import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from bnbot.metrics import Metrics
from bnbot.orders import (STATUS_LOST, STATUS_PLACED, STATUS_SENT, STATUS_SIM,
                          age_pending, mark_placed, mark_sent, mark_sim_filled, new_intent)
from bnbot.server import Handler, history, snapshot


class TestOrderLifecycle(unittest.TestCase):
    def test_intent_wraps_without_mutation(self):
        o = {"symbol": "BTCUSDT", "side": "BUY", "qty": 1}
        rec = new_intent(o, 7)
        self.assertNotIn("status", o)          # input untouched
        self.assertEqual(rec["status"], "intent")
        self.assertEqual(rec["seq"], 7)
        self.assertIsNone(rec["order_id"])

    def test_receipt_lifecycle(self):
        rec = mark_sent(new_intent({"symbol": "X"}, 1))
        self.assertEqual(rec["status"], STATUS_SENT)
        mark_placed(rec, 42)
        self.assertEqual(rec["status"], STATUS_PLACED)
        self.assertEqual(rec["order_id"], 42)

    def test_unreceipted_becomes_lost(self):
        recs = [mark_sent(new_intent({"symbol": "X"}, 1))]
        for _ in range(9):
            age_pending(recs, max_cycles=10)
            self.assertEqual(recs[0]["status"], STATUS_SENT)
        age_pending(recs, max_cycles=10)
        self.assertEqual(recs[0]["status"], STATUS_LOST)

    def test_paper_marks_sim(self):
        rec = mark_sim_filled(new_intent({"symbol": "X"}, 1))
        self.assertEqual(rec["status"], STATUS_SIM)


class TestMetrics(unittest.TestCase):
    def test_cycle_increments_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "metrics.json")
            m = Metrics.load(p)
            self.assertEqual(m.cycles, 0)
            m.cycle(orders=2, rejected_verifier=1, rejected_judgment=1, fills=2, fees=0.5, equity=100.0)
            m.cycle(orders=0, late=True)
            m.save()
            m2 = Metrics.load(p)
            self.assertEqual(m2.cycles, 2)
            self.assertEqual(m2.orders, 2)
            self.assertEqual(m2.rejected_verifier, 1)
            self.assertEqual(m2.late, 1)
            self.assertAlmostEqual(m2.fees, 0.5)
            self.assertEqual(m2.last_cycle["equity"], 100.0)

    def test_totals_shape(self):
        d = Metrics().cycle(orders=1).to_dict()
        for k in ("cycles", "orders", "fills", "rejected_verifier", "rejected_judgment",
                  "late", "fees", "realized_pnl", "last_cycle"):
            self.assertIn(k, d)


class TestStatusServer(unittest.TestCase):
    def test_snapshot_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "portfolio.json"), "w", encoding="utf-8") as f:
                json.dump({"cash": 123.45, "positions": {"A": {}, "B": {}}, "peak_equity": 200.0}, f)
            with open(os.path.join(d, "metrics.json"), "w", encoding="utf-8") as f:
                json.dump({"cycles": 3, "orders": 1}, f)
            with open(os.path.join(d, "STATE.md"), "w", encoding="utf-8") as f:
                f.write("## t1  equity=100\nline\n\n## t2  equity=101\nline\n")
            snap = snapshot(d)
            self.assertEqual(snap["cash"], 123.45)
            self.assertEqual(snap["positions"], 2)
            self.assertIn("metrics", snap)
            self.assertEqual(len(snap["position_list"]), 2)
            self.assertIsInstance(snap["equity_series"], list)
            blocks = history(d, 5)
            self.assertEqual(len(blocks), 2)
            self.assertTrue(blocks[-1].startswith("## t2"))

    def test_dashboard_served_verbatim_not_json_escaped(self):
        """Regression: a str body must be served as-is, not json.dumps'd.

        Bug found 2026-09-30: json-escaping the HTML turned every newline into a
        literal \\n and every quote into \\", so the inline <script> failed to
        parse in the browser and the dashboard rendered empty.
        """
        import re as _re
        with tempfile.TemporaryDirectory() as d:
            Handler.state_dir = d
            srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                base = f"http://127.0.0.1:{srv.server_address[1]}"
                body = urllib.request.urlopen(base + "/dashboard", timeout=5).read().decode("utf-8")
                self.assertIn("\n", body)                       # real newlines kept
                self.assertNotIn("\\nfunction", body)           # not JSON-escaped
                self.assertNotIn('\\"', body)
                m = _re.search(r"<script>([\s\S]*)</script>", body)
                self.assertIsNotNone(m)
                self.assertIn("function tick", m.group(1))
            finally:
                srv.shutdown()

    def test_http_endpoints_live(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "portfolio.json"), "w", encoding="utf-8") as f:
                json.dump({"cash": 9.0, "positions": {}}, f)
            Handler.state_dir = d
            srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                base = f"http://127.0.0.1:{srv.server_address[1]}"
                with urllib.request.urlopen(base + "/health", timeout=5) as r:
                    self.assertEqual(json.loads(r.read())["ok"], True)
                with urllib.request.urlopen(base + "/", timeout=5) as r:
                    self.assertEqual(json.loads(r.read())["cash"], 9.0)
                with urllib.request.urlopen(base + "/dashboard", timeout=5) as r:
                    body = r.read()
                    self.assertIn("bnbot", body.decode("utf-8"))
                    self.assertIn("量化平台状态", body.decode("utf-8"))
                with urllib.request.urlopen(base + "/nope", timeout=5) as r:  # noqa: F841
                    pass
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 404)
            finally:
                srv.shutdown()


if __name__ == "__main__":
    unittest.main()
