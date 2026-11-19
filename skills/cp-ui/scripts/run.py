#!/usr/bin/env python3
"""
cp-ui — design system (and, later, UI audit) for the project's front end.

It never calls a model (ADR-0012): the agent running it is the LLM.

  run.py --design-system ["<briefing>"] [--product NAME] [--out DIR]
        print the read-only packet: discovery, detected stack, three design
        directions (summary + HTML preview + MASTER.md draft), the record command
  run.py --design-system --record FILE|- --chosen-by NAME [--page PAGE]
        [--force --reason R]
        validate the chosen document, write design-system/MASTER.md (or
        pages/<PAGE>.md) + tokens.json, log the decision
  run.py --audit ["<scope>"] [--path SUB] [--visual]
        print the audit packet (--visual runs the profile's visual command): static candidates, checklist, document format
  run.py --audit --verify BUG-NNN [--visual] [--evidence PATH]
        re-check one cp-ui BUG; writes .context/ui/verify/BUG-NNN.json (exit 1 on fail)
  run.py --audit --record FILE|- [--path SUB] [--by NAME]
        validate the audit document, open one BUG per (rule, file) group of confirmed
        findings (visual: one per check, viewports as occurrences), store dismissals, write .context/ui/audits/<date>.md

Usage:
  python run.py --design-system "legal saas dashboard" [--context-dir D]
  python run.py --design-system --record FILE|- --chosen-by NAME [--context-dir D]
"""
import argparse
import json
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

# _shared/ sits in the skills root: next to this skill (repo, Claude Code) or one
# level up when the agent nests skills in a category (Hermes: skills/<category>/).
_SKILL_DIR = Path(__file__).resolve().parent.parent
for _root in (_SKILL_DIR.parent, _SKILL_DIR.parent.parent):
    if (_root / "_shared" / "discipline.py").is_file():
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        break
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _shared import cards, context, uicheck, uikit  # noqa: E402
from _shared.discipline import cmdline, fail, read_document  # noqa: E402
from _shared.rup import EXIT_OK, setup_console  # noqa: E402

SKILL_NAME = "cp-ui"
DISCOVERY_WORDS = 30
FALLBACK_QUERY = "saas dashboard"


def project_root(context_dir) -> Path:
    return Path(context_dir).resolve().parent


# ─── packet inputs ──────────────────────────────────────────────────────────

def find_discovery(context_dir):
    """The canonical cp-discover.md, else any cp-discover*.md under docs/; (path, text)."""
    canonical = context.artifact_path(context_dir, "Inception", "cp-discover")
    candidates = [canonical] if canonical.is_file() else sorted(
        (Path(context_dir) / "docs").glob("**/cp-discover*.md"))
    for path in candidates:
        try:
            return path, path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return None, ""


def _words(text, n):
    return text.split()[:n]


def discovery_query(text):
    lines = [l for l in text.splitlines()
             if l.strip() and not l.lstrip().startswith(("#", "|", "---"))]
    return " ".join(_words(" ".join(lines), DISCOVERY_WORDS))


def detect_stack(root):
    found = []
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        except (OSError, ValueError, AttributeError):
            deps = {}
        found.append("package.json (" + (", ".join(sorted(deps)[:12]) or "no dependencies") + ")")
    for name in ("pubspec.yaml", "Package.swift", "composer.json"):
        if (root / name).is_file():
            found.append(name)
    return found


# ─── --design-system packet ─────────────────────────────────────────────────

def print_packet(context_dir, briefing, product, out):
    from directions import compose, to_master, write_previews
    path, text = find_discovery(context_dir)
    query = (briefing or "").strip() or discovery_query(text)
    if not query:
        fail("no briefing and no discovery found — pass a briefing describing the product "
             "(or run cp-discover first)")
    product = (product or "").strip() or " ".join(_words(query, 4))
    stack = detect_stack(project_root(context_dir))
    ds = compose(query, product, fallback=FALLBACK_QUERY)
    matched = sum(1 for d in ds if not d.get("fallback"))
    note = ""
    if ds and matched == 0:
        note = (f"No match for the briefing's words — these directions come from a generic "
                f"fallback query ('{FALLBACK_QUERY}'); ask the operator for "
                f"product-type/industry keywords and re-run.\n")
    elif ds and matched < len(ds):  # keyword search: thin matches get topped up
        note = (f"**Note: only {matched} direction(s) matched the briefing — the others come "
                f"from a generic fallback ('{FALLBACK_QUERY}'); ask the operator for more "
                f"product-type/industry keywords and re-run.**\n")
    if not ds:
        fail("no usable design direction for this briefing — try other words")
    out_dir = Path(out) if out else Path(tempfile.mkdtemp(prefix="cp-ui-"))
    previews = write_previews(ds, out_dir)
    me = Path(__file__).resolve()
    record = cmdline([sys.executable, me, "--design-system", "--record", "FILE|-",
                      "--chosen-by", "<NAME>"])

    print(f"# Design system — {product}\n")
    print("You are the designer. Show the directions below side by side; the operator picks, "
          "mixes or edits. Do not choose for them.\n")
    print("## Discovery\n")
    if path:
        rel = path.relative_to(Path(context_dir)) if Path(context_dir) in path.parents else path
        print(f"Read `{rel}` first:\n")
        print(text.strip()[:3000] + "\n")
    else:
        print("none — ask the operator\n")
    print("## Detected stack\n")
    print("\n".join(f"- {s}" for s in stack) if stack else "unknown — ask the operator")
    print()
    print(f"## Directions ({len(ds)})\n")
    if note:
        print(note)
    for d, preview in zip(ds, previews):
        style = (d.get("style") or {}).get("name", "")
        typo = d.get("typography") or {}
        colors = d.get("colors") or {}
        tag = " (generic fallback)" if d.get("fallback") else ""
        print(f"### Direction {d['id']} — {style}{tag}\n")
        print(f"- Primary: {colors.get('primary', '')} on {colors.get('background', '')}")
        print(f"- Typography: {typo.get('heading', '')} / {typo.get('body', '')}")
        print(f"- Preview: {preview}\n")
    print("## MASTER.md drafts\n")
    for d in ds:
        print(f"### Draft {d['id']}\n\n```markdown\n{to_master(d, product).rstrip()}\n```\n")
    print("## Next\n")
    print("Show the previews, ask the operator, then write ONE final MASTER.md document "
          "(picked, mixed or edited) with the `## Decision` section filled: `Chosen by:` "
          "(the operator's name), `Alternatives shown:`, `Why:`.\n")
    print(f"- Record: `{record}`")
    print("- A page-specific system: add `--page <name>`; replace an existing one: "
          "`--force --reason \"...\"`.")


# ─── --design-system --record ───────────────────────────────────────────────

def _slug(page):
    return re.sub(r"[^a-z0-9]+", "-", page.lower()).strip("-")


def _product_of(text, default):
    m = re.search(r"^#\s*Design system\s*[—–-]\s*(.+?)\s*$", text, re.M)
    return m.group(1) if m else (default or "design system")


def record(context_dir, source, chosen_by, page, force, reason, product):
    if force and not (reason or "").strip():
        fail("--force needs --reason \"why the existing design system is replaced\"")
    if not (chosen_by or "").strip():
        fail("--chosen-by NAME is required (the operator who made the choice)")
    context.ensure_writable(context_dir)
    text = read_document(source)
    system, errors = uikit.parse_master(text)
    if errors:
        print("Design system rejected:")
        for e in errors:
            print(f"- {e}")
        sys.exit(1)
    decision = system["decision"]
    if decision["chosen_by"].strip().lower() != chosen_by.strip().lower():
        fail(f"--chosen-by '{chosen_by.strip()}' does not match the document's Decision "
             f"'Chosen by: {decision['chosen_by']}'")

    ds = uikit.ds_dir(context_dir)
    if page:
        slug = _slug(page)
        if not slug:
            fail("--page needs a name with letters or digits")
        target = ds / "pages" / f"{slug}.md"
    else:
        target = ds / "MASTER.md"
    if target.exists() and not force:
        fail(f"{target} already exists — pass --force --reason \"...\" to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    written = [target]
    if not page:
        tokens = ds / "tokens.json"
        tokens.write_text(json.dumps(uikit.tokens_from_system(system), indent=2) + "\n",
                          encoding="utf-8")
        written.append(tokens)

    name = _product_of(text, product)
    scope = f" (page {slug})" if page else ""
    entry = [f"\n## Design system — {name}{scope} ({date.today().isoformat()})\n",
             f"- Chosen by: {decision['chosen_by']}",
             f"- Alternatives shown: {decision['alternatives']}",
             f"- Why: {decision['why']}"]
    if force:
        entry.append(f"- Reason (overwrite): {reason.strip()}")
    decisions = Path(context_dir) / "tracking" / "decisions.md"
    decisions.parent.mkdir(parents=True, exist_ok=True)
    with decisions.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(entry) + "\n")
    context.append_event(context_dir, skill=SKILL_NAME,
                         what=f"design system recorded: {name}{scope}, chosen by {decision['chosen_by']}")
    for w in written:
        print(f"Wrote {w}")
    print(f"Decision logged in {decisions}")


# ─── --audit ────────────────────────────────────────────────────────────────

CHECKLIST_REF = _SKILL_DIR / "references" / "checklist.md"


def load_profile(context_dir) -> dict:
    """`.context/ui/profile.json` (optional). Unknown keys are left to other tasks."""
    path = Path(context_dir) / "ui" / "profile.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        fail(f"cannot read {path}: {e}")
    if not isinstance(data, dict):
        fail(f"{path} must contain a JSON object")
    return data


def excludes_of(context_dir) -> list:
    ex = load_profile(context_dir).get("exclude", [])
    if not isinstance(ex, list):
        fail("profile.json: `exclude` must be a list of paths/globs")
    return [str(x) for x in ex]


def _scan(context_dir, subpath=""):
    ds = uikit.load_design_system(context_dir)
    return uicheck.scan(project_root(context_dir), excludes_of(context_dir), ds, subpath)


def print_audit_packet(context_dir, scope, subpath, visual_opt_in=False):
    context.require_consent(context_dir)
    cands, scanned = _scan(context_dir, subpath)
    dismissed = uicheck.load_dismissals(context_dir)
    shown = [c for c in cands if uicheck.candidate_key(c) not in dismissed]
    hidden = len(cands) - len(shown)
    try:
        items = uicheck.parse_checklist_doc(CHECKLIST_REF.read_text(encoding="utf-8"))
    except OSError:
        items = {}
    profile = load_profile(context_dir)
    visual = []
    cmd_cwd = uicheck.visual_command_line(project_root(context_dir), profile)
    if cmd_cwd is None:
        visual_status = uicheck.VISUAL_NOT_CONFIGURED
    elif not visual_opt_in:
        visual_status = "skipped (--visual not given)"
    else:
        print(f"Running visual audit (--visual): {cmd_cwd[0]}\n  cwd: {cmd_cwd[1]}\n", flush=True)
        visual_status, visual = uicheck.run_visual(project_root(context_dir), profile)
    uicheck.save_visual_last(context_dir, visual_status, subpath, visual)
    me = Path(__file__).resolve()
    record_args = [sys.executable, me, "--audit", "--record", "FILE|-", "--by", "<NAME>"]
    if subpath:
        record_args += ["--path", subpath]
    record_cmd = cmdline(record_args)

    print(f"# UI audit — {scope or 'the whole front end'}\n")
    print("You are the auditor. Verify every candidate in the source (a regex hit is a "
          "candidate, not a bug), answer the checklist with evidence, then record ONE "
          "document. Say only what you verified: unverified items stay `not-verified`.\n")
    print(f"Header the record will write (visual layer: {visual_status}):\n")
    print("    " + uicheck.header_line(scanned, visual_status, {}) + "\n")
    if scanned == 0:
        print("[!] 0 UI files scanned — a backend-only project, a wrong --path or an over-broad "
              "`exclude`. This is NOT a clean bill of health.\n")

    print(f"## Static candidates ({len(shown)}" + (f", {hidden} hidden as dismissed" if hidden else "")
          + ")\n")
    for c in shown:
        print(f"- `{c.rule}` [{c.severity}] {c.file}:{c.line} — {c.snippet}")
    if not shown:
        print("- (none)")
    if hidden:
        print(f"\n{hidden} candidate(s) hidden: dismissed earlier "
              f"(.context/ui/dismissals.json).")
    print("\nWhat each rule means and how to dismiss a false positive: "
          "references/static-checks.md\n")

    if visual or visual_status != uicheck.VISUAL_NOT_CONFIGURED:
        shown_v = uicheck.visual_not_dismissed(visual, dismissed)
        hidden_v = len(visual) - len(shown_v)
        visual = shown_v
        print(f"## Visual candidates ({len(visual)}"
              + (f", {hidden_v} hidden as dismissed" if hidden_v else "")
              + f") — visual: {visual_status}\n")
        for v in visual:
            print("## Finding")
            print(f"Rule: visual:{v['check']}")
            print(f"Location: {uicheck.visual_location(v)}")
            print(f"Evidence: {uicheck.visual_evidence(v)}")
            print("Verdict: <confirmed | dismissed — <reason> | cannot verify — <why>>")
            print(f"Severity: {v['severity'] or 'Medium'}\n")
        if not visual:
            print("- (none)\n")

    print("## Checklist (answer every item with evidence)\n")
    for item in uicheck.CHECKLIST_IDS:
        print(f"### {item}\n{items.get(item, '(see references/checklist.md)')}\n")

    print("## Audit document to write\n")
    print("```")
    print("## Finding")
    print("Rule: img-no-alt            # a static rule id | checklist:<item-id> | visual:<check>")
    print("Location: src/pages/Home.tsx:12")
    print("Evidence: <what you saw: code or a screenshot path>")
    print("Verdict: confirmed          # or: dismissed — <reason>  /  cannot verify — <why>")
    print("Severity: Critical|High|Medium|Low")
    print("")
    print("## Checklist")
    print("- states-loading-empty-error: ok | finding | not-applicable | not-verified — <evidence>")
    print("```\n")
    print("Only `Verdict: confirmed` opens a BUG (one per rule and file; the occurrences are "
          "listed in it). `dismissed — <reason>` hides that candidate from future packets. "
          "Anything else opens nothing and is reported as not verified. A checklist item "
          "answered `finding` needs its own `## Finding` block with `Rule: checklist:<item-id>`.\n")
    print("## When done\n")
    print(f"- Record: `{record_cmd}`")


def verify_bug(context_dir, bug_id, visual_opt_in, evidence):
    """Re-check ONE cp-ui BUG (its `ui_key` rule on its file); write the verify record."""
    context.ensure_writable(context_dir)
    card = cards.get(context_dir, bug_id)
    key = str(card.meta.get("ui_key", ""))
    if card.meta.get("source") != uicheck.SOURCE or not key:
        fail(f"{bug_id} is not a cp-ui BUG (needs `source: cp-ui` and a `ui_key`): "
             f"--verify only re-checks BUGs opened by cp-ui --audit --record")
    rule, _, file = key.partition("::")
    root = project_root(context_dir)
    if rule.startswith("visual:"):
        if not visual_opt_in:
            fail(f"{bug_id} is a visual rule ({rule}): the visual re-check needs --visual "
                 f"(it runs the profile's visual_audit command)")
        recorded = [v for v in str(card.meta.get("ui_viewports", "")).split(",") if v]
        if not recorded and file != uicheck.VISUAL_PAGE:  # legacy per-viewport key
            recorded = [file]
        result, ev = uicheck.verify_visual(root, load_profile(context_dir),
                                           rule.split(":", 1)[1], recorded)
    elif rule.startswith("checklist:"):
        if not evidence:
            fail(f"{bug_id} is a checklist item ({rule}): pass --evidence PATH "
                 f"(a screenshot or note proving the fix)")
        path = Path(evidence)
        path = path if path.is_absolute() else root / path
        if not path.is_file():
            fail(f"--evidence {evidence}: not an existing file")
        result, ev = "pass", str(evidence)
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            result, ev = "fail", f"evidence {evidence} is outside the project root"
        else:
            after = uicheck.parse_ts(card.meta.get("ui_verify_after", ""))
            if after is None:
                result, ev = "fail", ("the BUG has no ui_verify_after: start it with "
                                      "cp-build --start first")
            elif path.stat().st_mtime < after.timestamp():
                result, ev = "fail", (f"evidence {evidence} is older than the start of the fix "
                                      f"({card.meta.get('ui_verify_after')})")
    else:
        result, ev = uicheck.verify_static(context_dir, root, excludes_of(context_dir),
                                           rule, file,
                                           uicheck.parse_ts(card.meta.get("ui_verify_after", "")))
    rec = uicheck.write_verify_record(context_dir, bug_id, rule, result, ev)
    print(f"{bug_id} {rule}: {result.upper()} at {rec['at']} — {ev}")
    return 0 if result == "pass" else 1


def _report_path(context_dir) -> Path:
    folder = Path(context_dir) / "ui" / "audits"
    stamp = date.today().isoformat()
    path = folder / f"{stamp}.md"
    n = 2
    while path.exists():
        path = folder / f"{stamp}-{n}.md"
        n += 1
    return path


def record_audit(context_dir, source, by, subpath=""):
    context.ensure_writable(context_dir)
    text = read_document(source).strip()
    findings, answers, errors = uicheck.parse_audit(text)
    if errors:
        print("Audit document rejected:")
        for e in errors:
            print(f"- {e}")
        sys.exit(1)

    cands, scanned = _scan(context_dir, subpath)
    errors = uicheck.check_dismissals(findings, cands)
    if errors:
        print("Audit document rejected (a dismissal must hide a real candidate):")
        for e in errors:
            print(f"- {e}")
        sys.exit(1)
    already = uicheck.load_dismissals(context_dir)
    left = uicheck.unaddressed(findings, cands, already)

    groups = {}
    unmatched = []
    for f in findings:
        if not f.confirmed:
            continue
        key = uicheck.group_key(f)
        if f.rule.strip() in uicheck.CHECKS:
            cand, err = uicheck.match_candidate(f, cands)
            if err:
                unmatched.append(err)
                continue
            key = f"{cand.rule}::{cand.file}"  # the scanner's normalized file
        groups.setdefault(key, []).append(f)
    if unmatched:
        print("Audit document rejected (a confirmed static finding must match a scanner "
              "candidate, or --verify could never re-check it):")
        for e in unmatched:
            print(f"- {e}")
        print("Fix the Location (path:line), or file what the scanner cannot see as "
              "`Rule: checklist:<id>`.")
        sys.exit(1)
    uicheck.record_dismissals(context_dir, findings, (by or "").strip() or "agent", cands)
    open_bugs = uicheck.open_bugs_by_key(context_dir)
    results = []  # (key, group, card id, created?)
    for key, group in groups.items():
        vps = uicheck.group_viewports(group) if key.endswith("::" + uicheck.VISUAL_PAGE) else []
        if key in open_bugs:
            if vps:
                old = [v for v in str(open_bugs[key].meta.get("ui_viewports", "")).split(",") if v]
                merged = old + [v for v in vps if v not in old]
                if merged != old:
                    cards.set_meta(open_bugs[key], "ui_viewports", ",".join(merged))
            results.append((key, group, open_bugs[key].id, False))
            continue
        rule, file = key.split("::", 1)
        title, body, priority = uicheck.bug_document(rule, file, group)
        card = cards.create(context_dir, "bug", title, body, priority=priority,
                            source=uicheck.SOURCE)
        cards.set_meta(card, "ui_key", key)
        if vps:
            cards.set_meta(card, "ui_viewports", ",".join(vps))
        results.append((key, group, card.id, True))

    # never re-run the command: `ran` only comes from the last packet run for this scope
    visual_status, visual = uicheck.visual_status_for_record(
        context_dir, load_profile(context_dir), subpath)
    visual_left = uicheck.unaddressed_visual(
        findings, uicheck.visual_not_dismissed(visual, already))
    header = uicheck.header_line(scanned, visual_status, answers, len(left) + len(visual_left))
    dismissed = [f for f in findings if f.dismissed]
    unverified = [f for f in findings if not f.confirmed and not f.dismissed]
    last = uicheck.load_visual_last(context_dir)
    at = last.get("at") if last and (last.get("scope") or "") == (subpath or "") else None
    lines = [header, f"Visual run at: {at or 'n/a'}", "", f"# UI audit — {date.today().isoformat()}", "", "## Findings", ""]
    for key, group, cid, created in results:
        lines.append(f"- {key} — " + (f"{cid} (opened)" if created else f"already open: {cid}"))
        lines += [f"  - {uicheck.occurrence(f)} [{f.severity.strip()}]" for f in group]
    if not results:
        lines.append("- none confirmed")
    lines += ["", "## Dismissed", ""]
    lines += [f"- {f.rule} at {f.location} — {f.reason} (by {(by or '').strip() or 'agent'})"
              for f in dismissed] or ["- none"]
    lines += ["", "## Not verified", ""]
    lines += [f"- {f.rule} at {f.location} — {f.verdict.strip()}" for f in unverified]
    lines += [f"- static candidate {c.rule} at {c.file}:{c.line} — not addressed: {c.snippet}"
              for c in left]
    lines += [f"- visual candidate visual:{v['check']} at {uicheck.visual_location(v)} — "
              f"not addressed: {uicheck.visual_evidence(v)}" for v in visual_left]
    lines += [f"- checklist:{k} — " + (answers[k][1] or "not verified")
              if k in answers else f"- checklist:{k} — not answered"
              for k in uicheck.CHECKLIST_IDS
              if answers.get(k, ("not-verified", ""))[0] == "not-verified"]
    lines += ["", "## Checklist", "", "| Item | Result | Evidence |", "|---|---|---|"]
    for k in uicheck.CHECKLIST_IDS:
        status, ev = answers.get(k, ("not-verified", "not answered"))
        lines.append(f"| {k} | {status} | {ev.replace('|', '/')} |")
    report = _report_path(context_dir)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    created = [cid for _, _, cid, new in results if new]
    context.append_event(context_dir, skill=SKILL_NAME,
                         what=f"ui audit recorded: {len(created)} BUG(s) opened, "
                              f"{len(dismissed)} dismissed")
    print(header)
    n_conf = sum(len(g) for _, g, _, _ in results)
    print(f"{n_conf} confirmed finding(s), {len(dismissed)} dismissed, "
          f"{len(unverified)} not verified.")
    print(f"BUG cards opened: {', '.join(created) if created else 'none'}")
    for key, _, cid, new in results:
        if not new:
            print(f"already open: {cid} ({key})")
    print(f"Report: {report}")


def main(argv=None) -> int:
    setup_console()
    p = argparse.ArgumentParser(description="cp-ui: design system for the front end")
    p.add_argument("briefing", nargs="?", default="", help="what the product is (free text)")
    p.add_argument("--design-system", action="store_true", help="design-system packet / record")
    p.add_argument("--record", metavar="FILE|-", help="record the chosen MASTER.md document")
    p.add_argument("--chosen-by", help="operator who made the choice (must match the document)")
    p.add_argument("--product", help="product name (default: first 4 words of the briefing)")
    p.add_argument("--page", help="record a page-specific system (design-system/pages/<PAGE>.md)")
    p.add_argument("--force", action="store_true", help="overwrite an existing file (needs --reason)")
    p.add_argument("--reason", help="why the existing file is replaced")
    p.add_argument("--out", help="directory for the HTML previews (default: a temp dir)")
    p.add_argument("--audit", action="store_true", help="UI audit packet / record")
    p.add_argument("--visual", action="store_true",
                   help="--audit: run the profile's visual_audit command (opt-in; never starts servers)")
    p.add_argument("--verify", metavar="BUG-ID", help="--audit: re-check one cp-ui BUG")
    p.add_argument("--evidence", metavar="PATH", help="--audit --verify: proof file for a checklist BUG")
    p.add_argument("--path", help="--audit [--record]: narrow the scan to a subtree")
    p.add_argument("--by", help="--audit --record: who dismissed (default: agent)")
    p.add_argument("--context-dir", help="target .context/ (default: auto-detect)")
    args = p.parse_args(argv)
    context_dir = context.resolve_context_dir(args.context_dir)

    if args.audit and args.design_system:
        fail("--audit and --design-system are separate modes; pick one")
    if args.audit:
        if args.verify:
            return verify_bug(context_dir, args.verify, args.visual, args.evidence)
        if args.record:
            record_audit(context_dir, args.record, args.by, args.path)
        else:
            print_audit_packet(context_dir, args.briefing, args.path, args.visual)
        return EXIT_OK
    if not args.design_system:
        fail("choose a mode: --design-system or --audit")
    if args.record:
        record(context_dir, args.record, args.chosen_by, args.page, args.force,
               args.reason, args.product)
    else:
        print_packet(context_dir, args.briefing, args.product, args.out)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
