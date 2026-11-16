# Review checklist and verdict

Review the card against the packet, then the code. Be specific: a finding names a file, a test or a criterion.

## Two verdicts, not one (ADR-0019)

A card can satisfy its criteria and still be code the project does not want to
own — or be beautiful code that does the wrong thing. Record both, separately:

- `## Spec` — does the delivery do what the card asks, criterion by criterion?
  `pass` or `gap`.
- `## Quality` — is this code the project wants to own (naming, boundaries, dead
  code, error paths, test hygiene)? `approved` or `changes`.

`## Verdict` `approved` requires `pass` + `approved`; anything else is
`changes requested`, and the first finding becomes the move reason.

**Cannot verify.** What you could not check without the builder's context — a
flow you cannot reproduce, a migration that needs a database — is a finding
starting with `- Cannot verify:`. It is an open question for the next reviewer,
never a pass. Never write a verdict you would have to hedge.

## Checklist

1. **Criteria.** Every criterion the card must cover (task `Covers`, or the bug ID) has a delivery test that really asserts it.
2. **Files.** Changes stay inside `Target files`. Each file outside needs a reason; each target not changed needs one too.
3. **Tests.** The packet's `Test checks` line is `OK`. Read the tests: real assertions, calling project code, red evidence plausible.
4. **Mutation.** The delivery's `## Mutation` covers the changed lines; every survivor has a test that kills it or a reason (cp-test `references/triage.md`). Missing → ask for it on logic that matters.
5. **Adversarial review.** For non-trivial cards, an agent without the builder's context reviews the diff against the story (concurrency, retries, transactions/migrations, unindexed queries, wrong counts, error paths). Each real finding starts with a test that reproduces it.
6. **Traceability.** The card links to its story and epic; the work matches the story's intent and the epic's scope.
7. **Quality.** Minimal change, no dead code, no unrelated refactors; the full suite is green.
8. **Integration.** Merge the branch yourself, then run the full suite **on the
   merged result** — a green branch plus a green main does not prove the merge is
   green. Only then move the card through `5-testing` / `6-staging` to `7-done`.
   Do the work in a worktree if the project allows it, so the branch you review is
   the branch that lands.

## Verdict document

```
## Verdict

approved            <- or: changes requested

## Spec

pass                <- or: gap

## Quality

approved            <- or: changes

## Findings

- <first finding: becomes the move reason when changes are requested>
- <more findings; write `none` when approved with nothing to report>
```

- The first non-empty line of `## Verdict` is exactly `approved` or `changes requested`.
- `approved` moves the card to `5-testing`; `changes requested` moves it back to `3-doing` with the first finding as reason.
- Reviews accumulate in the card's `## Review` section, newest last.
