"""eval/run_eval.py --mock: the harness wiring + scoring, deterministic (no model)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "eval"))

import run_eval  # noqa: E402


def test_mock_run_scores_both_conditions(tmp_path):
    out = tmp_path / "results.jsonl"
    rows = run_eval.run("sample", ["skill", "baseline"], mock=True, claude="claude",
                        model="", out=str(out))
    by = {r["condition"]: r for r in rows}

    # the skill condition: finds both true vulns, rejects the decoy (false positive) → precise
    assert by["skill"]["recall"] == 1.0
    assert by["skill"]["false_positives"] == 0
    assert by["skill"]["fp_rate"] == 0.0

    # the baseline: misses ssrf and confirms the decoy → lower recall, a false positive
    assert by["baseline"]["recall"] == 0.5
    assert by["baseline"]["false_positives"] == 1
    assert by["baseline"]["fp_rate"] == 0.5

    assert out.is_file() and out.read_text(encoding="utf-8").strip()
