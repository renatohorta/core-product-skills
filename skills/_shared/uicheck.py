#!/usr/bin/env python3
"""
uicheck.py — static UI checks (cp-ui). Pure functions, stdlib only.

Line-based regexes over UI source files (html/css/scss/jsx/tsx/vue/svelte/astro).
Findings are *candidates*: a human or the visual pass confirms them. A backend-only
project scans zero files and returns ([], 0) — never a clean bill of health.

Public surface (stable): UI_EXTENSIONS, Candidate, CHECKS, scan.
Must not import `uikit` (uikit imports this module).
"""
import os
import re
from dataclasses import dataclass
from pathlib import Path

from _shared.auditclosure import _matches

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
_FUNC_COLOR = re.compile(r"\b(?:rgba?|hsla?)\(")
_CSS_VAR_DEF = re.compile(r"^\s*(?:--[\w-]+|\$[\w-]+)\s*:")
_VAR_DEF_INLINE = re.compile(r"(?<![\w-])--[\w-]+\s*:\s*[^;}]*")
_IMG = re.compile(r"<img\b", re.I)
_BUTTON = re.compile(r"<button\b([^>]*)>(.*?)</button>", re.I)
_NAME_ATTR = re.compile(r"aria-label(?:ledby)?\s*=|\btitle\s*=", re.I)
_OUTLINE = re.compile(r"(?<![\w-])outline-none\b|\boutline\s*:\s*(?:none|0)\b")
_OUTLINE_OK = re.compile(r"focus-visible|focus:ring|focus:outline|focus:border|\bring-|:focus\b.*(?:box-shadow|border)")
_ZOOM = re.compile(r"user-scalable\s*=\s*(?:no|0)\b|maximum-scale\s*=\s*1(?:\.0+)?(?![\d.])", re.I)
_HTML_TAG = re.compile(r"<html\b", re.I)
_VIEWPORT = re.compile(r"""name\s*=\s*["']?viewport""", re.I)
_FONT_CSS = re.compile(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", re.I)
_FONT_TW = re.compile(r"text-\[(\d+(?:\.\d+)?)px\]")
_EMOJI = ("[\U0001F000-\U0001FAFF☀-➿⭐⭕⌚⌛⏩-⏳]")
_EMOJI_ICON = re.compile(r"<(?:button|a|li|NavLink|Link)\b[^>]*>\s*" + _EMOJI, re.I)
_ANIM = re.compile(r"@keyframes|\banimation(?:-name)?\s*:|\banimate-[a-z]|framer-motion|\bmotion\.\w")
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


def _read(path: Path):
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def _iter_files(root: Path, exclude):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
        for name in sorted(filenames):
            if not name.lower().endswith(UI_EXTENSIONS):
                continue
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
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
        for m in _IMG.finditer(ln):
            if not re.search(r"\balt\b", _tag_window(lines, i, m.start()), re.I):
                flagged.add("img-no-alt")
        for m in _BUTTON.finditer(ln):
            inner = m.group(2)
            if (not _NAME_ATTR.search(m.group(1)) and "sr-only" not in inner
                    and re.search(r"<\w", inner)
                    and not re.sub(r"<[^>]*>|\s+", "", inner)):
                flagged.add("icon-button-no-name")
        if _OUTLINE.search(ln) and not _OUTLINE_OK.search(ln):
            flagged.add("outline-removed")
        if _ZOOM.search(ln):
            flagged.add("zoom-disabled")
        if any(float(v) < 12 for v in _FONT_CSS.findall(ln) + _FONT_TW.findall(ln)):
            flagged.add("tiny-font")
        if _EMOJI_ICON.search(ln):
            flagged.add("emoji-icon")
        if want_color and _raw_color(ln):
            flagged.add("raw-color")
        for rule in CHECKS:  # stable order
            if rule in flagged:
                add(rule, i)
    return out


def scan(project_root, exclude, design_system):
    """-> (candidates, files scanned). Backend-only projects give ([], 0)."""
    root = Path(project_root)
    token_files = (design_system or {}).get("token_files", []) or []
    cands, scanned = [], 0
    anim = None
    reduced = False
    for path, rel in _iter_files(root, exclude or []):
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
