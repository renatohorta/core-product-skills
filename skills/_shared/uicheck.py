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
            if any(_matches(p, rel) for p in exclude if p):
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


def group_key(f: Finding) -> str:
    return f"{f.rule.strip()}::{file_of(f.location)}"


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
    from datetime import datetime
    rows = _load_dismissal_rows(context_dir)
    seen = {r.get("key") for r in rows}
    added = []
    for f in findings:
        if not f.dismissed:
            continue
        file = file_of(f.location)
        pick = match_candidate(f, candidates)[0] if f.rule.strip() in CHECKS else None
        fp = fingerprint(pick.snippet if pick else f.evidence)
        key = f"{f.rule.strip()}::{file}::{fp}"
        if key in seen:
            continue
        seen.add(key)
        row = {"key": key, "rule": f.rule.strip(), "file": file, "fingerprint": fp,
               "reason": f.reason, "by": actor or "agent",
               "at": datetime.now().isoformat(timespec="seconds")}
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
