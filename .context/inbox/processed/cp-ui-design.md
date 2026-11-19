# [Done] Design — cp-ui (design system before code, UI audit after code) — shipped ADR-0022

Status: draft for approval · Date: 2026-11-19 · Prospective ADR-0022

## Intent and why

Products built through the cp-* pipeline come out of it **generic and full of UI bugs**
(the operator's words). Two root causes, at two different points of the pipeline:

1. **Generic** — no visual identity is ever decided. The agent picks colors, fonts and
   layout per screen, at build time, and falls back to the same "Tailwind blue + cards"
   defaults. Today UI exists only as a role inside `cp-analysis-design` (Storyboards,
   Navigation Map, UI Prototype); there is no design system and nothing in `cp-build`
   constrains the visual decisions.
2. **UI bugs** — nothing in the pipeline looks at the interface. A screen with 2:1
   contrast, no keyboard focus, horizontal scroll at 360 px or no empty/error state goes
   to `7-done` unnoticed.

The fix mines the sibling repository `ui-ux-pro-max-skill` (UUPM, MIT, NextLevelBuilder,
v2.15.0 @ `2de1134`): a stdlib-Python BM25 search over curated CSVs (80 styles, 194
product palettes with reasoning rules, 74 font pairings, 130 severity-ranked UX
guidelines, 22 stack guides), a design-system generator (MASTER.md + page overrides,
tokens, `preview.html`), a prioritized pre-delivery checklist, and a Playwright
`design-audit.mjs` that screenshots 6 viewports and runs heuristic checks.

## Decisions made with the operator

- **Each product's identity is chosen by the skill operator**, not by the skill and not
  by a fixed brand. The skill proposes concrete directions; a person picks.
- **Playwright is optional.** The audit must work without it and say plainly when the
  visual check did not run.
- **Findings do not block.** Each confirmed UI finding becomes a `BUG-NNN` card and the
  delivering card moves on (same mechanics as `cp-operation-pentest`).
- **Approach A:** one new skill, `cp-ui`, with two moments (`--design-system`,
  `--audit`), plus small hooks in `cp-build`, `cp-review` and `cp-orchestrator`.

## Goals

- `cp-ui --design-system`: from the product's discovery, propose **2–3 distinct
  directions** (style, palette, font pairing, effects, anti-patterns) each with a
  `preview.html`, let the operator choose/mix/adjust, and record the chosen system in
  `.context/design-system/` with **who chose it and why**.
- `cp-ui --audit`: check the project's front-end against the UX rules in three layers —
  static source checks (always), the product's visual audit (if configured), and an
  evidence checklist answered by the agent — and open one BUG per confirmed finding.
- `cp-build` hands the design system and the top UI rules to the agent when a task
  touches UI, so tokens are used instead of raw values.
- `cp-orchestrator` routes UI requests to `cp-ui` without the user naming it.
- Everything stays inside the repo's rules: stdlib only, `python -S`, offline tests,
  skills never call a model (ADR-0012), never run git.

## Non-goals (v1)

- Generating UI code or components (that stays with `cp-build` and the agent).
- Making Playwright, Node or any MCP server a requirement.
- A coverage ledger (screen × rule) like the pentest's — v1 records findings only.
- Refreshing the vendored UUPM data automatically from upstream.
- Measuring the skill's effect in `eval/` (a later addition).
- Native-app visual audit (iOS/Android emulators). Native stacks get static checks and
  the checklist only.

## Anti-goals (failure even if it "works")

- The skill silently picks the look, or `--record` accepts a design system with no
  named operator.
- The audit reports "passed" for a check that never ran (visual audit not configured,
  checklist item unanswered).
- The backlog floods with noise: hundreds of near-identical BUGs (one per raw hex).
- Overwriting an existing design system without an explicit `--force` and a reason.
- The vendored third-party code runs anything at import time, touches the network, or
  breaks `python -S`.

## Constraints

- Repo rules in `CLAUDE.md` (stdlib, `python -S`, `.context/` only, `RUP_CONTEXT_DIR`
  in tests, exit codes 0/1/4/5, UTF-8 console).
- UUPM is MIT: redistributing its data and scripts verbatim is allowed with the
  copyright notice — add an entry to `NOTICE` and keep its `LICENSE` next to the copy.
- UUPM is downloaded third-party code: **read every vendored script before it is
  committed**, and run it only through our tests.

## Approaches considered

- **A) One skill `cp-ui` with two moments — chosen.** One copy of the data, one place
  to evolve, same shape as `cp-operation-pentest` (packet → agent → `--record`).
- B) Two skills (`cp-design-system`, `cp-ui-audit`). Rejected: both need the same data
  (UX rules, tokens) → duplicated data or a cross-skill dependency the family has never had.
- C) No new skill: design system into `cp-analysis-design`, audit into `cp-review`.
  Rejected: `cp-analysis-design` is a one-document RUP discipline, and `cp-review`'s
  verdict moves/blocks the card — the opposite of "open a BUG and move on".
- Rejected for all: requiring operators to install UUPM separately (extra dependency,
  version drift between operators).

## Design

### Layout

```
skills/cp-ui/
├── SKILL.md
├── scripts/run.py               # our CLI (packet / --record / --design-system / --audit)
├── references/                  # loaded on demand by the agent
│   ├── checklist.md             # the evidence checklist (from UUPM pro-rules + quick-reference)
│   └── static-checks.md         # what each static check means, linked to a UX rule id
├── templates/
│   └── ui-audit.mjs             # optional Playwright audit the product copies (from design-audit.mjs)
└── vendor/uupm/                 # pinned verbatim copy, see "Vendoring"
    ├── LICENSE
    ├── VERSION                  # 2.15.0 @ 2de1134
    ├── data/…  scripts/…
```

Shared logic that other skills need (reading the design system for `cp-build`) goes in
`skills/_shared/uikit.py` (name is the builder's call), not in another skill.

### Vendoring

Copy `src/ui-ux-pro-max/{data,scripts}` (not `cli/`, `gallery/`, `stack/`, `projects/`,
READMEs). Drop what the two moments do not use if it is large and unused — candidates:
`google-fonts.csv` (747 KB) and `phosphor-icons-upstream.json` (824 KB); keep them only
if `design_system.py` needs them. `cp-ui` calls the vendored code **in-process**
(import with an explicit `sys.path` entry) or as a subprocess with `python -S -I` —
builder's call, as long as tests run under `python -S` and nothing touches the network.
A test asserts `VERSION` and `LICENSE` exist and that the vendored search returns a
design system for a fixed query offline.

### Moment 1 — `cp-ui --design-system`

1. `run.py --design-system ["<briefing>"]` prints a packet:
   - what the discovery already says (product type, users, tone, platform) read from
     `.context/`; gaps the agent must ask the operator (one question per message, same
     rules as `cp-discover`);
   - **2–3 candidate directions**, generated by querying the vendored generator with
     deliberately different settings (e.g. low/high `--variance`), each with its
     `preview.html` written to a scratch folder **outside** `.context/` and the path printed;
   - the stack detected from the project (`package.json` deps etc.; never assumed);
   - the rule: present the directions side by side, the operator picks, mixes or edits.
2. The agent shows the previews to the operator and collects the choice.
3. `run.py --design-system --record FILE|- --chosen-by "<name>"` validates and writes:
   - `.context/design-system/MASTER.md` — the chosen system (style, palette with
     semantic roles, typography, spacing/radius/shadow, motion, anti-patterns, stack notes)
     plus a **"Decision"** section: chosen by, date, the alternatives shown, why;
   - `.context/design-system/tokens.json` — machine-readable tokens (UUPM `--tokens` shape);
   - optional `.context/design-system/pages/<page>.md` overrides (`--page`);
   - an ADR entry in `.context/tracking/decisions.md` and a `rup-log.md` line.
   - Missing `--chosen-by` → exit 1. Existing MASTER.md → exit 1 unless `--force
     --reason "<why>"`.

### Moment 2 — `cp-ui --audit`

`run.py --audit` prints a packet; `run.py --audit --record FILE|-` closes it.

**Layer 1 — static checks (always, stdlib).** Scan front-end sources (`.html .css .scss
.jsx .tsx .vue .svelte .astro`, honoring `profile.json` excludes) with regex/heuristics.
Each check is tied to a UUPM UX rule id and its severity. Initial set (builder may
refine the exact patterns):
- raw color literals (`#hex`, `rgb(`, arbitrary Tailwind `[#…]`) outside the token
  files — **only when a design system exists**;
- `<img>` without `alt`; icon-only `<button>`/link without accessible name;
- `outline-none`/`outline: none` with no `focus-visible` replacement in the same rule/class list;
- `user-scalable=no` / `maximum-scale=1`; missing `<html lang>` / viewport meta;
- font sizes below 12 px; emoji used as structural icons in buttons/nav;
- animations with no `prefers-reduced-motion` handling anywhere in the project.

Static hits are **candidates**: the packet lists them and the agent confirms or
dismisses each (with a reason) in the record — same discipline as the pentest's
"cannot verify" never becoming a card.

**Layer 2 — visual audit (optional).** If `.context/ui/profile.json` declares
`"visual_audit": {"command": "...", "report": "path/to/report.json"}`, `--audit` runs
the command in the project (precedent: `cp-test --mutate`, ADR-0016) and reads the
report. We ship `templates/ui-audit.mjs` (adapted from UUPM `design-audit.mjs`, MIT)
that the product copies; it writes a report in **our** JSON schema (findings with
`check`, `severity`, `viewport`, `selector`, `screenshot`). If not configured, or the
command fails, the result says so explicitly. Contrast in this layer is approximate and
labeled as such.

**Layer 3 — evidence checklist (always).** From `references/checklist.md`: loading /
empty / error states, 360 px width, keyboard-only path through the main flow, dark mode
if the system has one, touch targets, form errors next to fields. The agent answers each
item `ok | finding | not-applicable | not-verified` with evidence (screenshot path,
file:line, or reason). `not-verified` is allowed but shown as such.

**Result.** `--record` writes the audit report under `.context/` (e.g.
`.context/ui/audits/<date>.md`) with a header stating **what was verified**:
`static: N files · visual: ran (6 viewports) | not configured | failed · checklist: k/m
answered, j not-verified`. Each confirmed finding → a `BUG-NNN` card via `cards.create`.
**Grouping:** one BUG per (rule × file) — not per occurrence — listing the occurrences
inside; deduplicated against open BUGs created by earlier audits. Severity maps to card
priority (CRITICAL/HIGH → high, MEDIUM → medium, LOW → low). Exit 0 even with findings
(non-blocking); exit 1 only for an invalid record.

### Hooks in existing skills

- **`cp-build`**: when the task touches UI (heuristic: card text/labels or files with
  front-end extensions — builder's call) the packet gains a "UI" section: path to
  `MASTER.md`, the tokens to use, the priority-1–3 rules (a11y, touch, performance), and
  "no raw colors/fonts outside tokens". If there is **no** design system, the packet
  warns and suggests `cp-ui --design-system` (does not block).
- **`cp-review`**: for a UI card, the packet reminds the reviewer to run `cp-ui --audit`
  and to cite the audit report. It does not change how verdicts move the card.
- **`cp-orchestrator`**: two routes in `_shared/router.py` — `ui-design` ("wants a look,
  visual identity, design system, palette, fonts") and `ui-audit` ("wants the UI
  checked: accessibility, responsive, UI bugs") — plus a chain step suggesting
  `--design-system` after discovery for products with a UI.
- `cp-analysis-design`'s User-Interface Designer role: its packet points to
  `.context/design-system/` when it exists. Nothing else changes there.

### Traceability

ADR-0022 in `.context/tracking/decisions.md`; `NOTICE` entry for UUPM (MIT, verbatim
copy of data/scripts, adapted `ui-audit.mjs`); backlog EP/ST/TK cards as with the
pentest; this file moves to `inbox/processed/` with `[Done]` when shipped.

## Settled after the builder check (operator's decisions)

- **Closing a UI BUG:** for BUGs opened by `cp-ui`, the fix evidence is a **re-check**:
  `cp-ui --audit --verify BUG-NNN` re-runs only that BUG's check (static or visual) and
  records pass/fail as evidence; checklist-born BUGs close with an attached screenshot
  path. `cp-debug`/`cp-build` accept this evidence **instead of** a failing regression
  test, only for cards marked as UI findings (e.g. a `source: cp-ui` field). Other bugs
  keep the regression-test rule unchanged.
- **Where the visual audit runs:** a second, ADR-recorded exception to "skills never run
  the project's commands": `--audit` runs the command declared in
  `.context/ui/profile.json` **in the live project tree**, with a timeout (default
  120 s, configurable), and the command only writes a report. The profile gives the
  **URL of an app that is already running** (the operator starts it); the skill never
  starts or stops servers. `templates/ui-audit.mjs` only opens that URL, screenshots
  the viewports and writes the report. Timeout/failure → "visual: failed (<reason>)".

## Settled after the builder check (Claude's calls)

- **Record format / tokens:** the recorded document is the agent-written `MASTER.md` in
  a strict section/field format; our stdlib code parses it, validates it (hex format,
  text-on-surface contrast ≥ 4.5:1 for the declared pairs) and **derives**
  `tokens.json` from it. One source → tokens can never disagree with MASTER.md, and
  "mix/edit" is just editing the document.
- **Distinct directions:** UUPM's `generate()` varies only the style label with
  `--variance` (palette and fonts stay the top match). We add our own **direction
  composer** in `cp-ui` that calls the vendored `search()` and takes different-ranked
  palette and font matches (and/or varied query/colour mode). The vendored code stays
  verbatim. "Distinct" is tested as: no two directions share palette *and* font pair.
- **Dismissed candidates persist** in `.context/ui/dismissals.json` (rule × file ×
  fingerprint, reason, who, date) so false positives do not reappear each audit. A
  finding that returns after its BUG reached `7-done` opens a **new** BUG (regression).
- **Google Fonts:** previews may load fonts from the network when opened (viewing only;
  the skill itself never touches the network). MASTER.md carries a "self-host the
  fonts in production" note.
- Card priority uses the existing MoSCoW mapping (reuse the pentest's
  `SEVERITY_PRIORITY`). `references/checklist.md` is adapted from UUPM's
  `.claude/skills/ui-ux-pro-max/references/` (outside the vendored `src/`) and is
  credited in `NOTICE`.

## Calls made by Claude (not discussed with the operator)

- Skill name `cp-ui`; it is a delivery skill, not part of the `cp-operation-*` family.
- Vendored verbatim (MIT allows it) rather than rewritten as was done for BugHunter.
- BUG grouping per (rule × file) to avoid flooding; severity → priority mapping above.
- Static-check candidates are confirmed by the agent before becoming BUGs.
- Visual audit config lives in `.context/ui/profile.json` (separate from the tests profile).

## Left to the builder

Exact regexes of the static checks; in-process vs subprocess for the vendored code;
which large data files can be dropped; the `cp-build` "touches UI" heuristic; the
report JSON schema field names; task breakdown and order.
