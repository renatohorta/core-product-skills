---
name: cp-build
description: "Use when implementing a kanban task or bug test-first: start it (branch, packet, TDD rules) and finish it with a delivery whose tests are checked for value and evidence."
---

# cp-build — start and finish a task

Takes a task (or bug) card from `.context/kanban/` to `4-review` with tests
that prove its acceptance criteria. Needs the RUP standard authorized in
`.context/` (exit 5 otherwise: see `cp-context`). The skill never runs your
tests or git; it checks what you declare.

## Steps

1. Start: `python scripts/run.py --start TK-001`. The card moves to `3-doing`,
   gets a `branch`, and the skill prints the packet: card, parent story with
   its criteria, earlier RUP artifacts, TDD rules and the exact `--finish` command.
2. Create the branch, then per criterion: write the test first and run it, see it
   fail (save the output), implement, run it again (green), commit.
3. Write the delivery document (format in `references/tdd.md`). It needs
   `## Verification` — `Command:`, `Result:` and `Commit:` of the green run — and
   a `## Rulings` line for every deviation (`what — why — what it costs`).
4. Finish: `python scripts/run.py --finish TK-001 --delivery FILE|-`. Problems
   are printed under `Delivery rejected:` and nothing is written (exit 1): fix
   and rerun. On success the card gets `## Delivery` and moves to `4-review`.

## References

`references/tdd.md` — delivery format, the verification gate, the task brief.
`references/dispatch.md` — handing a card to a subagent (when the harness has one)
and reviewing its result.

## Commands

- `--start ID` — task/bug in `1-backlog`, `2-todo` or `blocked`.
- `--status [ID]` — read-only: what is in `3-doing`, with delivery, verification and
  mutation state, and the next command (the resume map after a compaction).
- `--finish ID --delivery FILE|- [--project-root DIR]` — card in `3-doing`;
  project root defaults to the parent of `.context/`. Bugs also get `## Fix`
  and `## Regression test`, and need a `## Root cause` first (`cp-debug --diagnose`).
- `--context-dir D` — another `.context/` (default: auto-detect or `RUP_CONTEXT_DIR`).

Exit codes: 0 ok · 1 usage/rejected delivery · 4 not writable · 5 not authorized.
