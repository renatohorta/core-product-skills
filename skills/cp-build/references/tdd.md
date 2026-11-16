# TDD delivery — format and test rules

## Test rules

- Write the test before the code and run it: it must fail first (red).
- Tie every test to a criterion: put the ID (`ST-001/AC-1`, or `st_001_ac_1`) in
  the test name, its docstring or a comment directly above it. A bug's test
  references the bug ID (`BUG-007`) or a criterion of its story.
- A task's `Covers` criteria must each have at least one test.
- Rejected tests: `assert True`, constant comparisons (`assert 1 == 1`), no
  assertion at all, or a test that never calls project code.
- Every listed test needs red evidence: the failing output you saw.
- JS/TS tests are checked by pattern; other languages only by name (a warning).
- Green is not enough: mutate the lines you changed and show the tests catch a
  wrong line (below). `--finish` warns when `## Mutation` is missing.

## Delivery document

Required sections: `What was done`, `Files changed`, `Tests`, `Red evidence`,
`Verification`. Recommended: `Mutation` and `Rulings` (shown to the reviewer; their
absence is a warning).

`## Verification` is the green run itself, on a commit anyone can check out
(ADR-0019) — red evidence proves the test failed first, this proves it passes now:

````markdown
## Verification

Command: python -m pytest -q
Result: exit 0, 42 passed in 3.1s
Commit: 9f2c1ab
````

`--finish` rejects a delivery without those three lines. Never write a command or
a result you did not run. When the project is not a git repository (or the change
is not committed yet), the honest value is `Commit: none — <why>`; the skill never
runs git, so it cannot invent the SHA for you.

`## Rulings` records every place where you deviated from the card or the plan and
why — one line each, `Ruling: <what you decided> — <why> — <what it costs if wrong>`.
A deviation nobody recorded is a surprise for the reviewer.
Each test is one line `- <path>::<test> — covers <ID>[, <ID>]`; red evidence is
one `### <path>::<test>` block with a fenced output per test.

````markdown
## What was done

Booking endpoint that returns the booked slot.

## Files changed

- app/booking.py
- tests/test_booking.py

## Tests

- tests/test_booking.py::test_book_slot_st_001_ac_1 — covers ST-001/AC-1

## Red evidence

### tests/test_booking.py::test_book_slot_st_001_ac_1

```
E   ImportError: cannot import name 'book' from 'app.booking'
```
````

## Task brief

`--start` prints the card, so the brief is the card: `Description`, `Target files`,
`## Covers`, plus `## Interfaces`, `## Constraints` and `## Review focus` when they
exist (cp-backlog `references/cards.md`). Read them before writing the first test:
exact names, signatures and values come from there, not from memory.

## Mutation of the changed lines

With `.context/tests/profile.json` in place (cp-test `--audit`, step A0), run the
mutants of the lines the task changed:

```bash
python <skills>/cp-test/scripts/run.py --mutate --lines app/booking.py:10-42 --fresh
python <skills>/cp-test/scripts/run.py --mutation-status
```

Then write the section. Every survivor needs a test that kills it (re-run with
`--rerun-survivors`) or the reason it cannot matter (cp-test `references/triage.md`):

````markdown
## Mutation

app/booking.py:10-42 — 14 mutants, 13 killed, 1 survived (93%).

- #22 line 31 `return None` — equivalent: the return value of `log_slot` is not used by any caller.
````
