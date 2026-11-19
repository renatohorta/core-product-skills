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

Design system:
- `--design-system ["<briefing>"] [--product NAME] [--out DIR]` — packet (read-only).
- `--design-system --record FILE|- --chosen-by NAME [--page PAGE] [--force --reason R]` — record.

Audit:
- `--audit ["<scope>"] [--path SUB] [--visual]` — packet (`--visual` runs the profile's visual command).
- `--audit --record FILE|- [--by NAME] [--path SUB]` — record: BUGs, dismissals, report.
- `--audit --verify BUG-NNN [--visual] [--evidence PATH]` — re-check one UI BUG.

Everywhere: `--context-dir D` — another `.context/` (default: auto-detect or `RUP_CONTEXT_DIR`).

Exit codes: 0 ok · 1 usage / invalid document / `--chosen-by` mismatch / overwrite refused /
verify failed · 4 `.context/` not writable · 5 not authorized (`--record` and the audit packet;
the design-system packet is read-only).

## Audit

Static UI check of the code, plus a checklist the agent verifies. The packet needs the
project to be authorized (exit 5 otherwise).

1. **Packet**: `python scripts/run.py --audit ["<scope>"] [--path SUB] [--visual]`. It writes only `.context/ui/visual-last.json`; the visual command runs only with `--visual`. It shows
   the honest header (static files scanned, the visual status, checklist counts),
   the regex candidates (minus those dismissed earlier, with how many were hidden), the seven
   checklist items and the document format. `0 files` means nothing was scanned, not "clean".
   Files to skip: `exclude` list in `.context/ui/profile.json`.
2. **Confirm or dismiss each candidate** by reading the code. What each rule means and its
   usual false positives: `references/static-checks.md`. Verdicts: `confirmed`,
   `dismissed — <reason>`, `cannot verify — <why>`; only `confirmed` opens a BUG.
3. **Answer the checklist** (`references/checklist.md`) with evidence you actually gathered;
   without evidence answer `not-verified`. A `finding` needs its own `## Finding` block with
   `Rule: checklist:<item-id>`.
4. **Record**: `python scripts/run.py --audit --record FILE|- [--by NAME] [--path SUB]` (same `--path` as the packet; a dismissal must match a real candidate by line or by snippet in its evidence, else exit 1; candidates you leave unaddressed are listed as not verified and counted in the header). One BUG per
   (rule, file) listing every occurrence, priority from the highest severity; if an open
   cp-ui BUG exists for that key it prints `already open: BUG-NNN` instead (a BUG already in
   `7-done` is a regression and opens a new one). Dismissals go to `.context/ui/dismissals.json`
   (`--by`, default `agent`); the report goes to `.context/ui/audits/<date>.md` (`-2`, `-3`
   on the same day), its first line stating what was and was not verified. Exit 0 even with
   findings; 1 on an invalid document (unknown rule/item, missing field, a `finding` without
   its block).

### Verify a fix

`--audit --verify BUG-NNN [--visual] [--evidence PATH]` re-checks only that BUG's rule on its file (the `ui_key` of the card). Static rules re-scan (dismissed candidates do not count); visual rules need `--visual` too (the product's command runs again); checklist rules need `--evidence PATH`, an existing file (relative to the project root or absolute). It writes `.context/ui/verify/BUG-NNN.json` (`bug`, `rule`, `result`, `at`, `evidence`), exit 0 on pass and 1 on fail. `cp-build --finish` accepts a passing record made after `--start` instead of a regression test, only for BUGs opened by cp-ui.

Order for a cp-ui BUG: `cp-build --start BUG` → `cp-debug --diagnose BUG --doc -` (`## Root cause` with an `Evidence:` line) → fix → `cp-ui --audit --verify BUG` → `cp-build --finish BUG`.

Trust model: verify re-checks what the scanner, the visual audit or the evidence can show (a file the scanner cannot read, an excluded one, a missing design system for `raw-color`, or a viewport the report never exercised is a `fail`, never a pass); records are not tamper-proof, so reviewers read them (cp-review shows `Re-checked by cp-ui`). Timestamps are UTC with offset; a record counts only if strictly later than `cp-build --start`, for the same BUG and rule. When a BUG is re-checked, the tests listed in the delivery need not name the BUG ID (listed tests are still validated). A confirmed static finding must match a scanner candidate at `--record`; what the scanner cannot see is filed as `checklist:<id>`.

### Visual audit (optional)

Off by default (`visual: not configured`). To enable it in your product:

1. Copy `templates/ui-audit.mjs` to `scripts/ui-audit.mjs` and run
   `npm i -D playwright && npx playwright install chromium`.
2. Start your app yourself (cp-ui never starts or stops servers).
3. Add to `.context/ui/profile.json`:
   `{"visual_audit": {"command": "node scripts/ui-audit.mjs --url http://localhost:5173 --out .ui-audit", "report": ".ui-audit/report.json", "timeout_s": 120}}`
   (`report` is relative to the project root; `timeout_s` defaults to 120).

Opt-in: only `--audit --visual` runs the declared command (the packet prints the exact command and cwd first; it never starts servers). Without `--visual` the status is `skipped (--visual not given)` when `visual_audit` is configured (`not configured` otherwise) and that is stored too, invalidating any older run. The report path must stay inside the project (`failed (report path outside project)`). With `--visual` the packet runs the command once (deleting any old report first) and lists each finding as a
candidate (`Rule: visual:<check>`, `Location: <viewport> <selector>`, evidence with the
screenshot path); the run is saved to `.context/ui/visual-last.json`. The record never
re-runs the command: its header reads that file when its scope (`--path`) matches the packet's.
Header (the report's second line is `Visual run at: <time>`): `visual: ran (k viewports)` (only from that file) · `visual: not configured` (no
`visual_audit`/`command`) · `visual: failed (<reason>)` — `timeout after 120s`, `exit code 2: <last stderr line>`, `visual run not persisted`,
`report not found: <path>`, `invalid report: <detail>`, `command not found: <name>`, or
`no visual run for this scope — run the packet first`. A confirmed `visual:` finding opens a
BUG like any other, grouped by rule and viewport (`visual:<check>::<viewport>`); visual
candidates you leave unaddressed are listed under `## Not verified`.
