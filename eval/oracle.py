#!/usr/bin/env python3
"""
oracle.py — score a pentest assessment against ground truth.

Given the agent's assessment document and an oracle (which (file, class) are truly
vulnerable, and which look vulnerable but are decoys), compute detection (recall) and
false positives (precision / FP-rate). The scorer reuses the skill's own parser
(`_shared.pentest.parse_findings`), so eval measures exactly what the skill records.

Pure standard library.
"""
import json
from pathlib import Path

# _shared/ lives under skills/ at the repo root (eval/ is a sibling of skills/).
_REPO = Path(__file__).resolve().parent.parent
import sys
for _p in (_REPO / "skills",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from _shared import pentest  # noqa: E402


def _norm_file(loc: str) -> str:
    return loc.split(":", 1)[0].replace("\\", "/").strip("/")


def _key(file: str, cls: str):
    return (_norm_file(file), (cls or "").strip().lower())


def load_oracle(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def score(assessment_text: str, oracle: dict) -> dict:
    """Detection and false-positive metrics for one assessment.

    - detected: distinct true vulns a confirmed finding matched (by file × class)
    - missed: true vulns no confirmed finding matched
    - false_positives: confirmed findings that hit a decoy or an unknown (file × class)
    - precision = TP / (TP + FP); recall = detected / true vulns; fp_rate = 1 - precision
    """
    vulns = oracle.get("vulns", [])
    true_keys = {_key(v["file"], v["class"]) for v in vulns if v.get("vulnerable")}
    decoy_keys = {_key(v["file"], v["class"]) for v in vulns if not v.get("vulnerable")}

    findings, _errors = pentest.parse_findings(assessment_text)
    confirmed = [f for f in findings if f.confirmed]

    detected, false_positives = set(), 0
    for f in confirmed:
        k = _key(f.location, f.vuln_class)
        if k in true_keys:
            detected.add(k)
        else:
            # a decoy, or a (file × class) that is not a known true vuln
            false_positives += 1
    tp = len(detected)
    missed = len(true_keys) - tp
    precision = tp / (tp + false_positives) if (tp + false_positives) else 1.0
    recall = tp / len(true_keys) if true_keys else 1.0
    return {
        "confirmed": len(confirmed),
        "detected": tp,
        "missed": missed,
        "false_positives": false_positives,
        "true_vulns": len(true_keys),
        "decoys": len(decoy_keys),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "fp_rate": round(1 - precision, 4),
    }
