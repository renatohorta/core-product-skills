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
  run.py --audit ["<scope>"] [--path SUB]
        print the read-only audit packet: static candidates, checklist, document format
  run.py --audit --record FILE|- [--by NAME]
        validate the audit document, open one BUG per (rule, file) group of confirmed
        findings, store dismissals, write .context/ui/audits/<date>.md

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
    ds = compose(query, product)
    note = ""
    if not ds:  # the vendored search is keyword-based: unknown words match nothing
        ds = compose(FALLBACK_QUERY, product)
        note = (f"No match for the briefing's words — these directions come from a generic "
                f"fallback query ('{FALLBACK_QUERY}'); ask the operator for "
                f"product-type/industry keywords and re-run.\n")
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
        print(f"### Direction {d['id']} — {style}\n")
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


def print_audit_packet(context_dir, scope, subpath):
    context.require_consent(context_dir)
    cands, scanned = _scan(context_dir, subpath)
    dismissed = uicheck.load_dismissals(context_dir)
    shown = [c for c in cands if uicheck.candidate_key(c) not in dismissed]
    hidden = len(cands) - len(shown)
    try:
        items = uicheck.parse_checklist_doc(CHECKLIST_REF.read_text(encoding="utf-8"))
    except OSError:
        items = {}
    me = Path(__file__).resolve()
    record_cmd = cmdline([sys.executable, me, "--audit", "--record", "FILE|-", "--by", "<NAME>"])

    print(f"# UI audit — {scope or 'the whole front end'}\n")
    print("You are the auditor. Verify every candidate in the source (a regex hit is a "
          "candidate, not a bug), answer the checklist with evidence, then record ONE "
          "document. Say only what you verified: unverified items stay `not-verified`.\n")
    print("Header the record will write (visual layer: " + uicheck.VISUAL_NOT_CONFIGURED + "):\n")
    print("    " + uicheck.header_line(scanned, uicheck.VISUAL_NOT_CONFIGURED, {}) + "\n")
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


def _report_path(context_dir) -> Path:
    folder = Path(context_dir) / "ui" / "audits"
    stamp = date.today().isoformat()
    path = folder / f"{stamp}.md"
    n = 2
    while path.exists():
        path = folder / f"{stamp}-{n}.md"
        n += 1
    return path


def record_audit(context_dir, source, by):
    context.ensure_writable(context_dir)
    text = read_document(source).strip()
    findings, answers, errors = uicheck.parse_audit(text)
    if errors:
        print("Audit document rejected:")
        for e in errors:
            print(f"- {e}")
        sys.exit(1)

    cands, scanned = _scan(context_dir)
    uicheck.record_dismissals(context_dir, findings, (by or "").strip() or "agent", cands)

    groups = {}
    for f in findings:
        if f.confirmed:
            groups.setdefault(uicheck.group_key(f), []).append(f)
    open_bugs = uicheck.open_bugs_by_key(context_dir)
    results = []  # (key, group, card id, created?)
    for key, group in groups.items():
        if key in open_bugs:
            results.append((key, group, open_bugs[key].id, False))
            continue
        rule, file = key.split("::", 1)
        title, body, priority = uicheck.bug_document(rule, file, group)
        card = cards.create(context_dir, "bug", title, body, priority=priority,
                            source=uicheck.SOURCE)
        cards.set_meta(card, "ui_key", key)
        results.append((key, group, card.id, True))

    visual = ("ran (agent-reported)" if any(f.rule.startswith("visual:") for f in findings)
              else uicheck.VISUAL_NOT_CONFIGURED)
    header = uicheck.header_line(scanned, visual, answers)
    dismissed = [f for f in findings if f.dismissed]
    unverified = [f for f in findings if not f.confirmed and not f.dismissed]
    lines = [header, "", f"# UI audit — {date.today().isoformat()}", "", "## Findings", ""]
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
    p.add_argument("--path", help="--audit: narrow the scan to a subtree")
    p.add_argument("--by", help="--audit --record: who dismissed (default: agent)")
    p.add_argument("--context-dir", help="target .context/ (default: auto-detect)")
    args = p.parse_args(argv)
    context_dir = context.resolve_context_dir(args.context_dir)

    if args.audit and args.design_system:
        fail("--audit and --design-system are separate modes; pick one")
    if args.audit:
        if args.record:
            record_audit(context_dir, args.record, args.by)
        else:
            print_audit_packet(context_dir, args.briefing, args.path)
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
