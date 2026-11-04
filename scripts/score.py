#!/usr/bin/env python3
"""Deterministic scorer for the India Morning Market Desk.

Usage: python3 scripts/score.py runs/<session-date> [--weights config/weights.json]

Reads each scored child report named in config/weights.json, combines the
signals into a -100..+100 score, and writes score.json into the run folder.
Standard library only.
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
MIN_COVERAGE_PCT = 50.0
PROB_FLOOR, PROB_CEIL = 35.0, 70.0
PROB_SLOPE = 0.30
VALID_SIGNALS = {-2, -1, 0, 1, 2}

DEFAULT_WEIGHTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "config", "weights.json"
)


class ScoreError(Exception):
    """Raised when the run cannot be scored."""


def load_weights(path):
    with open(path, encoding="utf-8") as fh:
        weights = json.load(fh)
    if not isinstance(weights, dict) or not weights:
        raise ScoreError(f"weights file {path} must be a non-empty JSON object")
    for agent, w in weights.items():
        if isinstance(w, bool) or not isinstance(w, (int, float)) or w <= 0:
            raise ScoreError(f"weight for {agent} must be a positive number")
    total = sum(weights.values())
    if not math.isclose(total, 100):
        raise ScoreError(f"weights must total 100, got {total}")
    return weights


def read_report(run_dir, agent):
    """Return (signal, reason). signal is None when the report is excluded."""
    path = os.path.join(run_dir, f"{agent}.json")
    if not os.path.isfile(path):
        return None, "missing"
    try:
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, f"malformed: {exc.__class__.__name__}"
    if not isinstance(report, dict):
        return None, "malformed: not an object"
    if report.get("agent") not in (None, agent):
        return None, f"malformed: agent field is {report.get('agent')!r}"
    status = report.get("status")
    if status == "failed":
        return None, "failed"
    if status not in ("complete", "partial"):
        return None, f"malformed: status {status!r}"
    signal = report.get("signal")
    if signal is None:
        return None, "null signal"
    if isinstance(signal, bool) or not isinstance(signal, (int, float)):
        return None, f"malformed: signal {signal!r}"
    if signal not in VALID_SIGNALS:
        return None, f"malformed: signal {signal!r} outside -2..+2"
    return int(signal), status


def score_run(run_dir, weights):
    if not os.path.isdir(run_dir):
        raise ScoreError(f"run folder not found: {run_dir}")

    total_weight = sum(weights.values())
    contributions, excluded = [], []
    weighted_sum = 0.0
    available = 0.0

    for agent, weight in weights.items():
        signal, reason = read_report(run_dir, agent)
        if signal is None:
            excluded.append({"agent": agent, "weight": weight, "reason": reason})
            continue
        part = weight * signal / 2
        weighted_sum += part
        available += weight
        contributions.append(
            {"agent": agent, "weight": weight, "signal": signal, "status": reason,
             "weighted_points": part}
        )

    coverage_pct = round(available / total_weight * 100, 2)
    if coverage_pct < MIN_COVERAGE_PCT:
        raise ScoreError(
            f"coverage {coverage_pct}% is below the {MIN_COVERAGE_PCT:.0f}% minimum; "
            f"excluded: {', '.join(e['agent'] + ' (' + e['reason'] + ')' for e in excluded)}"
        )

    score = weighted_sum / available * 100
    score = round(score, 2) + 0.0  # normalise -0.0
    for c in contributions:
        c["contribution"] = round(c.pop("weighted_points") / available * 100, 2) + 0.0
    contributions.sort(key=lambda c: (-abs(c["contribution"]), c["agent"]))

    if score > 0:
        direction = "Bullish"
    elif score < 0:
        direction = "Bearish"
    else:
        direction = "Tie"

    prob = 50 + score * PROB_SLOPE
    prob = round(min(PROB_CEIL, max(PROB_FLOOR, prob)), 2)

    return {
        "run_dir": os.path.normpath(run_dir),
        "scored_at_ist": datetime.now(IST).isoformat(timespec="seconds"),
        "score": score,
        "direction": direction,
        "coverage_pct": coverage_pct,
        "estimated_probability_up": prob,
        "probability_label": "heuristic_uncalibrated",
        "formula": "score = sum(weight * signal / 2) / sum(available weights) * 100",
        "contributions": contributions,
        "excluded": excluded,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Score a morning desk run folder.")
    parser.add_argument("run_dir", help="run folder, e.g. runs/2026-11-04")
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS, help="weights JSON file")
    args = parser.parse_args(argv)

    try:
        weights = load_weights(args.weights)
        result = score_run(args.run_dir, weights)
    except (ScoreError, OSError, ValueError) as exc:
        print(f"score.py error: {exc}", file=sys.stderr)
        return 1

    out_path = os.path.join(args.run_dir, "score.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")
    print(
        f"score {result['score']:+.2f} {result['direction']}, coverage "
        f"{result['coverage_pct']}%, p_up {result['estimated_probability_up']} "
        f"(heuristic_uncalibrated) -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
