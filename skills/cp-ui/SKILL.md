---
name: cp-ui
description: "Use when the project needs a front-end design system chosen and recorded (colors, typography, style), or when its UI must be checked against that design system."
---

# cp-ui — design system for the front end

The agent running this skill is the LLM (ADR-0012); the skill never calls a model, never
runs git. It composes three accessible design directions offline, the **operator** picks,
mixes or edits, and the result becomes `.context/design-system/MASTER.md` + `tokens.json`.

## Design system

1. **Get the packet** (read-only, works without authorization):
   `python scripts/run.py --design-system ["<briefing>"] [--product NAME] [--out DIR]`.
   It shows the discovery (`.context/docs/**/cp-discover*.md`, else "none — ask the
   operator"), the detected stack (package.json, pubspec.yaml, Package.swift, composer.json,
   else "unknown — ask"), three directions each with a summary, an HTML preview path (a temp
   dir, or `--out`) and a MASTER.md draft. Without a briefing the query comes from the discovery.
2. **Present the directions side by side. The operator picks, mixes or edits** — never choose
   for them. Open the previews for them.
3. **Write ONE final MASTER.md** (`## Style`, `## Colors`, `## Typography`, `## Decision`
   with `Chosen by:`, `Alternatives shown:`, `Why:` filled).
4. **Record it**: `python scripts/run.py --design-system --record FILE|- --chosen-by NAME`.
   `--chosen-by` must equal the document's `Chosen by:` (case-insensitive). It validates
   (required color roles, WCAG AA contrast, fonts, decision), writes `MASTER.md` and
   `tokens.json`, appends `## Design system — <product> (<date>)` to
   `.context/tracking/decisions.md` (no ADR number: those are hand-assigned) and logs it.
5. **Page-specific system**: add `--page NAME` — writes `design-system/pages/<name>.md`
   only; MASTER.md and tokens.json are untouched.
6. **Replacing** an existing file needs `--force --reason "..."`; the reason goes into the
   decisions entry. `--force` alone exits 1.

Format of MASTER.md, allowed roles, contrast pairs and how to present: `references/design-system.md`.

## Commands

- `--design-system ["<briefing>"] [--product NAME] [--out DIR]` — packet.
- `--design-system --record FILE|- --chosen-by NAME [--page PAGE] [--force --reason R]` — record.
- `--context-dir D` — another `.context/` (default: auto-detect or `RUP_CONTEXT_DIR`).

Exit codes: 0 ok · 1 usage / invalid document / `--chosen-by` mismatch / overwrite refused ·
4 `.context/` not writable · 5 not authorized (`--record` only; the packet is read-only).

## Audit

Added in a later task.
