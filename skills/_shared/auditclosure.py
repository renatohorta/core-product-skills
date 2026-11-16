#!/usr/bin/env python3
"""
auditclosure.py — did the test audit cover the code it claims? (ADR-0018)

A mutation score is a number over the modules that were mutated. It says nothing
about the modules that were not: "87% over three modules" reads like "the tests
are fine" while forty modules were never touched. A report that lists only the
audited modules implies the rest was checked and came out clean — the most
dangerous default a Test Value Assessment can have.

    CLEAN   every source module reached a mutation verdict
            (or carries an explicit waiver with its reason)
    MARKED  otherwise, and the gaps ship as "Not audited — do not read as
            passing" generated from this ledger, never hand-written

Verdicts per source module (`profile.source_extensions`, non-test files):

    audited        at least one mutant was graded (killed / timeout / survived)
    blocked        mutants exist but none was graded (all error<N> / invalid):
                   the audit reached the module and could not judge it
    never_audited  no mutant has a result
    waived         an explicit, reasoned waiver (`--waive`)

`blocked` is deliberately NOT covered — same rule as the coverage-closure gate
this was ported from (Claude-BugHunter, engine/closure.py, ADR-0016/0018).

Pure functions over `results.jsonl` + the waivers file, so the gate is testable
without running a single mutant.
"""
import json
import re
from datetime import datetime
from pathlib import Path

from _shared import mutation

SOURCE_EXTS = [".py"]
COVERED = ("audited", "waived")
WAIVERS = "closure-waivers.json"
REPORT = "closure.md"


# ─── the surface: which files the audit is expected to cover ─────────────

def _matches(pattern: str, path: str) -> bool:
    """`*` (one segment), `**` (any depth), `?`. A bare directory name covers it all."""
    pat = (pattern or "").strip().replace("\\", "/").strip("/")
    if not pat:
        return False
    rx = (re.escape(pat)
          .replace(r"\*\*/", "(?:.*/)?")
          .replace(r"\*\*", ".*")
          .replace(r"\*", "[^/]*")
          .replace(r"\?", "[^/]"))
    return re.fullmatch(rx + "(?:/.*)?", path) is not None


def source_files(project_root, profile) -> list:
    """Every non-test source module of the project, relative POSIX paths, sorted.

    Generated/vendored trees come from `copy_ignore` (the same list the mutation
    copies use); `audit_exclude` narrows the surface further (e.g. "src/legacy/**").
    """
    root = Path(project_root)
    exts = tuple(profile.get("source_extensions") or SOURCE_EXTS)
    ignore = set(profile.get("copy_ignore") or mutation.DEFAULT_IGNORE)
    extra = [p for p in (profile.get("audit_exclude") or []) if p]
    out = []
    for path in mutation._walk(root, ignore):
        rel = path.relative_to(root)
        if not path.name.endswith(exts) or mutation.is_test_file(rel):
            continue
        posix = str(rel).replace("\\", "/")
        if any(_matches(p, posix) for p in extra):
            continue
        out.append(posix)
    return sorted(out)


# ─── waivers: the reasoned escape hatch ─────────────────────────────────

def waivers_path(ledger_dir) -> Path:
    return Path(ledger_dir) / WAIVERS


def load_waivers(ledger_dir) -> list:
    path = waivers_path(ledger_dir)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = data.get("waivers") if isinstance(data, dict) else data
    return [w for w in (rows or []) if isinstance(w, dict) and w.get("pattern")]


def add_waiver(ledger_dir, pattern: str, reason: str) -> dict:
    """Record why a part of the surface is out of the audit. The reason is mandatory."""
    pattern, reason = (pattern or "").strip(), (reason or "").strip()
    if not pattern:
        raise ValueError("--waive needs a path or glob (e.g. src/legacy/**)")
    if len(reason) < 12:
        raise ValueError("--waive needs --reason explaining why that surface does not "
                         "owe a mutation verdict (12+ characters)")
    path = waivers_path(ledger_dir)
    rows = load_waivers(ledger_dir)
    entry = {"pattern": pattern.replace("\\", "/").strip("/"), "reason": reason,
             "at": datetime.now().isoformat(timespec="seconds")}
    for old in rows:
        if old["pattern"] == entry["pattern"]:
            old.update(entry)
            break
    else:
        rows.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "waivers": rows}, indent=2) + "\n",
                    encoding="utf-8")
    return entry


# ─── the gate ────────────────────────────────────────────────────────────

def evaluate(project_root, results_dir, ledger_dir, profile) -> dict:
    """Per source module: audited / blocked / never_audited / waived + the closure verdict.

    `results_dir` holds the mutation run (`results.jsonl`); `ledger_dir` holds the
    waivers (`closure-waivers.json`) next to the rest of the audit evidence.
    """
    files = source_files(project_root, profile)
    results = mutation.load_results(Path(results_dir) / "results.jsonl")
    per = mutation.summarize(results)
    waivers = load_waivers(ledger_dir)
    surface = set(files)
    rows = []
    for f in files:
        r = per.get(f) or {"mutants": 0, "killed": 0, "timeout": 0, "survived": 0,
                           "error": 0, "invalid": 0, "score": None}
        graded = r["killed"] + r["timeout"] + r["survived"]
        waiver = next((w for w in waivers if _matches(w["pattern"], f)), None)
        if graded:
            state, note = "audited", ""
        elif r["mutants"]:
            state = "blocked"
            note = (f"{r['mutants']} mutant(s) ran but none was graded "
                    f"({r['error']} error, {r['invalid']} invalid) — the audit reached "
                    "this module and could not judge it")
        elif waiver:
            state, note = "waived", waiver.get("reason", "")
        else:
            state, note = "never_audited", ""
        rows.append({"path": f, "state": state, "mutants": r["mutants"], "graded": graded,
                     "score": r["score"] if graded else None, "note": note})
    gaps = [r for r in rows if r["state"] not in COVERED]
    counts = {s: sum(1 for r in rows if r["state"] == s)
              for s in ("audited", "waived", "blocked", "never_audited")}
    counts["files"] = len(rows)
    outside = sorted({f for f, _ in results if f not in surface})
    if not gaps:
        reason = ("every source module reached a mutation verdict or carries a reasoned "
                  "waiver")
    else:
        bits = [f"{counts['blocked']} blocked"] if counts["blocked"] else []
        bits += [f"{counts['never_audited']} never audited"] if counts["never_audited"] else []
        reason = f"{len(gaps)} module(s) with no verdict: " + ", ".join(bits)
    return {"clean": not gaps, "rows": rows, "gaps": gaps, "counts": counts,
            "outside_surface": outside, "reason": reason}


def render(evaluation: dict, project: str = "", sha: str = "") -> str:
    """`closure.md` — the audit's own coverage, with the gaps spelled out."""
    c, rows = evaluation["counts"], evaluation["rows"]
    head = [f"# Audit closure — {project or 'project'} @ {sha or '(no git SHA)'}", "",
            f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
            f"- Source modules in the declared surface: {c['files']} "
            f"(`source_extensions` minus tests and `audit_exclude`)",
            f"- Mutation verdict: **{c['audited']}** audited · **{c['waived']}** waived "
            f"· **{c['blocked']}** blocked · **{c['never_audited']}** never audited",
            f"- **Closure: {'complete' if evaluation['clean'] else 'INCOMPLETE'}** — "
            f"{evaluation['reason']}", ""]
    if evaluation["clean"]:
        head += ["Every source module either reached a mutation verdict or carries an "
                 "explicit waiver with its reason. No coverage caveats apply.", ""]
    else:
        head += ["**This audit did not reach full coverage.** The modules below were in "
                 "the declared surface and are not covered; a mutation score over the "
                 "audited modules is not a claim about them.", ""]
        blocked = [r for r in rows if r["state"] == "blocked"]
        never = [r for r in rows if r["state"] == "never_audited"]
        if blocked:
            head += ["## Blocked — reached, not judged", ""]
            head += [f"- `{r['path']}` — {r['note']}" for r in blocked] + [""]
        if never:
            head += ["## Not audited — do not read as passing", ""]
            head += [f"- `{r['path']}`" for r in never] + [""]
        head += ["Absence of a mutation score above is not evidence that the tests would "
                 "catch a bug. Cover it (`cp-test --mutate --files …`) or waive it with a "
                 f"reason (`cp-test --waive <path> --reason \"…\"`).", ""]
    waived = [r for r in rows if r["state"] == "waived"]
    if waived:
        head += ["## Waived — out of the audit, on purpose", ""]
        head += [f"- `{r['path']}` — {r['note']}" for r in waived] + [""]
    audited = [r for r in rows if r["state"] == "audited"]
    if audited:
        head += ["## Audited", "", "| Module | Mutants | Graded | Score |", "|---|---:|---:|---:|"]
        for r in sorted(audited, key=lambda z: (z["score"] if z["score"] is not None else 101,
                                                z["path"])):
            head.append(f"| `{r['path']}` | {r['mutants']} | {r['graded']} | "
                        f"{'—' if r['score'] is None else str(r['score']) + '%'} |")
        head.append("")
    if evaluation.get("outside_surface"):
        head += ["## Mutated but outside the declared surface", "",
                 "These files have mutation results yet are not covered by "
                 "`source_extensions`/`audit_exclude` — align the profile or the audit:", ""]
        head += [f"- `{f}`" for f in evaluation["outside_surface"]] + [""]
    return "\n".join(head).rstrip() + "\n"
