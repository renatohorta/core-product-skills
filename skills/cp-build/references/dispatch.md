# Dispatching a subagent (when the harness has one)

Claude Code has the Task tool, Hermes has `delegate_task`, Codex and OpenCode have
their own. A subagent starts with an empty context and no memory of this session:
everything it needs must be in the dispatch. Adapted from
`obra/superpowers` subagent-driven-development (ADR-0019).

## When it is worth it

- The task is **independent** (no other card is editing the same files) and its
  brief fits in a paragraph plus the card.
- The work is long and mechanical — the plan already says exactly what to write —
  and you would rather keep this context for coordination.
- You want a **reviewer that never saw the author's reasoning**. This is the best
  use by far: the author re-reading their own diff is not a review.

Do not dispatch when the tasks are coupled (two agents editing one module), when
the card is small, or when you cannot state the acceptance check in one line.

## The dispatch prompt (five parts, nothing else)

1. **Where it fits** — one line: which story/epic, which card.
2. **The brief** — the card text and its `Interfaces` / `Constraints` /
   `Review focus`, pasted verbatim or pointed at the card file. Exact names,
   signatures, values and test cases live here, nowhere else.
3. **Decisions from earlier cards** that the brief cannot know (renamed helper,
   interface that changed).
4. **Your rulings** on anything ambiguous you noticed while writing the brief.
5. **The contract**: the acceptance check, the report file, what to return.

Never paste the session history, and never paste the accumulated summaries of
earlier tasks: a fresh agent needs its task, the interfaces it touches and the
global constraints. Everything you paste stays in your context for the rest of
the session and is re-read on every turn — hand over files, not transcripts.

## What to tell it (and what not to)

- "Follow `cp-build`'s TDD rules: the test first, watch it fail, record the red
  evidence, then the minimum code, then `## Verification` with command, result and
  commit."
- "Do not dispatch subagents of your own." A worker that spawns a reviewer
  duplicates the review you are going to run, at full price.
- "Write the delivery to `<path>` and return only: status, the commit, one line of
  test result, and anything you could not do." The report file keeps the detail
  out of your context.
- Do not ask it to re-plan the card, and do not let it run `cp-backlog` moves: the
  card's state is yours to change.

## After it returns

The summary is a **claim**, not evidence: read the diff (or the review package)
and run the acceptance check yourself before you record anything. A subagent that
says "tests pass" without the command and its output has proved nothing — the
same rule `verification-before-completion` applies to you applies to it.

Then review: `cp-review <ID> --package` writes the package; give that file to a
**fresh** reviewer that did not implement the card, and ask for the two verdicts
(`## Spec`, `## Quality`) plus `Cannot verify:` lines.

## Fix loop, and when to stop

One review round finds real issues; fix them and re-review only the changed
hunks. If the same area comes back three times, the card is wrong, not the code:
stop, write a `## Rulings` line saying why, and split or re-plan the card.
Escalate the model (or do it inline yourself) rather than looping a cheap model
against a structural problem.
