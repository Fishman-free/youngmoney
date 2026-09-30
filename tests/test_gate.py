import json
import os
import tempfile
import unittest

from bnbot.gate import DEFAULT_GATES, evaluate, max_drawdown


def write_sleeve(d, trades=0, equities=(1000.0,), fees=0.1, halt=False, symbols=("DOGEUSDT",)):
    state = os.path.join(d, "state")
    logs = os.path.join(d, "logs")
    os.makedirs(state, exist_ok=True)
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(logs, "orders-20260101.log"), "w", encoding="utf-8") as f:
        for i in range(trades):
            f.write(json.dumps({"symbol": symbols[i % len(symbols)], "side": "BUY",
                                "qty": 1, "price": 10.0, "fee": fees}) + "\n")
    with open(os.path.join(state, "STATE.md"), "w", encoding="utf-8") as f:
        for i, eq in enumerate(equities):
            f.write(f"## 2026-01-0{i+1}T00:00:00+00:00  equity={eq:,.2f}  orders=0  rejected=0\n")
    if halt:
        open(os.path.join(state, "KILL_SWITCH"), "w").close()
    return state, logs


class TestGate(unittest.TestCase):
    def test_missing_history_fails_all_count_gates(self):
        with tempfile.TemporaryDirectory() as d:
            rep = evaluate(os.path.join(d, "state"), os.path.join(d, "logs"))
            self.assertFalse(rep["checks"]["G1_trades"]["pass"])
            self.assertFalse(rep["checks"]["G2_expectancy"]["pass"])
            self.assertTrue(rep["verdict"].startswith("FAIL"))

    def test_full_pass_requires_all_four(self):
        with tempfile.TemporaryDirectory() as d:
            equities = [1000.0 + i for i in range(210)]      # monotone up -> positive expectancy
            state, logs = write_sleeve(d, trades=210, equities=equities)
            rep = evaluate(state, logs)
            self.assertTrue(all(c["pass"] for c in rep["checks"].values()), rep["checks"])
            self.assertTrue(rep["verdict"].startswith("PASS"))
            self.assertEqual(rep["trades"], 210)

    def test_drawdown_gate_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            equities = [1000.0, 1200.0, 700.0]               # -41.7% from peak
            state, logs = write_sleeve(d, trades=210, equities=equities)
            rep = evaluate(state, logs)
            self.assertFalse(rep["checks"]["G3_max_drawdown"]["pass"])
            self.assertTrue(rep["verdict"].startswith("FAIL"))

    def test_halt_gate_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            state, logs = write_sleeve(d, trades=210, equities=[1000.0, 1010.0], halt=True)
            rep = evaluate(state, logs)
            self.assertFalse(rep["checks"]["G4_halts"]["pass"])

    def test_negative_expectancy_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            equities = [1000.0 - i for i in range(210)]      # monotone down
            state, logs = write_sleeve(d, trades=210, equities=equities)
            rep = evaluate(state, logs)
            self.assertFalse(rep["checks"]["G2_expectancy"]["pass"])
            self.assertTrue(rep["verdict"].startswith("FAIL"))

    def test_thresholds_are_configurable(self):
        self.assertEqual(DEFAULT_GATES["min_trades"], 200)
        with tempfile.TemporaryDirectory() as d:
            state, logs = write_sleeve(d, trades=10, equities=[1000.0, 1005.0])
            rep = evaluate(state, logs, {"min_trades": 5})
            self.assertTrue(rep["checks"]["G1_trades"]["pass"])

    def test_max_drawdown_helper(self):
        self.assertAlmostEqual(max_drawdown([100, 110, 99, 120]), 1.0 - 99 / 110)
        self.assertEqual(max_drawdown([100]), 0.0)


if __name__ == "__main__":
    unittest.main()
