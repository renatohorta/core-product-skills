# Testing a skill change

> ADR-0019. Adapted from `obra/superpowers` `writing-skills`, which treats a skill
> as code: a change to the prompt is a change to behaviour, and behaviour is
> measured, not asserted.

The suite in `tests/` proves the **contract**: the command exists, the packet has
the artifacts, the exit codes are right, the gate rejects what it should. It
cannot prove the **behaviour**: that an agent reading the skill actually does the
thing. A skill can pass every test and still be ignored.

So a change that is meant to alter behaviour (a rule, a gate, a reference an agent
must follow) needs two kinds of evidence.

## 1. Baseline first (RED)

Before writing the change, run the scenario **without** it:

- Give a fresh agent (a subagent, a new session) the situation, not the answer:
  a card, a broken test, a half-written delivery.
- Record what it did, verbatim: the shortcuts, the exact sentences it used to
  justify skipping the step.
- If it already behaves the way you want, stop: there is nothing to fix, and a
  new rule would only add noise.

## 2. Minimal change (GREEN)

Write the smallest rule that blocks the behaviour you actually observed. Then run
the same scenario again, with the skill present, and compare.

## 3. Close the loopholes (REFACTOR)

Every time an agent negotiates with the rule ("this card is simple, so…"), add the
counter — as a red-flags table row or a rationalization row in the skill, which is
what our own skills already do. Re-run until the behaviour is stable across at
least three fresh runs; if three runs give three interpretations, the wording is
not binding yet.

## Choosing the form

The form must match the failure:

| What went wrong | Right form | Wrong form |
|---|---|---|
| The agent knows the rule and skips it under pressure | prohibition + red-flags table | soft guidance ("prefer…") |
| It complies but the output has the wrong shape | a recipe or a required field | a list of "don't"s |
| It forgets an element it usually produces | a required section in the template | a reminder in the prose |
| The behaviour depends on a condition | a conditional on something observable | an unconditional rule with exceptions |

## What we do not do

- No change to a discipline rule without a baseline run: prose is cheap, behaviour
  change is expensive, and the repo has no eval lab.
- No "compliance" rewrites of tuned tables (red flags, rationalization lists) —
  they were tuned by exactly this process.
- No SKILL.md over 20 KB: the harness truncates a re-attached skill after a
  compaction (`tests/test_skill_contract.py` enforces the budget).

## Result of the first run (2026-11-16)

Six fresh agents, one per arm per rule, each given only the skill text (the
pre-ADR-0019 version from git history vs. the current one) and one task in a
fixture project. Graded by the **real gates**, not by reading the prose.

| Rule | Arm without the rule | Arm with the rule |
|------|----------------------|-------------------|
| `## Verification` in a delivery | no section at all → `--finish` rejected | section present, three fields filled → `--finish` accepted |
| `## Spec` + `## Quality` in a review | neither section → `--record` rejected | `pass` + `approved`, plus a `Cannot verify:` line → accepted |
| `Evidence:` in the root cause | absent → `--diagnose` rejected | 61-character evidence line → accepted |

3/3 rules changed the behaviour they were written for. Two things the run taught:

- **The rule was wrong for a real case.** The agent wrote `Commit: none — the
  workspace is not a git repository …` and the gate rejected it, because the
  regex demanded a SHA. cp-build never runs git, so a project without git can
  never satisfy a SHA-only rule. The gate now accepts `Commit: none — <why>`
  (with the reason) and still rejects a bare `none`. That defect was invisible to
  the contract tests and to a reading of the skill.
- **The new prose transfers.** The with-rule arm also produced `## Rulings` on its
  own, with the `what — why — cost` shape, and a `Cannot verify:` finding in the
  review — neither of which was in the task prompt, only in the skill.

**Caveat**: one run per arm. This measures that the rule is *read and followed*,
not that it is stable across models or pressure; a discipline rule (one an agent
is tempted to skip) needs pressure scenarios and repeats, per the protocol above.

## Cost

A baseline run is one subagent and a few minutes. That is the whole reason the
process is affordable here: it is per change, not per release.
