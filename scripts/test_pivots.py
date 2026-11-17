#!/usr/bin/env python3
"""Tests for scripts/pivots.py. Run: python3 scripts/test_pivots.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pivots import pivots  # noqa: E402


class PivotTests(unittest.TestCase):
    def test_known_values(self):
        # H 110, L 90, C 100 -> P 100, R1 110, S1 90, R2 120, S2 80, R3 130, S3 70
        self.assertEqual(pivots(110, 90, 100),
                         {"P": 100, "R1": 110, "S1": 90, "R2": 120, "S2": 80, "R3": 130, "S3": 70})

    def test_ordering(self):
        lv = pivots(25337.60, 25172.10, 25291.10)
        self.assertTrue(lv["S3"] < lv["S2"] < lv["S1"] < lv["P"] < lv["R1"] < lv["R2"] < lv["R3"])

    def test_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            pivots(90, 110, 100)
        with self.assertRaises(ValueError):
            pivots(110, 90, 120)


if __name__ == "__main__":
    unittest.main(verbosity=2)
