# eval — does cp-operation-pentest help, and does it stay precise?

This harness measures what the skill asserts but a test cannot: when an agent audits code
**with** the skill's references versus **without** them, does it find more real holes
(recall) without crying wolf (precision / false-positive rate)? The skills-on/off delta is
the signal.

It lives **outside `skills/`** on purpose: the live path calls a model (the `claude` CLI),
which the skills themselves never do (ADR-0012), and which cannot run in the stdlib suite.

## Layout

- `cases/<name>/` — a fixture codebase with planted vulnerabilities **and decoys**
  (code that looks vulnerable but is safe — that is how false positives are measured),
  plus `oracle.json` (the ground truth: which `(file, class)` are vulnerable, which are decoys).
- `oracle.py` — scores an assessment against the oracle, reusing the skill's own parser
  (`_shared/pentest.parse_findings`), so eval scores exactly what the skill records.
- `run_eval.py` — obtains an assessment per condition, scores it, prints the table, writes JSONL.
- `cases/<name>/mock_<condition>.md` — canned assessments for `--mock` (deterministic, no model).

## Run

```bash
# Deterministic, no model — scores the canned assessments (this is what the suite exercises):
python eval/run_eval.py --mock

# Live — call the agent for real (needs the `claude` CLI authed):
python eval/run_eval.py --conditions skill,baseline --model claude-opus-4-8 --out eval/results.jsonl
```

Conditions:
- **skill** — the prompt is the skill's own work packet (its class list + references) plus the source.
- **baseline** — the same agent and model, a generic "find vulnerabilities" instruction, no references.

Metrics per condition: `recall` (true vulns detected / all true vulns), `precision`
(true positives / all confirmed), `fp_rate` (= 1 − precision), and the raw counts. A skill
that lifts recall while holding precision is earning its keep; one that lifts recall by
confirming decoys is not.

## Adding a case

1. Drop a small codebase under `eval/cases/<name>/` with real planted vulns and at least one
   decoy per class you care about.
2. Write `eval/cases/<name>/oracle.json` (`{"vulns": [{"file","class","vulnerable"}]}`).
3. Optionally add `mock_skill.md` / `mock_baseline.md` to keep a deterministic check.
4. `python eval/run_eval.py --case <name> --mock`.

The pure scoring core is covered by `tests/test_eval_oracle.py` and `tests/test_eval_run_mock.py`.
The live agent run is manual.
