"""eval/oracle.py — scoring an assessment against ground truth (detection + false positives).

The pure core of the eval harness: deterministic, runs in the suite. The live agent run
(eval/run_eval.py) is manual and not exercised here.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "eval"))

import oracle  # noqa: E402


ORACLE = {"vulns": [
    {"file": "app/db.py", "class": "injection", "vulnerable": True},
    {"file": "app/fetch.py", "class": "ssrf", "vulnerable": True},
    {"file": "app/safe.py", "class": "injection", "vulnerable": False},   # decoy
]}


def _assessment(*findings):
    blocks = []
    for cls, loc, verdict in findings:
        blocks.append(f"## Finding\nClass: {cls}\nLocation: {loc}\n"
                      f"Evidence: e\nVerdict: {verdict}\nSeverity: High\n")
    return "\n".join(blocks)


def test_perfect_run_scores_full_recall_no_false_positives():
    doc = _assessment(("injection", "app/db.py:1", "confirmed"),
                      ("ssrf", "app/fetch.py:9", "confirmed"))
    s = oracle.score(doc, ORACLE)
    assert s["detected"] == 2 and s["missed"] == 0
    assert s["false_positives"] == 0
    assert s["recall"] == 1.0 and s["precision"] == 1.0


def test_a_decoy_confirmed_is_a_false_positive():
    doc = _assessment(("injection", "app/db.py:1", "confirmed"),
                      ("injection", "app/safe.py:5", "confirmed"))   # decoy
    s = oracle.score(doc, ORACLE)
    assert s["detected"] == 1
    assert s["false_positives"] == 1
    assert s["precision"] == 0.5
    assert s["fp_rate"] == 0.5


def test_cannot_verify_is_not_counted_as_a_detection_or_fp():
    doc = _assessment(("injection", "app/db.py:1", "cannot verify — needs auth"))
    s = oracle.score(doc, ORACLE)
    assert s["detected"] == 0 and s["false_positives"] == 0
    assert s["missed"] == 2       # both true vulns unreported


def test_missed_true_vuln_lowers_recall():
    doc = _assessment(("injection", "app/db.py:1", "confirmed"))
    s = oracle.score(doc, ORACLE)
    assert s["detected"] == 1 and s["missed"] == 1
    assert s["recall"] == 0.5
