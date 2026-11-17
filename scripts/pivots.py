#!/usr/bin/env python3
"""Classic floor pivots from the previous session's high, low and close.

Usage: python3 scripts/pivots.py --high H --low L --close C [--label Nifty]

Prints JSON with P, R1-R3 and S1-S3, rounded to 2 decimals, plus the inputs,
so the report can show where the levels came from. Standard library only.
"""

import argparse
import json
import sys


def pivots(high, low, close):
    if not (high >= low and low <= close <= high):
        raise ValueError("need low <= close <= high")
    p = (high + low + close) / 3
    levels = {
        "P": p,
        "R1": 2 * p - low,
        "S1": 2 * p - high,
        "R2": p + (high - low),
        "S2": p - (high - low),
        "R3": high + 2 * (p - low),
        "S3": low - 2 * (high - p),
    }
    return {k: round(v, 2) for k, v in levels.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Classic floor pivots")
    ap.add_argument("--high", type=float, required=True)
    ap.add_argument("--low", type=float, required=True)
    ap.add_argument("--close", type=float, required=True)
    ap.add_argument("--label", default="")
    a = ap.parse_args(argv)
    try:
        out = pivots(a.high, a.low, a.close)
    except ValueError as exc:
        print(f"pivots.py error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"label": a.label, "inputs": {"high": a.high, "low": a.low, "close": a.close},
                      "method": "classic floor pivots, calculated", "levels": out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
