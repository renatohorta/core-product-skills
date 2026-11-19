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

from _shared import context, uikit  # noqa: E402
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
        note = (f"No style data matched the briefing words; the directions below use the "
                f"generic query \"{FALLBACK_QUERY}\". Ask the operator for domain keywords "
                f"(e.g. \"legal saas dashboard\") and re-run for closer matches.\n")
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
    p.add_argument("--context-dir", help="target .context/ (default: auto-detect)")
    args = p.parse_args(argv)
    context_dir = context.resolve_context_dir(args.context_dir)

    if not args.design_system:
        fail("choose a mode: --design-system")
    if args.record:
        record(context_dir, args.record, args.chosen_by, args.page, args.force,
               args.reason, args.product)
    else:
        print_packet(context_dir, args.briefing, args.product, args.out)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
