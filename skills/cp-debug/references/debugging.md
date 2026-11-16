# Debugging protocol

Two rules hold the whole protocol: **no fix before a root cause**, and **a cause
you cannot point at is a guess**. The four phases come from `obra/superpowers`
(ADR-0019); the mutation step is ours (ADR-0016).

## Phase 1 — Investigate the cause

- **Read the error.** The whole stack trace, the line, the exit code. Do not skim
  past warnings: they are frequently the answer.
- **Reproduce reliably.** Exact steps and inputs, every time. If it does not
  reproduce, you have no bug yet — gather data, do not guess.
- **Check what changed.** Recent commits, new dependency, config, environment
  (`git log`/`git diff` are yours to run — the skill never runs git for you).
- **Instrument the boundaries** when the system has more than one component (CI →
  build → sign, API → service → database): one line at each boundary showing what
  enters and what leaves, plus the config that reaches it. Run once, see which
  boundary loses or corrupts the value, then investigate that component only.
  Guessing at three layers at once is how a two-hour bug becomes two days.
- **Walk the value back.** Where does the bad value originate? Who called with it?
  Keep going up until you reach the decision or the missing check.

## Phase 2 — Look for the pattern

Is this one instance of a class? Search for the same shape elsewhere (the same
unchecked assumption, the same missing guard, the same query without a limit).
One bug found by hand usually means siblings exist.

## Phase 3 — One hypothesis at a time

State the hypothesis, then prove it with the smallest experiment: a log line, a
debugger stop, a narrower test. A hypothesis that survives three "should be" is a
hypothesis you have not tested. When an experiment contradicts you, drop the
hypothesis — do not stack a second fix on top.

## Phase 4 — Fix the cause

- Change the decision, not the symptom's location. Minimal edit.
- The regression test (step 2 of the SKILL) goes green and the rest of the suite
  stays green.
- Prove the test guards the fix: mutate the fixed lines
  (`cp-test --mutate --lines <file>:<a>-<b>`). The mutants that undo the fix (the
  flipped condition, the removed check) must die; a survivor there means the
  regression test does not pin the bug. Report it in the delivery's `## Mutation`.
- If the same mistake can occur elsewhere, add the test or open another bug.

## Recording it

`## Root cause` states what is wrong, why it happens, and what proves it:

```
## Root cause

The slot set is never checked before insert: `book()` inserts first and only
then looks for an existing row.

Evidence: with DEBUG=1 the INSERT log line carries the same slot id twice, and
the check at booking.py:41 never runs before it; a sequential re-run passes,
which rules out the transaction.
```

The `Evidence:` line is mandatory (`--diagnose` rejects a document without it):
it is what separates a diagnosis from a narrative you would have written anyway.
