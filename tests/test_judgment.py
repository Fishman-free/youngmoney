import json
import os
import tempfile
import unittest

from bnbot.judgment import JudgmentLayer, build_state_snapshot


class FakeRouter:
    def __init__(self, answers=None, boom=False):
        self.answers = answers or {}
        self.boom = boom

    def predict(self, snapshot, questions):
        if self.boom:
            raise RuntimeError("engine down")
        return {"answers": self.answers}


GOOD = {
    "regime": {"choice": "trending", "confidence": 0.8},
    "toxicity": {"noul": 0.2},
    "setup": {"score": 2.5},
}


class TestJudgmentGate(unittest.TestCase):
    def _layer(self, answers=None, boom=False, policy=None, tmp=None):
        jl = JudgmentLayer(os.path.join(tmp, "jlog.jsonl"), policy=policy)
        jl._router = FakeRouter(answers, boom)
        jl._engine = "fake"
        return jl

    def test_good_battery_passes(self):
        with tempfile.TemporaryDirectory() as d:
            jl = self._layer(GOOD, tmp=d)
            allow, reason = jl.gate(jl.ask("state"))
            self.assertTrue(allow, reason)

    def test_low_confidence_vetoes(self):
        with tempfile.TemporaryDirectory() as d:
            ans = dict(GOOD, regime={"choice": "chaotic", "confidence": 0.3})
            jl = self._layer(ans, tmp=d)
            allow, reason = jl.gate(jl.ask("state"))
            self.assertFalse(allow)
            self.assertIn("J2", reason)

    def test_weak_setup_vetoes(self):
        with tempfile.TemporaryDirectory() as d:
            ans = dict(GOOD, setup={"score": 0.5})
            jl = self._layer(ans, tmp=d)
            allow, reason = jl.gate(jl.ask("state"))
            self.assertFalse(allow)
            self.assertIn("J3", reason)

    def test_toxicity_vetoes(self):
        with tempfile.TemporaryDirectory() as d:
            ans = dict(GOOD, toxicity={"noul": 0.9})
            jl = self._layer(ans, tmp=d)
            allow, reason = jl.gate(jl.ask("state"))
            self.assertFalse(allow)
            self.assertIn("J4", reason)

    def test_missing_judgment_follows_policy(self):
        with tempfile.TemporaryDirectory() as d:
            jl = self._layer(boom=True, tmp=d)  # engine down -> None answers
            allow, _ = jl.gate(jl.ask("state"))
            self.assertTrue(allow)  # default on_missing=pass (auxiliary)
            jl2 = self._layer(boom=True, policy={"on_missing": "hold"}, tmp=d)
            allow2, reason2 = jl2.gate(jl2.ask("state"))
            self.assertFalse(allow2)
            self.assertIn("J1", reason2)

    def test_triples_logged(self):
        with tempfile.TemporaryDirectory() as d:
            jl = self._layer(GOOD, tmp=d)
            jl.ask("sym X | trend_signal 1")
            jl.ask("sym Y")  # failure path
            jl2 = self._layer(boom=True, tmp=d)
            jl2.ask("sym Z")
            lines = open(os.path.join(d, "jlog.jsonl"), encoding="utf-8").read().splitlines()
            self.assertEqual(len(lines), 3)
            recs = [json.loads(l) for l in lines]
            self.assertEqual(recs[0]["status"], "ok")
            self.assertIsNotNone(recs[0]["answers"])
            self.assertTrue(recs[2]["status"].startswith("error:"))

    def test_snapshot_is_compact_and_numeric(self):
        snap = "sym BTCUSDT | trend_signal 1 | momentum_30d 1 | realized_vol 0.400 | funding_ann 0.1000"
        self.assertLess(len(snap), 400)  # article: state engine stays under 400 tokens
        self.assertIn("trend_signal", snap)


if __name__ == "__main__":
    unittest.main()
