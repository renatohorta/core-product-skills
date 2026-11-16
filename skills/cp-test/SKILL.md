---
name: cp-test
description: "Use when the user asks for a test plan, test strategy, test cases, test evaluation, mutation testing, or whether the tests are worth anything: the RUP Test Discipline plus the test-value audit (static audit, mutation, triage, audit closure)."
   cat doc.md | python scripts/run.py --record - --phase Elaboration --input briefing.md
   ```

   The recorder checks that every required `## <Artifact>` section exists (if not,
   it lists the missing ones, writes nothing and exits `1` — add them and record
   again) and writes `.context/docs/<NN-phase>/cp-test.md` with a provenance header,
   plus a row in `.context/tracking/rup-log.md`.

   **Evidence is mandatory**: run the suite (and coverage) yourself and put the
   command, commit SHA, duration and result of every execution in the Test Log.
   Never write a number you did not measure.

## Test-value audit — do the tests catch bugs? (ADR-0016, ADR-0018)

Coverage says which lines ran, not whether a test would notice a wrong line.
When the question is the value of the tests, run the audit protocol:

```bash
python scripts/run.py "<briefing>" --audit [--files a.py b.py] [--workers N] [--budget 2h]
```

It prints steps A0–A8 with the exact commands: profile the project
(`.context/tests/profile.json`), baseline, inventory, static audit, choose the
modules by risk, mutate, triage the survivors, act (cards/CRs), record. The tools:

| Command | Does |
|---------|------|
| `--profile-template` | Prints the `profile.json` to fill (suite command, isolation per worker) |
| `--static-audit [DIR]` | Tests with no assertion, trivial asserts, no project call, self-mocks → `tests/static-audit.md` |
| `--mutants --files F… [--verbose]` | Counts/lists the mutants (read-only) |
| `--mutate --files F… [--lines F:A-B] [--workers N] [--budget 2h] [--fresh] [--rerun-survivors]` | Runs the mutants in disposable copies, in parallel, resumable → `tests/mutation/results.jsonl` |
| `--mutation-status` | Progress of a long run |
| `--mutation-report` | `tests/mutation/report.md` (score per module, worst first) + `triage.md` rows for the survivors |
| `--triage-check` | Fails until every survivor is classified with its reason and action |
| `--audit-closure` | Which **source modules** the audit never reached → `tests/closure.md`; exits `1` while a module is silent (ADR-0018) |
| `--waive PATH\|GLOB --reason "…"` | Declares a surface out of the audit — a decision with its reason, not a silent omission |
| `--show-mutant F:IDX` | Diff of one mutant |

A mutation score covers only the modules that were mutated. `--audit-closure`
answers the other half — every source module (`profile.source_extensions`, minus
tests and `audit_exclude`) needs a verdict: **audited**, **waived** with its reason,
**blocked** (mutants ran, none was graded) or **never audited**. While any module
is silent the command exits `1` and `closure.md` states, in the report's own words,
that the audit did not reach full coverage. A score over a subset is never a
statement about the code it did not touch.

The mutation run executes the project's own test command (from the profile) in
copies of the project: the original is never written, git is never run, and the
run refuses to continue if the code under test changed. Python mutants are
generated here; other languages use their ecosystem tool with the same protocol.
Rules: `references/audit.md` (protocol, profile, runner pitfalls) and
`references/triage.md` (survivor classes).

## CLI contract

| Argument | Meaning |
|----------|---------|
| `briefing` (positional) | Business demand / context for the discipline |
| `--input <file>` | Read the briefing from a file (alternative to positional) |
| `--phase {Inception,Elaboration,Construction,Transition}` | RUP phase (default: Elaboration) |
| `--context-dir <dir>` | The `.context/` (default: `$RUP_CONTEXT_DIR`, else the nearest up to the git root) |
| `--record <file\|->` | Validate your document and write it to `.context/` |

The audit options are listed above. Exit codes: `0` success · `1` usage error /
missing artifacts / failed baseline / incomplete triage · `4` `.context/` not
writable · `5` `.context/` not authorized. Standard library only — no LLM key.

## Reference

Agent → artifact mapping and missions: `references/agents.md`. Audit:
`references/audit.md`, `references/triage.md`.
