# cp-ui Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new `cp-ui` skill that makes each product decide its visual identity before code (`--design-system`) and audits the UI after code (`--audit`, one BUG per confirmed finding), plus hooks in cp-build / cp-review / cp-orchestrator.

**Architecture:** Same shape as `cp-operation-pentest`: `run.py` prints a packet, the agent works, `--record` validates and writes `.context/`. Pure logic lives in `skills/_shared/uikit.py` (design system: parse/validate/tokens) and `skills/_shared/uicheck.py` (static checks, findings, BUG grouping, dismissals, verify records). UUPM (MIT) is vendored verbatim under `skills/cp-ui/vendor/uupm/` and wrapped by our own direction composer.

**Tech Stack:** Python 3 stdlib only, pytest (suite runs under `python -S`), optional Node/Playwright only in the product (template `ui-audit.mjs`).

**Spec:** `.context/inbox/initiatives/cp-ui-design.md`

## Global Constraints

- Stdlib only; tests pass under `python -S`; no network, no model calls (ADR-0012); skills never run git.
- Tests set `RUP_CONTEXT_DIR` to a temp dir (`ctx_env` fixture); never write into this repo's `.context/`.
- Exit codes: 0 ok · 1 usage/invalid · 4 not writable · 5 needs authorization.
- Vendored UUPM = v2.15.0 @ `2de1134`, verbatim, with its `LICENSE`; credited in `NOTICE`.
- Card priority from severity via the pentest mapping: critical/high → Must, medium → Should, low → Could.
- Contrast threshold for declared text pairs: **4.5:1**.
- Visual audit command timeout: default **120 s**, overridable by `timeout_s` in `.context/ui/profile.json`.
- BUGs created by cp-ui carry card meta `source: cp-ui` (the existing `source` field).
- `.context/` paths: `design-system/MASTER.md`, `design-system/tokens.json`, `design-system/pages/<page>.md`, `ui/profile.json`, `ui/dismissals.json`, `ui/audits/<YYYY-MM-DD>.md`, `ui/verify/<BUG-ID>.json`.

## Review Focus

1. **Project with no front-end files** (pure backend) → `--audit` must say "static: 0 files" and not crash or invent findings. (Task 5)
2. **Re-running `--audit --record` with the same findings** → no duplicate BUGs while the earlier BUG is open. (Task 6)
3. **Visual audit command hangs or exits non-zero** → result says `visual: failed (<reason>)`, record still succeeds. (Task 7)
4. **`--design-system --record` when a MASTER.md already exists** → exit 1 unless `--force --reason`; the old file is untouched on refusal. (Task 4)
5. **A cp-ui BUG delivered with neither tests nor a passing verify record** → `cp-build --finish` rejects it; a non-cp-ui BUG with only a verify record is still rejected. (Task 8)

---

### Task 1: Vendor UUPM and prove it runs offline under `python -S`

**Files:**
- Create: `skills/cp-ui/vendor/uupm/{LICENSE,VERSION}`, `skills/cp-ui/vendor/uupm/scripts/{core.py,design_system.py,preview.py,reasoning_contract.py}`, `skills/cp-ui/vendor/uupm/data/**` (all `*.csv`, `stacks/*.csv`, `catalog-summary.json`, `data-provenance.json`)
- Create: `skills/cp-ui/scripts/uupm.py` (loader)
- Modify: `NOTICE`
- Test: `tests/test_ui_vendor.py`

**Interfaces:**
- Produces: `uupm.load()` → module namespace with `core.search(query, domain, max_results)` and `design_system.DesignSystemGenerator().generate(query, project_name, variance=None) -> dict` (keys incl. `colors` with roles from `SEMANTIC_COLOR_ENTRIES`, `typography` with `heading`/`body`/`google_fonts_url`, `style`, `color_mode`). `uupm.VENDOR_DIR: Path`.

- [ ] **Step 1: Read every vendored `.py` file before copying** (downloaded third-party code). Confirm no `subprocess`, `socket`, `urllib.request`, `eval`/`exec`, or writes at import time. Do not copy `validate_data.py`, `search.py`, `tests/`. Exclude `phosphor-icons-upstream.json` and `google-font-licenses.json` (only `validate_data.py` reads them).
- [ ] **Step 2: Write the failing tests**

```python
def test_vendor_has_license_and_pinned_version():
    v = SKILLS_DIR / "cp-ui" / "vendor" / "uupm"
    assert (v / "LICENSE").read_text().startswith("MIT License")
    assert (v / "VERSION").read_text().strip() == "2.15.0 @ 2de1134"

def test_vendored_generator_runs_offline(python_cmd):
    # subprocess with python -S -I; asserts a palette and fonts come back
    out = run_py(python_cmd, "-S", "-I", "-c", LOAD_AND_GENERATE % "legal saas dashboard")
    data = json.loads(out)
    assert data["colors"]["primary"].startswith("#")
    assert data["typography"]["heading"]
```
- [ ] **Step 3: Run** `.venv/bin/python -m pytest tests/test_ui_vendor.py -v` → FAIL (missing files).
- [ ] **Step 4: Copy the files; write `uupm.py`** that inserts `VENDOR_DIR/"scripts"` into `sys.path` once and imports `core`, `design_system`, `preview`. Add the UUPM block to `NOTICE` (author NextLevelBuilder, MIT, verbatim data/scripts; adapted `ui-audit.mjs` and `references/checklist.md`).
- [ ] **Step 5: Run** the test → PASS; full suite → PASS.
- [ ] **Step 6: Commit** `feat(cp-ui): vendor ui-ux-pro-max v2.15.0 (MIT)`.

### Task 2: `_shared/uikit.py` — MASTER.md parse, validate, tokens

**Files:**
- Create: `skills/_shared/uikit.py`
- Test: `tests/test_uikit.py`

**Interfaces:**
- Produces:
  - `REQUIRED_COLORS = ("primary","on_primary","background","foreground")`, `CONTRAST_PAIRS = (("foreground","background"),("on_primary","primary"),("card_foreground","card"),("muted_foreground","background"))` (a pair is checked only when both roles are present), `MIN_CONTRAST = 4.5`
  - `parse_master(text: str) -> tuple[dict, list[str]]` → `({"style": str, "colors": {role: hex}, "typography": {"heading": str, "body": str}, "decision": {"chosen_by": str, "alternatives": str, "why": str}}, errors)`
  - `contrast_ratio(a: str, b: str) -> float` (WCAG relative luminance)
  - `tokens_from_system(system: dict) -> dict` → DTCG: `{"color": {role: {"$type":"color","$value":hex}}, "font": {"heading": {"$type":"fontFamily","$value":...}, "body": {...}}}`
  - `ds_dir(context_dir) -> Path`, `load_design_system(context_dir) -> dict | None` (parsed MASTER.md or None)

MASTER.md format (the agent writes it; the packet in Task 4 prints it):

```markdown
# Design system — <product>
## Style
<one paragraph>
## Colors
- primary: #1D4ED8
- on_primary: #FFFFFF
...
## Typography
- heading: Fraunces
- body: Inter
## Spacing
## Motion
## Anti-patterns
## Decision
Chosen by: <name>
Alternatives shown: <A, B, C>
Why: <reason>
```

- [ ] **Step 1: Failing tests** — `test_parse_master_reads_roles_and_fonts`, `test_parse_master_reports_missing_required_role` (no `foreground` → error mentions `foreground`), `test_parse_master_rejects_bad_hex` (`#12345` → error), `test_low_contrast_pair_is_an_error` (`foreground #999999` on `background #FFFFFF` → error naming the pair and the ratio), `test_contrast_ratio_black_white_is_21` (`== pytest.approx(21.0)`), `test_tokens_from_system_shape` (`tokens["color"]["primary"]["$value"] == "#1D4ED8"`), `test_missing_decision_chosen_by_is_an_error`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** with the existing `_shared.discipline` section helpers where they fit (`- key: value` lines under `##` headings).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(uikit): parse and validate the design system, derive tokens`.

### Task 3: Direction composer + previews

**Files:**
- Create: `skills/cp-ui/scripts/directions.py`
- Test: `tests/test_ui_directions.py`

**Interfaces:**
- Consumes: `uupm.load()` (Task 1).
- Produces:
  - `compose(query: str, project: str, n: int = 3) -> list[dict]` — n UUPM-shaped design-system dicts, each with an added `"id"` (`"A"`, `"B"`, `"C"`).
  - `write_previews(directions: list[dict], out_dir: Path) -> list[Path]` — `out_dir/direction-<id>.html` via vendored `preview.format_preview_html`.
  - `to_master(direction: dict, product: str) -> str` — a MASTER.md draft in Task 2's format with an empty `## Decision`.

Approach: base = `generate(query, project, variance=v)` for v in (2, 6, 9); then replace `colors` with the k-th ranked `core.search(query, "color", max_results=5)` row and `typography` with the k-th `core.search(query, "typography", max_results=5)` row (k = 0,1,2), mapping row columns to the same keys `generate()` uses (`design_system.py` lines ~560–600). If fewer rows exist, return fewer directions (min 1).

- [ ] **Step 1: Failing tests** — `test_compose_returns_distinct_directions` (for `"legal saas dashboard"`: ≥2 directions and no two share both `colors["primary"]` and `typography["heading"]`), `test_write_previews_creates_one_html_each` (files exist, contain `<html`), `test_to_master_round_trips_through_parse_master` (`to_master(d)` with a filled `## Decision` parses with `errors == []`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(cp-ui): direction composer with previews`.

### Task 4: `cp-ui --design-system` packet and record

**Files:**
- Create: `skills/cp-ui/scripts/run.py`, `skills/cp-ui/SKILL.md` (design-system section; audit section added in Task 6)
- Test: `tests/test_ui_design_system.py`

**Interfaces:**
- Consumes: `directions.compose/write_previews/to_master`, `uikit.parse_master/tokens_from_system/ds_dir`, `context.ensure_writable`, `context.append_event`.
- Produces CLI:
  - `run.py --design-system ["<briefing>"] [--out DIR] [--context-dir D]` — packet: discovery found in `.context/docs/**/cp-discover*.md` (or "none — ask the operator"), detected stack (`package.json` deps / `pubspec.yaml` / `Package.swift` / `composer.json`, else "unknown — ask"), each direction's summary + preview path (default out dir: a temp dir, never `.context/`), each direction's MASTER.md draft, the record command, the rule "present side by side; the operator picks, mixes or edits".
  - `run.py --design-system --record FILE|- --chosen-by NAME [--page PAGE] [--force --reason R]` — validates via `parse_master`; requires `--chosen-by` and that it equals `## Decision` `Chosen by:`; writes `MASTER.md` (or `pages/<PAGE>.md`), `tokens.json`; appends ADR-style entry `Design system — <product>` to `.context/tracking/decisions.md` and a `rup-log.md` event.

- [ ] **Step 1: Failing tests** — `test_packet_lists_directions_and_preview_paths`, `test_packet_says_unknown_stack_when_none_detected`, `test_record_writes_master_and_tokens`, `test_record_without_chosen_by_exits_1`, `test_record_refuses_overwrite_without_force` (exit 1; MASTER.md bytes unchanged), `test_record_force_requires_reason`, `test_record_appends_decision_entry`, `test_record_without_authorization_exits_5`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (copy the `_shared` bootstrap and `setup_console` from the pentest `run.py`). **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(cp-ui): --design-system packet and record`.

### Task 5: `_shared/uicheck.py` — static checks

**Files:**
- Create: `skills/_shared/uicheck.py`
- Test: `tests/test_uicheck_static.py`

**Interfaces:**
- Produces:
  - `UI_EXTENSIONS = (".html",".css",".scss",".jsx",".tsx",".vue",".svelte",".astro")`
  - `@dataclass Candidate(rule: str, file: str, line: int, snippet: str, severity: str)`
  - `CHECKS: dict[str, dict]` — rule id → `{"severity", "ux_rule", "summary"}`; ids: `raw-color`, `img-no-alt`, `icon-button-no-name`, `outline-removed`, `zoom-disabled`, `missing-lang`, `missing-viewport`, `tiny-font`, `emoji-icon`, `no-reduced-motion`
  - `scan(project_root: Path, exclude: list[str], design_system: dict | None) -> tuple[list[Candidate], int]` → (candidates, files scanned). `raw-color` runs only when `design_system` is not None, and skips files listed in `design_system.get("token_files", [])` plus any file named `tokens.*`/`theme.*`. `no-reduced-motion` is project-level (one candidate, `file="(project)"`) when animations exist and no `prefers-reduced-motion`/`useReducedMotion` appears anywhere.

- [ ] **Step 1: Failing tests** — one positive and one negative fixture per rule (e.g. `<img src="a.png">` → `img-no-alt`; `<img alt="" src=…>` → none; `className="outline-none focus-visible:ring-2"` → none; `outline-none` alone → `outline-removed`), plus `test_scan_backend_only_project_scans_zero_files` (Review Focus 1: only `.py` files → `([], 0)`), `test_raw_color_skipped_without_design_system`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** with line-based regexes; reuse `auditclosure._matches` for excludes. **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(uicheck): static UI checks`.

### Task 6: `cp-ui --audit` packet and record (findings → grouped BUGs, dismissals, report)

**Files:**
- Modify: `skills/_shared/uicheck.py`, `skills/cp-ui/scripts/run.py`, `skills/cp-ui/SKILL.md`
- Create: `skills/cp-ui/references/{checklist.md,static-checks.md}`
- Test: `tests/test_ui_audit.py`

**Interfaces:**
- Consumes: `uicheck.scan`, `uikit.load_design_system`, `cards.create/load_all`, `SEVERITY_PRIORITY` (copy the pentest dict into `uicheck`).
- Produces:
  - Audit document format the agent writes:
    ```
    ## Finding
    Rule: img-no-alt | checklist:<item-id> | visual:<check>
    Location: src/pages/Home.tsx:12
    Evidence: <text or screenshot path>
    Verdict: confirmed | dismissed — <reason>
    Severity: High
    ## Checklist
    - states-loading-empty-error: ok | finding | not-applicable | not-verified — <evidence>
    ```
  - `parse_audit(text) -> tuple[list[Finding], dict[str, tuple[str, str]], list[str]]` (findings, checklist answers, errors); `Finding(rule, location, evidence, verdict, severity)`.
  - `group_key(f: Finding) -> str` = `f"{rule}::{file}"` (file = location before `:`).
  - `record_dismissals(context_dir, findings, actor)` / `load_dismissals(context_dir) -> set[str]` — key `rule::file::fingerprint` where fingerprint = sha1 of the trimmed snippet/evidence[:200].
  - `open_bugs_by_key(context_dir) -> dict[str, Card]` — cp-ui BUGs (meta `source: cp-ui`) not in `7-done`, keyed by `group_key` stored in card meta `ui_key`.
  - BUG card: title `[ui] <rule> in <file>`, sections `## Symptom` (rule summary + ux rule), `## Reproduction` (all occurrences `file:line — evidence`), priority via severity, `source="cp-ui"`, then `cards.set_meta(card, "ui_key", key)`.
  - Report `.context/ui/audits/<date>.md` with first line `Verified — static: N files · visual: <ran (k viewports) | not configured | failed (<reason>)> · checklist: a/m answered, j not-verified`.
- CLI: `run.py --audit ["<scope>"] [--path SUB]` (packet: header line as above with visual "pending", candidates minus dismissed, checklist items from `references/checklist.md`, document format, record command); `run.py --audit --record FILE|-` (exit 0 even with findings; 1 on invalid document).

- [ ] **Step 1: Failing tests** — `test_confirmed_findings_group_per_rule_and_file` (3 `img-no-alt` in one file → 1 BUG listing 3 occurrences), `test_rerecord_does_not_duplicate_open_bug` (Review Focus 2), `test_finding_after_bug_done_opens_new_bug`, `test_dismissed_candidate_not_shown_next_packet`, `test_report_header_states_what_was_verified` (`"visual: not configured"`, `"j not-verified"`), `test_checklist_finding_opens_bug`, `test_record_exits_0_with_findings`, `test_invalid_document_exits_1_and_creates_nothing`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**; write `references/checklist.md` (item ids: `states-loading-empty-error`, `width-360`, `keyboard-main-flow`, `dark-mode`, `touch-targets`, `form-errors-inline`, `focus-visible`; adapted from UUPM `pro-rules.md`/`quick-reference.md`) and `references/static-checks.md` (one entry per `CHECKS` id). **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(cp-ui): --audit with grouped BUGs, dismissals and honest report`.

### Task 7: Optional visual audit layer + `ui-audit.mjs` template

**Files:**
- Modify: `skills/_shared/uicheck.py`, `skills/cp-ui/scripts/run.py`
- Create: `skills/cp-ui/templates/ui-audit.mjs`
- Test: `tests/test_ui_visual.py`

**Interfaces:**
- Profile `.context/ui/profile.json`: `{"visual_audit": {"command": "node scripts/ui-audit.mjs --url http://localhost:5173 --out .ui-audit", "report": ".ui-audit/report.json", "timeout_s": 120}}`.
- Report schema (what `ui-audit.mjs` writes): `{"viewports": ["mobile-360", ...], "findings": [{"check": str, "severity": str, "viewport": str, "selector": str, "detail": str, "screenshot": str}]}`.
- Produces: `run_visual(project_root: Path, profile: dict) -> tuple[str, list[dict]]` → (status line `"ran (k viewports)" | "not configured" | "failed (<reason>)"`, findings). Runs `subprocess.run(shlex.split(command), cwd=project_root, timeout=timeout_s)`; it never starts servers. `--audit` (packet) calls it and lists visual findings as candidates (`Rule: visual:<check>`).

- [ ] **Step 1: Failing tests** (fake command = a tiny Python script via `python_cmd` writing a report) — `test_visual_not_configured`, `test_visual_ran_reads_findings`, `test_visual_timeout_reports_failed` (script sleeps; `timeout_s: 1`; Review Focus 3), `test_visual_nonzero_exit_reports_failed`, `test_visual_missing_report_reports_failed`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**; write `ui-audit.mjs` adapted from UUPM `stack/scripts/design-audit.mjs` (keep its 6 viewports and checks; remove `--file` mode; output our report schema; header comment credits UUPM MIT). **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(cp-ui): optional visual audit via the product's command`.

### Task 8: `--verify BUG-NNN` and cp-build accepting it for cp-ui BUGs

**Files:**
- Modify: `skills/_shared/uicheck.py`, `skills/cp-ui/scripts/run.py`, `skills/_shared/testcheck.py:263-296`, `skills/cp-build/scripts/run.py:139-171`
- Test: `tests/test_ui_verify.py`

**Interfaces:**
- Produces:
  - `run.py --audit --verify BUG-NNN [--evidence PATH]` — re-runs only that BUG's rule on its file (static → `scan` filtered; visual → `run_visual` filtered by check; checklist → requires `--evidence` pointing to an existing file). Writes `.context/ui/verify/BUG-NNN.json` = `{"bug": id, "rule": r, "result": "pass"|"fail", "at": iso, "evidence": str}`; prints the result; exit 0 on pass, 1 on fail.
  - `uicheck.verify_record(context_dir, bug_id) -> dict | None`.
  - `testcheck.check_delivery(..., ui_verified: bool = False)` — when `task.type == "bug"` and `ui_verified`, drop the "lists no tests" and "No test references the bug ID" problems; all other checks unchanged.
  - `cp-build start`: for a bug with `source: cp-ui`, set meta `ui_verify_after` = now (ISO). `cp-build finish`: `ui_verified` is true only when `source == "cp-ui"`, `verify_record` exists, `result == "pass"` and `at >= ui_verify_after` (a verify from before the start is stale).

- [ ] **Step 1: Failing tests** — `test_verify_pass_writes_record`, `test_verify_fail_exits_1`, `test_checklist_bug_verify_needs_evidence_file`, `test_finish_accepts_cp_ui_bug_with_passing_verify_and_no_tests`, `test_finish_rejects_cp_ui_bug_without_verify_or_tests` (Review Focus 5), `test_finish_rejects_non_cp_ui_bug_with_only_verify` (Review Focus 5), `test_stale_verify_before_start_is_ignored`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; run `tests/test_rup_build.py` → still PASS.
- [ ] **Step 5: Commit** `feat(cp-ui): --verify re-check closes UI bugs`.

### Task 9: Hooks — cp-build packet, cp-review, cp-analysis-design, router

**Files:**
- Modify: `skills/cp-build/scripts/run.py` (`start`), `skills/cp-review/scripts/run.py` (`packet`), `skills/cp-analysis-design/scripts/run.py` (UI designer role text), `skills/_shared/router.py` (`routes`, `CHAINS`), `skills/cp-orchestrator/SKILL.md`
- Test: `tests/test_ui_hooks.py`, extend `tests/test_router.py`

**Interfaces:**
- Consumes: `uikit.load_design_system`, `uicheck.UI_EXTENSIONS`.
- Produces: `uikit.touches_ui(card) -> bool` — true when any `## Target files` line ends with a `UI_EXTENSIONS` suffix or the title/body contains one of `("ui", "screen", "page", "tela", "component", "layout", "css")` as a word.
  - cp-build `start` prints `## UI` when `touches_ui`: with a design system → MASTER.md path, color and font tokens, the priority-1–3 rules (a11y, touch, performance — one line each), "no raw colors/fonts outside tokens"; without → `⚠️ no design system: run cp-ui --design-system first (not blocking)`.
  - cp-review packet prints, for `touches_ui` cards, `## UI audit` with the `cp-ui --audit` command and the newest `.context/ui/audits/*.md` header line (or "none yet").
  - Router: `("ui-design", "wants a look, visual identity, design system, palette, fonts", ..., cmd("cp-ui", "--design-system", "<request>"))`, `("ui-audit", "wants the UI checked: accessibility, responsive, UI bugs", ..., cmd("cp-ui", "--audit"))`; chain `("Product with a UI", "discover → ui --design-system [operator picks] → requirements → backlog → build (UI section) → ui --audit → BUGs → debug/build → review")`.

- [ ] **Step 1: Failing tests** — `test_build_start_prints_ui_section_with_tokens`, `test_build_start_warns_without_design_system`, `test_build_start_no_ui_section_for_backend_task`, `test_review_packet_mentions_ui_audit_for_ui_card`, `test_router_routes_ui_requests` (route keys present, commands name `cp-ui`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: cp-build/cp-review/router hooks for cp-ui`.

### Task 10: Docs, ADR, e2e, traceability

**Files:**
- Modify: `skills/cp-ui/SKILL.md` (final), `CLAUDE.md` (rule 6: add the second exception — `cp-ui --audit` runs the visual command declared in `.context/ui/profile.json`; skill counts 9+7), `.context/tracking/decisions.md` (ADR-0022), `README.md` (skill list)
- Move: `.context/inbox/initiatives/cp-ui-design.md` → `.context/inbox/processed/` with `[Done]` title prefix
- Test: `tests/test_ui_e2e.py`; `tests/test_skill_contract.py` must pass for the new SKILL.md

- [ ] **Step 1: Failing e2e test** — temp project with `index.html` (`<img src=x>`, `outline-none`) → `--design-system` packet → record a MASTER.md → `--audit` packet lists `img-no-alt` → `--audit --record` → one BUG `source: cp-ui` → fix the file → `--verify` passes.
- [ ] **Step 2: Run** → FAIL until SKILL.md/wiring complete; **Step 3** finish docs and ADR-0022 (context, decision: approach A + the four operator decisions, consequences, the second command-running exception); **Step 4** full suite under `.venv/bin/python -m pytest` → PASS.
- [ ] **Step 5: Backlog** — create EP/ST/TK cards via `cp-backlog` mirroring Tasks 1–9 (as was done for the pentest) and move them to `7-done` once merged.
- [ ] **Step 6: Commit, merge to `main`, push** as `renatohorta` (repo-local identity already pinned) — only with the operator's go-ahead.
