#!/usr/bin/env python3
"""
run_eval.py — does cp-operation-pentest actually help, and does it stay precise?

For each case (a fixture codebase with planted vulns + decoys) and each condition
(skill = audit with the skill's references; baseline = the same agent without them), it
obtains an assessment, scores it against the oracle (eval/oracle.py), and reports
detection (recall) and false positives (precision / fp_rate). The skills-on/off delta is
the point: a skill that raises recall while holding precision is earning its keep.

  python eval/run_eval.py --mock                      # deterministic: score the canned
                                                       # assessments (no model, CI-safe)
  python eval/run_eval.py --conditions skill          # live: call the agent for one condition
  python eval/run_eval.py --case sample --claude claude --model claude-opus-4-8

The live path calls the `claude` CLI headlessly; it needs that CLI authed and is run by
hand, never in the stdlib suite. `--mock` reads eval/cases/<case>/mock_<condition>.md so the
wiring and the scoring are testable without a model.

Pure standard library.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
for _p in (_HERE, _REPO / "skills"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import oracle  # noqa: E402

CONDITIONS = ("skill", "baseline")
PENTEST_RUN = _REPO / "skills" / "cp-operation-pentest" / "scripts" / "run.py"


def case_dir(case: str) -> Path:
    return _HERE / "cases" / case


def mock_assessment(case: str, condition: str) -> str:
    return (case_dir(case) / f"mock_{condition}.md").read_text(encoding="utf-8")


def _packet(case: str) -> str:
    """The skill's work packet over the case (the audit instructions + references map)."""
    r = subprocess.run([sys.executable, str(PENTEST_RUN), "audit this project"],
                       capture_output=True, text=True,
                       env={"RUP_CONTEXT_DIR": str(case_dir(case) / ".context")},
                       cwd=str(case_dir(case)))
    return r.stdout


def live_assessment(case: str, condition: str, claude: str, model: str) -> str:
    """Call the agent headlessly and return its assessment document.

    skill  : prompt = the skill's packet + 'write the assessment'.
    baseline: prompt = a generic 'find vulnerabilities' instruction, no references.
    """
    files = "\n\n".join(f"=== {p.relative_to(case_dir(case))} ===\n{p.read_text(encoding='utf-8')}"
                        for p in sorted(case_dir(case).rglob("*.py")))
    if condition == "skill":
        prompt = (_packet(case) + "\n\nHere is the source. Produce ONLY the assessment "
                  "document described above.\n\n" + files)
    else:
        prompt = ("You are a security auditor. Find vulnerabilities in the source below. "
                  "For each, write a block:\n## Finding\nClass: <kind>\nLocation: file:line\n"
                  "Evidence: ...\nVerdict: confirmed|cannot verify|false positive\n"
                  "Severity: ...\n\n" + files)
    cmd = [claude, "-p", prompt]
    if model:
        cmd += ["--model", model]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout


def run(case, conditions, *, mock, claude, model, out):
    data = oracle.load_oracle(case_dir(case) / "oracle.json")
    rows = []
    for cond in conditions:
        text = (mock_assessment(case, cond) if mock
                else live_assessment(case, cond, claude, model))
        s = oracle.score(text, data)
        s.update({"case": case, "condition": cond})
        rows.append(s)
    if out:
        Path(out).write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return rows


def _print_table(rows):
    print(f"{'condition':<10} {'recall':>7} {'precision':>10} {'fp_rate':>8} "
          f"{'detected':>9} {'missed':>7} {'FP':>4}")
    for r in rows:
        print(f"{r['condition']:<10} {r['recall']:>7} {r['precision']:>10} {r['fp_rate']:>8} "
              f"{r['detected']:>9} {r['missed']:>7} {r['false_positives']:>4}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Eval cp-operation-pentest: detection vs false positives")
    p.add_argument("--case", default="sample")
    p.add_argument("--conditions", default="skill,baseline",
                   help="comma list of: " + ", ".join(CONDITIONS))
    p.add_argument("--mock", action="store_true", help="score canned assessments, no model")
    p.add_argument("--claude", default="claude", help="the claude CLI (live mode)")
    p.add_argument("--model", default="", help="model id held constant across conditions")
    p.add_argument("--out", default="", help="write results as JSONL here")
    args = p.parse_args(argv)
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    rows = run(args.case, conditions, mock=args.mock, claude=args.claude,
               model=args.model, out=args.out)
    _print_table(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
