---
name: cp-discover
description: "Use when starting anything new — a product, a feature or an epic — or when the idea is still fuzzy: a discovery conversation (problem, users, goals, non-goals, anti-goals, constraints, open questions) confirmed by the user and recorded in .context/."
---

# cp-discover — talk first, then write

Discovery is a conversation, not a form. You, the agent, interview the user and
only then write the document. The result (`cp-discover.md`, Inception) is
embedded first in the packet of every later RUP skill.

## When to use

Before building anything new: a product, a feature, an epic. Skip it for a bug
(`cp-debug`) or a change that is already specified.

## Conversation rules

The order of the conversation and its gates are in
`references/brainstorming.md` (ADR-0019): look before asking, echo the request in
about 200 words, lay out the approaches **before** writing, play back in chunks,
size the work, and do not build before approval. The short version:

- One question per message. Never a list of questions.
- Build each question on the last answer; say why you ask when it is not obvious.
- Do not guess to fill a gap: ask, or put it in Open questions.
- Lay out the two or three real approaches in a message of their own, with what
  each trades off and your recommendation, before writing the document.
- Play back each part in your own words (200-300 words) and ask what is wrong or missing.
- Write and record only after the user confirms the playback.

## Steps

1. Print the packet: `python scripts/run.py "<idea>"` (phase defaults to Inception).
2. Hold the conversation, section by section (`references/discovery.md`).
3. Write one document with a `## <Section>` heading per artifact.
4. Record it (mandatory): `python scripts/run.py --record FILE|- "<idea>"`.

The recorder checks every heading, then writes
`.context/docs/01-inception/cp-discover.md` and logs it. Needs the RUP standard
authorized in `.context/` (exit 5 otherwise: see `cp-context`).

Exit codes: 0 ok · 1 usage/invalid document · 4 `.context/` not writable ·
5 not authorized.
