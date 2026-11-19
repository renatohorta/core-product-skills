"""cp-ui direction composer — n distinct, accessible design directions, offline.

    compose(query, project, n=3)      -> [UUPM-shaped design-system dict + "id"]
    write_previews(directions, dir)   -> [dir/direction-<id>.html]
    to_master(direction, product)     -> MASTER.md draft (empty ## Decision)

Each direction is a vendored-generator base (variance 2 / 6 / 9) whose colors and
typography are replaced by the k-th ranked palette / font pairing. Palettes whose
declared text pairs fall below WCAG AA (4.5:1) are skipped, never proposed.
Stdlib only; never calls a model.
"""
import re
import sys
from pathlib import Path

# _shared/ sits in the skills root: next to this skill (repo, Claude Code) or one
# level up when the agent nests skills in a category (Hermes: skills/<category>/).
_SKILL_DIR = Path(__file__).resolve().parent.parent
for _root in (_SKILL_DIR.parent, _SKILL_DIR.parent.parent):
    if (_root / "_shared" / "uikit.py").is_file():
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        break
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import uupm  # noqa: E402
from _shared import uikit  # noqa: E402

VARIANCES = (2, 6, 9)
IDS = ("A", "B", "C")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
# (colors.csv column, role) — same mapping DesignSystemGenerator.generate() uses.
_COLOR_COLUMNS = (
    ("Primary", "primary"), ("On Primary", "on_primary"),
    ("Secondary", "secondary"), ("On Secondary", "on_secondary"),
    ("Accent", "accent"), ("On Accent", "on_accent"),
    ("Background", "background"), ("Foreground", "foreground"),
    ("Card", "card"), ("Card Foreground", "card_foreground"),
    ("Muted", "muted"), ("Muted Foreground", "muted_foreground"),
    ("Border", "border"), ("Destructive", "destructive"),
    ("On Destructive", "on_destructive"), ("Ring", "ring"),
)
_MAX_ROWS = 5


def _colors_from_row(row):
    colors = {role: row.get(col, "") for col, role in _COLOR_COLUMNS}
    colors["notes"] = row.get("Notes", "")
    # legacy keys the vendored preview/formatters still read
    colors["cta"] = row.get("Accent", "")
    colors["text"] = row.get("Foreground", "")
    colors["on_cta"] = row.get("On Accent", "")
    return colors


def _typography_from_row(row):
    return {
        "heading": row.get("Heading Font", "Inter"),
        "body": row.get("Body Font", "Inter"),
        "mood": row.get("Mood/Style Keywords", ""),
        "best_for": row.get("Best For", ""),
        "google_fonts_url": row.get("Google Fonts URL", ""),
        "css_import": row.get("CSS Import", ""),
        "tailwind_config": row.get("Tailwind Config", ""),
        "category": row.get("Category", ""),
    }


def _accessible(colors):
    """Required roles are valid hex and every declared (both present) text pair passes."""
    if not all(_HEX.match(colors.get(r, "")) for r in uikit.REQUIRED_COLORS):
        return False
    for fg, bg in uikit.CONTRAST_PAIRS:
        a, b = colors.get(fg, ""), colors.get(bg, "")
        if _HEX.match(a) and _HEX.match(b) and uikit.contrast_ratio(a, b) < uikit.MIN_CONTRAST:
            return False
    return True


def _rows(m, query, domain):
    return m.core.search(query, domain, max_results=_MAX_ROWS).get("results", [])


def _collect(m, query, palettes, pal_seen, fonts, font_seen):
    for row in _rows(m, query, "color"):
        colors = _colors_from_row(row)
        key = (colors["primary"].upper(), colors["background"].upper())
        if _accessible(colors) and key not in pal_seen:
            pal_seen.add(key)
            palettes.append(colors)
    for row in _rows(m, query, "typography"):
        typo = _typography_from_row(row)
        key = (typo["heading"], typo["body"])
        if key not in font_seen:
            font_seen.add(key)
            fonts.append(typo)


def compose(query, project, n=3, fallback=None):
    """Up to n (max 3) directions; fewer when the data yields fewer usable rows.

    With `fallback` (a broader query), a thin match (< 2 usable palettes or fonts) is
    topped up from it; those directions carry `fallback: True` so the packet can say so.
    """
    m = uupm.load()
    palettes, pal_seen, fonts, font_seen = [], set(), [], set()
    _collect(m, query, palettes, pal_seen, fonts, font_seen)
    matched = min(len(palettes), len(fonts))
    if fallback and matched < min(2, n):
        _collect(m, fallback, palettes, pal_seen, fonts, font_seen)
    count = min(max(1, n), len(IDS), len(palettes), len(fonts))
    gen = m.design_system.DesignSystemGenerator()
    out = []
    for k in range(count):
        d = gen.generate(query, project_name=project, variance=VARIANCES[k])
        d["colors"], d["typography"], d["id"] = palettes[k], fonts[k], IDS[k]
        d["fallback"] = k >= matched
        out.append(d)
    return out


def write_previews(directions, out_dir):
    m = uupm.load()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for d in directions:
        path = out_dir / f"direction-{d['id']}.html"
        path.write_text(m.preview.format_preview_html(d), encoding="utf-8")
        paths.append(path)
    return paths


def _para(text):
    return " ".join(str(text or "").split())


def to_master(direction, product):
    """MASTER.md draft; the operator fills the three ## Decision values."""
    style = direction.get("style") or {}
    summary = _para(style.get("name"))
    extra = _para(style.get("keywords"))
    desc = f"{summary}. {extra}".strip(". ") if extra else summary
    colors = direction.get("colors") or {}
    typo = direction.get("typography") or {}
    lines = [f"# Design system — {product}", "", "## Style",
             f"{desc or 'TBD'} (direction {direction.get('id', '?')})", "", "## Colors"]
    for role in uikit.ROLES:
        value = str(colors.get(role, "")).strip()
        if _HEX.match(value):
            lines.append(f"- {role}: {value}")
    lines += ["", "## Typography",
              f"- heading: {typo.get('heading', '')}",
              f"- body: {typo.get('body', '')}"]
    anti = _para(direction.get("anti_patterns"))
    if anti:
        lines += ["", "## Anti-patterns", anti]
    lines += ["", "## Decision", "Chosen by:", "Alternatives shown:", "Why:", ""]
    return "\n".join(lines)
