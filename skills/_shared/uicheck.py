#!/usr/bin/env python3
"""
uicheck.py — static UI checks (cp-ui). Pure functions, stdlib only.

Line-based regexes over UI source files (html/css/scss/jsx/tsx/vue/svelte/astro).
Findings are *candidates*: a human or the visual pass confirms them. A backend-only
project scans zero files and returns ([], 0) — never a clean bill of health.

Also holds the audit document model (cp-ui --audit): parse_audit, group_key, dismissals,
open BUG lookup, the report header. Public surface (stable): UI_EXTENSIONS, Candidate,
CHECKS, scan, SEVERITY_PRIORITY, CHECKLIST_IDS, Finding, parse_audit, group_key.
Must not import `uikit` (uikit imports this module).
"""
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from _shared.auditclosure import _matches
from _shared.pentest import _fields, _finding_blocks, is_confirmed

UI_EXTENSIONS = (".html", ".css", ".scss", ".jsx", ".tsx", ".vue", ".svelte", ".astro")

IGNORE_DIRS = {".git", ".hg", ".svn", "node_modules", "dist", "build", ".next",
               ".nuxt", "vendor", "coverage", "out", "target", ".venv", "venv",
               "__pycache__"}

MAX_BYTES = 2_000_000
SNIPPET_MAX = 160
PROJECT = "(project)"

CHECKS = {
    "raw-color": {"severity": "medium",
                  "ux_rule": "UX: Color — use design tokens, not literals",
                  "summary": "Hard-coded color literal instead of a design token"},
    "img-no-alt": {"severity": "high",
                   "ux_rule": "UX: Accessibility — Alt text",
                   "summary": "<img> without an alt attribute"},
    "icon-button-no-name": {"severity": "high",
                            "ux_rule": "UX: Accessibility — Icon button labels",
                            "summary": "Icon-only button without an accessible name"},
    "outline-removed": {"severity": "high",
                        "ux_rule": "UX: Accessibility — Focus states",
                        "summary": "Focus outline removed without a replacement"},
    "zoom-disabled": {"severity": "high",
                      "ux_rule": "UX: Accessibility — Zoom / text scaling",
                      "summary": "Viewport blocks pinch-zoom"},
    "missing-lang": {"severity": "medium",
                     "ux_rule": "UX: Accessibility — Document language",
                     "summary": "<html> without a lang attribute"},
    "missing-viewport": {"severity": "medium",
                         "ux_rule": "UX: Responsive — Viewport meta",
                         "summary": "HTML document without a viewport meta tag"},
    "tiny-font": {"severity": "medium",
                  "ux_rule": "UX: Typography — Minimum readable size",
                  "summary": "Font size below 12px"},
    "emoji-icon": {"severity": "low",
                   "ux_rule": "UX: Icons — Use vector icons, not emojis",
                   "summary": "Emoji used as an icon in a button, link or nav item"},
    "no-reduced-motion": {"severity": "low",
                          "ux_rule": "UX: Accessibility — Reduced motion",
                          "summary": "Animations exist but prefers-reduced-motion is never honored"},
}


@dataclass
class Candidate:
    rule: str
    file: str
    line: int
    snippet: str
    severity: str


_HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_FUNC_COLOR = re.compile(r"\b(?:rgba?|hsla?)\(\s*(?!var\(|theme\()")
_CSS_VAR_DEF = re.compile(r"^\s*(?:--[\w-]+|\$[\w-]+)\s*:")
_VAR_DEF_INLINE = re.compile(r"(?<![\w-])--[\w-]+\s*:\s*[^;}]*")
_TAG = re.compile(r"<(img|button|a|li|NavLink|Link)\b", re.I)
_NAV_CTX = re.compile(r"""<nav\b|role\s*=\s*["']navigation|class(?:Name)?\s*=\s*["'][^"']*\bnav""", re.I)
_NAME_ATTR = re.compile(r"aria-label(?:ledby)?\s*=|\btitle\s*=", re.I)
_OUTLINE = re.compile(r"(?<![\w-])outline-none\b|\boutline\s*:\s*(?:none|0)\b")
# a real visible replacement: ring/shadow/sized outline under a focus variant, or CSS focus rule
# with box-shadow / a non-none outline. `focus:outline-none` is NOT a replacement.
_OUTLINE_OK = re.compile(
    r"focus(?:-visible|-within)?:(?:ring|shadow|border-\S)"
    r"|focus(?:-visible|-within)?:outline-(?!none\b|hidden\b)\S"
    r"|:focus(?:-visible|-within)?\b[^{]*\{[^}]*(?:box-shadow|outline\s*:\s*(?!none|0\b))")
_ZOOM = re.compile(r"user-scalable\s*=\s*(?:no|0)\b|maximum-scale\s*=\s*1(?:\.0+)?(?![\d.])", re.I)
_HTML_TAG = re.compile(r"<html\b", re.I)
_VIEWPORT = re.compile(r"""name\s*=\s*["']?viewport""", re.I)
_FONT_CSS = re.compile(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", re.I)
_FONT_TW = re.compile(r"text-\[(\d+(?:\.\d+)?)px\]")
_EMOJI = ("[\U0001F000-\U0001FAFF☀-➿⭐⭕⌚⌛⏩-⏳]")
_EMOJI_START = re.compile(r"\s*" + _EMOJI)
_ANIM = re.compile(r"@keyframes|\banimation(?:-name)?\s*:|\banimate-[a-z]|framer-motion|\bmotion\.\w")
SCRIPT_EXTENSIONS = (".js", ".ts", ".mjs", ".cjs")
_REDUCED = re.compile(r"prefers-reduced-motion|useReducedMotion|motion-reduce|motion-safe")


def _snip(line: str) -> str:
    return line.strip()[:SNIPPET_MAX]


def _tag_window(lines, i, col=0, span=8) -> str:
    """Text of the tag opening at lines[i][col:], continued over following lines until '>'."""
    out = lines[i][col:]
    j = i
    while ">" not in out and j + 1 < len(lines) and j - i < span:
        j += 1
        out += " " + lines[j]
    return out.split(">", 1)[0]


def _open_tag(lines, i, col, span=8):
    """Brace/quote-aware opening tag at lines[i][col:] -> (tag text, text after its '>').

    Skips `{...}` and quoted strings so the `>` of an arrow (`=>`) does not end the tag.
    Continues over following lines. Returns (text, "") when the tag never closes.
    """
    text = "\n".join(lines[i:i + span + 1])
    pos = col
    depth = 0
    quote = ""
    n = len(text)
    while pos < n:
        ch = text[pos]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == ">" and depth == 0:
            return text[col:pos], text[pos + 1:]
        pos += 1
    return text[col:], ""


def _read(path: Path):
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def _excluded(rel: str, exclude) -> bool:
    return any(_matches(p, rel) for p in (exclude or []) if p)


def scannable(project_root, rel, exclude, design_system, rule=None):
    """Why `scan` would not look at `rel` (None when it would). Uses the scanner's own
    predicates so a verify cannot pass on a file the scanner never reads."""
    rel = file_of(rel)
    if rel == PROJECT:
        return None
    root = Path(project_root)
    path = root / rel
    if not path.is_file():
        return f"{rel} does not exist under the project root"
    parts = rel.split("/")
    if any(d in IGNORE_DIRS for d in parts[:-1]):
        return f"{rel} is in an ignored directory"
    if not rel.lower().endswith(UI_EXTENSIONS):
        return f"{rel} is not a UI file the scanner reads ({', '.join(UI_EXTENSIONS)})"
    if _excluded(rel, exclude):
        return f"{rel} is excluded by the profile"
    if _read(path) is None:
        return f"{rel} is unreadable or larger than {MAX_BYTES} bytes"
    if rule == "raw-color":
        if design_system is None:
            return "raw-color needs a design system (none recorded): it cannot be re-checked"
        if _is_token_file(rel, design_system.get("token_files", []) or []):
            return f"{rel} is a token file: raw-color is not scanned there"
    return None


def _iter_files(root: Path, exclude, extra_exts=(), subpath=""):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
        for name in sorted(filenames):
            if not name.lower().endswith(UI_EXTENSIONS + tuple(extra_exts)):
                continue
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if subpath and not (rel == subpath or rel.startswith(subpath + "/")):
                continue
            if _excluded(rel, exclude):
                continue
            yield path, rel


def _is_token_file(rel: str, token_files) -> bool:
    if Path(rel).name.lower().startswith(("tokens.", "theme.")):
        return True
    listed = {str(t).replace("\\", "/").removeprefix("./") for t in token_files}
    return rel in listed


def _raw_color(line: str) -> bool:
    if _CSS_VAR_DEF.match(line):
        return False
    line = _VAR_DEF_INLINE.sub("", line)
    for m in _HEX.finditer(line):
        before = line[:m.start()]
        if before.endswith(("href=\"", "href='", "url(", "href=", "to=\"", "to='")):
            continue
        if m.start() and (line[m.start() - 1].isalnum() or line[m.start() - 1] in "&_"):
            continue
        return True
    return bool(_FUNC_COLOR.search(line))


def _scan_text(rel, text, lines, want_color):
    out = []

    def add(rule, i):
        out.append(Candidate(rule, rel, i + 1, _snip(lines[i]), CHECKS[rule]["severity"]))

    is_html = rel.lower().endswith(".html")
    if is_html and _HTML_TAG.search(text):
        for i, ln in enumerate(lines):
            m = _HTML_TAG.search(ln)
            if m:
                if not re.search(r"\blang\s*=", _tag_window(lines, i, m.start()), re.I):
                    add("missing-lang", i)
                if not _VIEWPORT.search(text):
                    add("missing-viewport", i)
                break

    for i, ln in enumerate(lines):
        flagged = set()
        for m in _TAG.finditer(ln):
            kind = m.group(1).lower()
            tag, rest = _open_tag(lines, i, m.start())
            if kind == "img":
                if not re.search(r"\balt\b", tag, re.I):
                    flagged.add("img-no-alt")
            elif kind == "button":
                inner = rest.split("</button>", 1)[0] if "</button>" in rest else None
                if (inner is not None and not _NAME_ATTR.search(tag)
                        and "sr-only" not in inner and re.search(r"<\w", inner)
                        and not re.sub(r"<[^>]*>|\s+", "", inner)):
                    flagged.add("icon-button-no-name")
            if (kind != "img" and _EMOJI_START.match(rest)
                    and (kind != "li" or _NAV_CTX.search(ln))):
                flagged.add("emoji-icon")
        if _OUTLINE.search(ln) and not _OUTLINE_OK.search(ln):
            flagged.add("outline-removed")
        if _ZOOM.search(ln):
            flagged.add("zoom-disabled")
        if any(float(v) < 12 for v in _FONT_CSS.findall(ln) + _FONT_TW.findall(ln)):
            flagged.add("tiny-font")
        if want_color and _raw_color(ln):
            flagged.add("raw-color")
        for rule in CHECKS:  # stable order
            if rule in flagged:
                add(rule, i)
    return out


def scan(project_root, exclude, design_system, subpath=""):
    """-> (candidates, files scanned). Backend-only projects give ([], 0).

    `subpath` (optional) narrows the walk to a subtree; paths stay project-relative.
    """
    root = Path(project_root)
    subpath = (subpath or "").replace("\\", "/").strip("/")
    token_files = (design_system or {}).get("token_files", []) or []
    cands, scanned = [], 0
    anim = None
    reduced = False
    for path, rel in _iter_files(root, exclude or [], SCRIPT_EXTENSIONS, subpath):
        if not rel.lower().endswith(UI_EXTENSIONS):
            text = _read(path)
            if text is not None and _REDUCED.search(text):
                reduced = True
            continue
        text = _read(path)
        if text is None:
            continue
        scanned += 1
        lines = text.splitlines()
        want_color = design_system is not None and not _is_token_file(rel, token_files)
        cands.extend(_scan_text(rel, text, lines, want_color))
        if _REDUCED.search(text):
            reduced = True
        if anim is None:
            for i, ln in enumerate(lines):
                if _ANIM.search(ln):
                    anim = f"{rel}:{i + 1}: {_snip(ln)}"[:SNIPPET_MAX]
                    break
    if anim and not reduced:
        cands.append(Candidate("no-reduced-motion", PROJECT, 1, anim,
                               CHECKS["no-reduced-motion"]["severity"]))
    return cands, scanned


# ─── audit document model (cp-ui --audit) ───────────────────────────────────

# Copied from cp-operation-pentest (severity word -> card priority).
SEVERITY_PRIORITY = {"critical": "Must", "high": "Must", "medium": "Should",
                     "low": "Could", "info": "Won't", "informational": "Won't"}
_SEVERITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1,
                  "informational": 1}
SOURCE = "cp-ui"
# Must agree with the `### <id>` headings of references/checklist.md (tested).
CHECKLIST_IDS = ("states-loading-empty-error", "width-360", "keyboard-main-flow",
                 "dark-mode", "touch-targets", "form-errors-inline", "focus-visible")
CHECKLIST_STATUSES = ("ok", "finding", "not-applicable", "not-verified")
ANSWERED = ("ok", "finding", "not-applicable")
REQUIRED_FIELDS = ("rule", "location", "evidence", "verdict", "severity")
DISMISSALS = ("ui", "dismissals.json")
VISUAL_NOT_CONFIGURED = "not configured"


@dataclass
class Finding:
    rule: str
    location: str
    evidence: str
    verdict: str
    severity: str

    @property
    def confirmed(self) -> bool:
        return is_confirmed(self.verdict)

    @property
    def dismissed(self) -> bool:
        return _first_token(self.verdict) == "dismissed"

    @property
    def reason(self) -> str:
        """Text after `dismissed —` / `cannot verify —`."""
        parts = re.split(r"\s*(?:—|–|:|\s-\s)\s*", self.verdict.strip(), maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""


def _first_token(verdict: str) -> str:
    norm = (verdict or "").strip().lower()
    return re.split(r"[\s:—–-]+", norm, maxsplit=1)[0] if norm else ""


def priority_of(severity: str) -> str:
    return SEVERITY_PRIORITY.get((severity or "").strip().lower(), "Should")


def severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get((severity or "").strip().lower(), 3)


def file_of(location: str) -> str:
    path = (location or "").split(":", 1)[0].strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def finding_file(f: Finding) -> str:
    """The grouping 'file' of a finding: the viewport for `visual:` rules (Location is
    `<viewport> <selector>`), the path before `:line` for everything else."""
    if f.rule.strip().startswith("visual:"):
        parts = (f.location or "").split()
        return parts[0] if parts else ""
    return file_of(f.location)


def group_key(f: Finding) -> str:
    return f"{f.rule.strip()}::{finding_file(f)}"


def fingerprint(text: str) -> str:
    return hashlib.sha1((text or "").strip()[:200].encode("utf-8")).hexdigest()


def candidate_key(c: Candidate) -> str:
    return f"{c.rule}::{c.file}::{fingerprint(c.snippet)}"


def _rule_valid(rule: str):
    rule = rule.strip()
    if rule in CHECKS:
        return None
    if rule.startswith("checklist:"):
        item = rule.split(":", 1)[1].strip()
        return None if item in CHECKLIST_IDS else f"unknown checklist item '{item}'"
    if rule.startswith("visual:") and rule.split(":", 1)[1].strip():
        return None
    return (f"unknown rule '{rule}' (use a static check id, checklist:<item-id> "
            f"or visual:<check>)")


def _parse_checklist(text: str, errors: list) -> dict:
    answers, inside = {}, False
    for line in (text or "").splitlines():
        if line.strip().startswith("## "):
            inside = line.strip().lower() == "## checklist"
            continue
        if not inside:
            continue
        m = re.match(r"^\s*[-*]\s*([\w-]+)\s*:\s*(.*?)\s*$", line)
        if not m:
            continue
        item, rest = m.group(1), m.group(2)
        if item not in CHECKLIST_IDS:
            errors.append(f"Checklist: unknown item '{item}' "
                          f"(valid: {', '.join(CHECKLIST_IDS)})")
            continue
        sm = re.match(r"(not-applicable|not-verified|finding|ok)\b\s*(?:[—–]|--?)?\s*(.*)$",
                      rest, re.I)
        if not sm:
            errors.append(f"Checklist: '{item}' needs one of {', '.join(CHECKLIST_STATUSES)}")
            continue
        status, evidence = sm.group(1).lower(), sm.group(2).strip()
        if status == "ok" and not evidence:  # no evidence, no `ok`
            status, evidence = "not-verified", "ok without evidence"
        answers[item] = (status, evidence)
    return answers


def parse_audit(text: str):
    """(findings, checklist answers {id: (status, evidence)}, errors)."""
    findings, errors = [], []
    for i, block in enumerate(_finding_blocks(text), 1):
        f = _fields(block)
        missing = [k for k in REQUIRED_FIELDS if not f.get(k)]
        if missing:
            errors.append(f"Finding #{i} is missing: {', '.join(missing)} "
                          f"(needs {', '.join(REQUIRED_FIELDS)})")
            continue
        bad = _rule_valid(f["rule"])
        if bad:
            errors.append(f"Finding #{i}: {bad}")
            continue
        fnd = Finding(f["rule"].strip(), f["location"], f["evidence"], f["verdict"],
                      f["severity"])
        if fnd.dismissed and not fnd.reason:
            errors.append(f"Finding #{i}: a dismissal needs a reason "
                          f"(`dismissed — <reason>`)")
            continue
        findings.append(fnd)
    answers = _parse_checklist(text, errors)
    have = {f.rule for f in findings}
    for item, (status, _) in answers.items():
        if status == "finding" and f"checklist:{item}" not in have:
            errors.append(f"Checklist: '{item}' is `finding` but there is no "
                          f"`## Finding` block with `Rule: checklist:{item}`")
    return findings, answers, errors


def header_line(files_scanned: int, visual_status: str, answers: dict,
                unaddressed: int = 0) -> str:
    """The honest first line of the report: what was and was not verified."""
    total = len(CHECKLIST_IDS)
    answered = sum(1 for k in CHECKLIST_IDS if answers.get(k, ("", ""))[0] in ANSWERED)
    extra = f", {unaddressed} candidates not addressed" if unaddressed else ""
    return (f"Verified — static: {files_scanned} files{extra} · visual: {visual_status} · "
            f"checklist: {answered}/{total} answered, {total - answered} not-verified")


def parse_checklist_doc(text: str) -> dict:
    """references/checklist.md -> {id: section body}, from its `### <id>` headings."""
    out, cur = {}, None
    for line in (text or "").splitlines():
        m = re.match(r"^###\s+(\S+)\s*$", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif line.startswith("#"):
            cur = None
        elif cur is not None:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


# ─── dismissals ──────────────────────────────────────────────────────────

def dismissals_path(context_dir) -> Path:
    return Path(context_dir).joinpath(*DISMISSALS)


def _load_dismissal_rows(context_dir) -> list:
    try:
        data = json.loads(dismissals_path(context_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def load_dismissals(context_dir) -> set:
    return {str(r.get("key", "")) for r in _load_dismissal_rows(context_dir)}


def match_candidate(f: Finding, candidates):
    """-> (candidate | None, error | None) for a finding about a static rule.

    Exact (rule, file, line) wins; else the (rule, file) candidates whose snippet is
    contained in the evidence (or vice versa); else, with no line in the Location, the
    only candidate of that (rule, file). Ambiguous or no match -> an error listing the
    current candidate lines so the agent can fix its Location."""
    rule, file = f.rule.strip(), file_of(f.location)
    pool = [c for c in candidates if c.rule == rule and c.file == file]
    line = f.location.split(":", 1)[1].split(":")[0].strip() if ":" in f.location else ""
    exact = [c for c in pool if line and str(c.line) == line]
    if exact:
        return exact[0], None
    ev = (f.evidence or "").strip()
    by_text = [c for c in pool if c.snippet.strip() and (c.snippet.strip() in ev
                                                          or (ev and ev in c.snippet))]
    if len(by_text) == 1:
        return by_text[0], None
    if not line and len(pool) == 1:
        return pool[0], None
    where = ", ".join(f"{c.file}:{c.line}" for c in pool) or "none"
    why = "ambiguous" if len(by_text) > 1 else "matches no current candidate"
    return None, (f"'{f.rule.strip()}' at {f.location} {why}; "
                  f"current candidates for {rule} in {file or '(no file)'}: {where}")


def check_dismissals(findings, candidates) -> list:
    """Errors for dismissed static-rule findings that would not hide any candidate."""
    return [err for f in findings if f.dismissed and f.rule.strip() in CHECKS
            for _, err in [match_candidate(f, candidates)] if err]


def record_dismissals(context_dir, findings, actor, candidates=()) -> list:
    """Persist `dismissed` findings (validate first with check_dismissals). The fingerprint
    is the matching candidate's snippet, so the next packet hides exactly that candidate;
    non-static rules (checklist/visual) have no candidate and use their evidence."""
    rows = _load_dismissal_rows(context_dir)
    seen = {r.get("key") for r in rows}
    added = []
    for f in findings:
        if not f.dismissed:
            continue
        file = finding_file(f)
        pick = match_candidate(f, candidates)[0] if f.rule.strip() in CHECKS else None
        fp = fingerprint(pick.snippet if pick else f.evidence)
        key = f"{f.rule.strip()}::{file}::{fp}"
        if key in seen:
            continue
        seen.add(key)
        row = {"key": key, "rule": f.rule.strip(), "file": file, "fingerprint": fp,
               "reason": f.reason, "by": actor or "agent",
               "at": now_utc()}
        rows.append(row)
        added.append(row)
    if added:
        path = dismissals_path(context_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return added


def unaddressed(findings, candidates, dismissed_keys) -> list:
    """In-scope candidates not dismissed earlier that no finding of this record covers."""
    covered = set()
    for f in findings:
        if f.rule.strip() in CHECKS:
            c, _ = match_candidate(f, candidates)
            if c is not None:
                covered.add(candidate_key(c))
    return [c for c in candidates
            if candidate_key(c) not in dismissed_keys and candidate_key(c) not in covered]


# ─── BUG cards ───────────────────────────────────────────────────────────

def open_bugs_by_key(context_dir) -> dict:
    """cp-ui BUGs not yet in 7-done, keyed by the `ui_key` stored in their meta."""
    from _shared import cards
    out = {}
    for card in cards.load_all(context_dir).values():
        key = str(card.meta.get("ui_key", ""))
        if (card.type == "bug" and card.meta.get("source") == SOURCE and key
                and card.status != "7-done"):
            out.setdefault(key, card)
    return out


def _rule_description(rule: str) -> str:
    if rule in CHECKS:
        return f"{CHECKS[rule]['summary']} ({CHECKS[rule]['ux_rule']})"
    if rule.startswith("checklist:"):
        return f"Checklist item '{rule.split(':', 1)[1]}' failed the audit"
    return f"Visual check '{rule.split(':', 1)[1]}' failed"


def occurrence(f: Finding) -> str:
    return f"{f.location} — {f.evidence}"


def bug_document(rule: str, file: str, group):
    """(title, body, priority) for the BUG of one (rule, file) group of confirmed findings."""
    top = max(group, key=lambda f: severity_rank(f.severity))
    seen, lines = set(), []
    for f in group:
        o = occurrence(f)
        if o not in seen:
            seen.add(o)
            lines.append(f"- {o}")
    body = ("## Symptom\n"
            f"{_rule_description(rule)}. Severity: {top.severity.strip()}. "
            f"Found by cp-ui --audit in {file}.\n\n"
            "## Reproduction\n" + "\n".join(lines) + "\n")
    return f"[ui] {rule} in {file}", body, priority_of(top.severity)


# ─── optional visual layer ───────────────────────────────────────────────

VISUAL_LAST = ("ui", "visual-last.json")
VISUAL_DEFAULT_TIMEOUT = 120
_VISUAL_FIELDS = ("check", "severity", "viewport", "selector", "detail", "screenshot")


def visual_last_path(context_dir) -> Path:
    return Path(context_dir).joinpath(*VISUAL_LAST)


def _failed(reason: str):
    return f"failed ({reason})", []


def _stderr_tail(raw) -> str:
    lines = [ln.strip() for ln in (raw or b"").decode("utf-8", "replace").splitlines() if ln.strip()]
    return lines[-1][:120] if lines else ""


def visual_command_line(project_root, profile):
    """(command, cwd) the visual layer would run, or None when not configured."""
    cfg = (profile or {}).get("visual_audit")
    if not isinstance(cfg, dict) or not str(cfg.get("command") or "").strip():
        return None
    return str(cfg["command"]).strip(), str(Path(project_root))


def run_visual(project_root, profile: dict):
    """Run the product's own visual-audit command -> (status, findings). Never raises and
    never starts or stops a server (the command is the product's)."""
    cfg = (profile or {}).get("visual_audit")
    if not isinstance(cfg, dict) or not str(cfg.get("command") or "").strip():
        return VISUAL_NOT_CONFIGURED, []
    root = Path(project_root)
    report = (root / str(cfg.get("report") or ".ui-audit/report.json")).resolve()
    try:
        report.relative_to(root.resolve())
    except ValueError:
        return _failed("report path outside project")
    timeout_s = cfg.get("timeout_s", VISUAL_DEFAULT_TIMEOUT)
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
        timeout_s = VISUAL_DEFAULT_TIMEOUT
    try:
        argv = shlex.split(str(cfg["command"]))
    except ValueError as e:
        return _failed(f"invalid command: {e}")
    if not argv:
        return VISUAL_NOT_CONFIGURED, []
    try:  # a stale report must never be mistaken for this run's
        report.unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        return _failed(f"cannot remove old report: {e}")
    try:
        proc = subprocess.run(argv, cwd=root, timeout=timeout_s, capture_output=True)
    except subprocess.TimeoutExpired:
        return _failed(f"timeout after {timeout_s:g}s")
    except FileNotFoundError:
        return _failed(f"command not found: {argv[0]}")
    except OSError as e:
        return _failed(f"cannot run {argv[0]}: {e}")
    if proc.returncode != 0:
        tail = _stderr_tail(proc.stderr)
        return _failed(f"exit code {proc.returncode}" + (f": {tail}" if tail else ""))
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _failed(f"report not found: {cfg.get('report') or '.ui-audit/report.json'}")
    except (OSError, ValueError) as e:
        return _failed(f"invalid report: {e}")
    if not isinstance(data, dict) or not isinstance(data.get("viewports"), list) \
            or not isinstance(data.get("findings"), list):
        return _failed("invalid report: expected an object with `viewports` and `findings` lists")
    findings = []
    for i, f in enumerate(data["findings"]):
        if not isinstance(f, dict) or not str(f.get("check") or "").strip():
            return _failed(f"invalid report: finding #{i + 1} has no `check`")
        findings.append({k: str(f.get(k) or "") for k in _VISUAL_FIELDS})
    return f"ran ({len(data['viewports'])} viewports)", findings


def report_viewports(project_root, profile) -> list:
    """Viewport names of the report the last `run_visual` just wrote (names only)."""
    cfg = (profile or {}).get("visual_audit") or {}
    try:
        data = json.loads((Path(project_root) / str(cfg.get("report")
                                                    or ".ui-audit/report.json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for v in data.get("viewports", []) if isinstance(data, dict) else []:
        name = v.get("name") if isinstance(v, dict) else v
        if isinstance(name, str):
            out.append(name)
    return out


def visual_location(v: dict) -> str:
    return f"{v['viewport']} {v['selector']}".strip()


def visual_evidence(v: dict) -> str:
    shot = f" (screenshot: {v['screenshot']})" if v.get("screenshot") else ""
    return f"{v['detail']}{shot}"


def save_visual_last(context_dir, status, scope, findings) -> bool:
    """Persist the run. On failure: try a minimal `not persisted` marker, else unlink the old
    file, warn on stderr — never leave an older `ran` behind. Returns True if persisted."""
    from datetime import datetime
    path = visual_last_path(context_dir)
    at = datetime.now().isoformat(timespec="seconds")

    def _write(st, fs):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": st, "at": at, "scope": scope or "",
                                    "findings": fs}, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    try:
        _write(status, findings)
        return True
    except OSError as e:
        print(f"warning: visual run not persisted ({path}: {e}) — the record will not claim a visual run",
              file=sys.stderr)
    try:
        _write("failed (visual run not persisted)", [])
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass
    return False


def load_visual_last(context_dir):
    try:
        data = json.loads(visual_last_path(context_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("status"), str) else None


def visual_status_for_record(context_dir, profile, scope):
    """(status, stored findings) for the record: only the last packet run for this scope can
    say `ran`; the record never re-runs the command."""
    last = load_visual_last(context_dir)
    if last is not None and (last.get("scope") or "") == (scope or ""):
        fs = [f for f in last.get("findings", []) if isinstance(f, dict)]
        return last["status"], [{k: str(f.get(k) or "") for k in _VISUAL_FIELDS} for f in fs]
    if not isinstance((profile or {}).get("visual_audit"), dict):
        return VISUAL_NOT_CONFIGURED, []
    return "failed (no visual run for this scope — run the packet first)", []


def unaddressed_visual(findings, visual_findings) -> list:
    """Stored visual findings that no `visual:<check>` finding of this record covers
    (same check and viewport, and the selector when the record names one)."""
    out = []
    for v in visual_findings:
        covered = False
        for f in findings:
            if f.rule.strip() != f"visual:{v['check']}":
                continue
            if finding_file(f) == v["viewport"] and (not v["selector"] or v["selector"] in f.location):
                covered = True
                break
        if not covered:
            out.append(v)
    return out


# ─── verify (re-check one UI BUG) ────────────────────────────────────────

def verify_path(context_dir, bug_id) -> Path:
    return Path(context_dir) / "ui" / "verify" / f"{bug_id}.json"


def verify_record(context_dir, bug_id):
    """The stored `--verify` record of a BUG, or None when missing or unreadable."""
    try:
        data = json.loads(verify_path(context_dir, bug_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def now_utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ts(value):
    """A timezone-aware datetime, or None (naive or unparsable values are not trusted)."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None and dt.utcoffset() is not None else None


def ui_verify_status(context_dir, card):
    """(record, None) when the record proves this cp-ui BUG's fix, else (record|None, why):
    same bug, same rule as the card's current ui_key, result pass, strictly after the start."""
    if card.type != "bug" or card.meta.get("source") != SOURCE:
        return None, "not a cp-ui BUG"
    rule = str(card.meta.get("ui_key", "")).partition("::")[0]
    rec = verify_record(context_dir, card.id)
    if rec is None:
        return None, "no verify record"
    if not rule:
        return rec, "the card has no ui_key"
    if rec.get("bug") != card.id:
        return rec, f"the record is for {rec.get('bug')}, not {card.id}"
    if rec.get("rule") != rule:
        return rec, f"the record re-checked rule {rec.get('rule')}, the BUG's rule is {rule}"
    if rec.get("result") != "pass":
        return rec, f"the re-check result is {rec.get('result')}"
    after, at = parse_ts(card.meta.get("ui_verify_after", "")), parse_ts(rec.get("at", ""))
    if after is None or at is None:
        return rec, "unparsable or timezone-less time (ui_verify_after / record at)"
    if not at > after:
        return rec, f"the record ({rec.get('at')}) is not after the start ({card.meta.get('ui_verify_after')})"
    return rec, None


def ui_verified(context_dir, card):
    """The verify record when it is valid for the card, else None."""
    rec, why = ui_verify_status(context_dir, card)
    return rec if why is None else None


def write_verify_record(context_dir, bug_id, rule, result, evidence) -> dict:
    rec = {"bug": bug_id, "rule": rule, "result": result,
           "at": now_utc(), "evidence": evidence}
    path = verify_path(context_dir, bug_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rec


def _dismissed_after_start(row, rule, file, after) -> bool:
    """A dismissal of this BUG's rule/file made after the fix started (or with a time we
    cannot trust) must not hide the candidate from the re-check."""
    if after is None or row.get("rule") != rule or file_of(str(row.get("file", ""))) != file:
        return False
    at = parse_ts(row.get("at", ""))
    return at is None or at > after


def dismissals_for(context_dir, rule, file) -> list:
    """Stored dismissals of a (rule, file): for reviewers to read next to a re-check."""
    return [r for r in _load_dismissal_rows(context_dir)
            if r.get("rule") == rule and file_of(str(r.get("file", ""))) == file_of(file)]


def verify_static(context_dir, project_root, exclude, rule, file, after=None):
    """(result, evidence): re-scan and look for non-dismissed candidates of rule in file."""
    from _shared import uikit
    ds = uikit.load_design_system(context_dir)
    want = file_of(file)
    why = scannable(project_root, want, exclude, ds, rule)
    if why:
        return "fail", f"cannot re-check: {why}"
    cands, _ = scan(project_root, exclude, ds)
    dismissed = {str(r.get("key", "")) for r in _load_dismissal_rows(context_dir)
                 if not _dismissed_after_start(r, rule, want, after)}
    left = [c for c in cands if c.rule == rule and file_of(c.file) == want
            and candidate_key(c) not in dismissed]
    if not left:
        return "pass", f"no `{rule}` candidates left in {want}"
    return "fail", "; ".join(f"{c.file}:{c.line}" for c in left[:5])


def verify_visual(project_root, profile, check, viewport):
    """(result, evidence) from a fresh run of the product's visual command."""
    status, findings = run_visual(project_root, profile)
    if not status.startswith("ran"):
        return "fail", status
    seen = report_viewports(project_root, profile)
    if viewport not in seen:
        return "fail", f"viewport {viewport} not exercised (report has: {', '.join(seen) or 'none'})"
    left = [v for v in findings if v["check"] == check and v["viewport"] == viewport]
    if not left:
        return "pass", f"{status}: no `{check}` in {viewport}"
    return "fail", "; ".join(visual_location(v) for v in left[:5])
