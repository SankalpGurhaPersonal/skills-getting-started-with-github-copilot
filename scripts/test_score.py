#!/usr/bin/env python3
"""Tests for scripts/score.py. Run: python3 scripts/test_score.py

Uses mock reports in temporary folders only. No live market data.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCORE = os.path.join(HERE, "score.py")
WEIGHTS_PATH = os.path.join(ROOT, "config", "weights.json")

with open(WEIGHTS_PATH, encoding="utf-8") as fh:
    WEIGHTS = json.load(fh)


def report(agent, signal, status="complete"):
    return {
        "agent": agent,
        "generated_at_ist": "2026-11-04T08:20:00+05:30",
        "status": status,
        "signal": signal,
        "signal_confidence": "medium",
        "headline": "mock report for tests",
        "evidence": [],
        "india_read_through": "",
        "sectors_positive": [],
        "sectors_negative": [],
        "risks": [],
        "missing_data": [],
    }


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.run_dir = tempfile.mkdtemp(prefix="mock-run-")

    def tearDown(self):
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def write(self, agent, signal, status="complete", raw=None):
        path = os.path.join(self.run_dir, f"{agent}.json")
        with open(path, "w", encoding="utf-8") as fh:
            if raw is not None:
                fh.write(raw)
            else:
                json.dump(report(agent, signal, status), fh)

    def write_all(self, signals):
        for agent in WEIGHTS:
            self.write(agent, signals.get(agent, 0))

    def run_score(self):
        proc = subprocess.run(
            [sys.executable, SCORE, self.run_dir, "--weights", WEIGHTS_PATH],
            capture_output=True, text=True,
        )
        result = None
        out = os.path.join(self.run_dir, "score.json")
        if os.path.exists(out):
            with open(out, encoding="utf-8") as fh:
                result = json.load(fh)
        return proc, result

    def assertScored(self):
        proc, result = self.run_score()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIsNotNone(result)
        return result

    # --- required cases -------------------------------------------------

    def test_weights_total_100(self):
        self.assertEqual(len(WEIGHTS), 11)
        self.assertEqual(sum(WEIGHTS.values()), 100)

    def test_all_bullish(self):
        self.write_all({a: 2 for a in WEIGHTS})
        r = self.assertScored()
        self.assertEqual(r["score"], 100)
        self.assertEqual(r["direction"], "Bullish")
        self.assertEqual(r["coverage_pct"], 100)
        self.assertEqual(r["estimated_probability_up"], 70)  # 50 + 30, at the cap
        self.assertEqual(r["probability_label"], "heuristic_uncalibrated")

    def test_all_bearish(self):
        self.write_all({a: -2 for a in WEIGHTS})
        r = self.assertScored()
        self.assertEqual(r["score"], -100)
        self.assertEqual(r["direction"], "Bearish")
        self.assertEqual(r["estimated_probability_up"], 35)  # 50 - 30, floored

    def test_mixed_signals(self):
        signals = {
            "gift-nifty-tracker": 1, "us-markets": 2, "asia-markets": -1,
            "europe-markets": 0, "fx-rates": -2, "commodities": 1,
            "institutional-flows": -1, "derivatives-positioning": 1,
            "india-technicals": 0, "india-news-policy": 0, "india-earnings": -1,
        }
        self.write_all(signals)
        r = self.assertScored()
        # 20*.5 + 15*1 - 10*.5 - 7*1 + 5*.5 - 12*.5 + 13*.5 - 2*.5 = 15.0
        self.assertEqual(r["score"], 15.0)
        self.assertEqual(r["direction"], "Bullish")
        self.assertEqual(r["estimated_probability_up"], 54.5)
        contribs = [abs(c["contribution"]) for c in r["contributions"]]
        self.assertEqual(contribs, sorted(contribs, reverse=True))
        self.assertEqual(r["contributions"][0]["agent"], "us-markets")
        self.assertAlmostEqual(sum(c["contribution"] for c in r["contributions"]), 15.0)

    def test_missing_report(self):
        self.write_all({a: 1 for a in WEIGHTS})
        os.remove(os.path.join(self.run_dir, "us-markets.json"))
        r = self.assertScored()
        self.assertEqual(r["coverage_pct"], 85)
        self.assertEqual(r["score"], 50)  # renormalised over available weight
        self.assertIn({"agent": "us-markets", "weight": 15, "reason": "missing"}, r["excluded"])

    def test_failed_report(self):
        self.write_all({a: -1 for a in WEIGHTS})
        self.write("gift-nifty-tracker", None, status="failed")
        r = self.assertScored()
        self.assertEqual(r["coverage_pct"], 80)
        self.assertEqual(r["score"], -50)
        reasons = {e["agent"]: e["reason"] for e in r["excluded"]}
        self.assertEqual(reasons["gift-nifty-tracker"], "failed")

    def test_coverage_below_50(self):
        # Only gift-nifty (20) + us-markets (15) + asia (10) = 45%
        for agent in ("gift-nifty-tracker", "us-markets", "asia-markets"):
            self.write(agent, 2)
        proc, result = self.run_score()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("below the 50% minimum", proc.stderr)
        self.assertIsNone(result)

    def test_exact_tie(self):
        signals = {a: 0 for a in WEIGHTS}
        signals["gift-nifty-tracker"] = 1   # +10
        signals["fx-rates"] = -2            # -7
        signals["commodities"] = -1         # -2.5
        signals["europe-markets"] = -1      # -1.5
        signals["india-earnings"] = 1       # +1    -> net 0
        self.write_all(signals)
        r = self.assertScored()
        self.assertEqual(r["score"], 0)
        self.assertEqual(r["direction"], "Tie")
        self.assertEqual(r["estimated_probability_up"], 50)

    # --- extra robustness ----------------------------------------------

    def test_malformed_and_null_signal_excluded(self):
        self.write_all({a: 2 for a in WEIGHTS})
        self.write("india-technicals", None, raw="{not json")
        self.write("commodities", None)  # status complete but null signal
        self.write("india-earnings", 5)  # out of range
        r = self.assertScored()
        reasons = {e["agent"]: e["reason"] for e in r["excluded"]}
        self.assertTrue(reasons["india-technicals"].startswith("malformed"))
        self.assertEqual(reasons["commodities"], "null signal")
        self.assertTrue(reasons["india-earnings"].startswith("malformed"))
        self.assertEqual(r["coverage_pct"], 83)
        self.assertEqual(r["score"], 100)

    def test_unweighted_reports_ignored(self):
        self.write_all({a: 0 for a in WEIGHTS})
        self.write("sector-rotation", None)
        self.write("macro-calendar", None)
        r = self.assertScored()
        agents = {c["agent"] for c in r["contributions"]} | {e["agent"] for e in r["excluded"]}
        self.assertEqual(agents, set(WEIGHTS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
