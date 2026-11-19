"""cp-ui: parse and validate the design-system MASTER.md, derive DTCG tokens.

Standard library only. MASTER.md is written by the agent (`## Style`, `## Colors`,
`## Typography`, optional `## Spacing`/`## Motion`/`## Anti-patterns`, `## Decision`).
"""
import re
from pathlib import Path

ROLES = ("primary", "on_primary", "secondary", "on_secondary", "accent", "on_accent",
         "background", "foreground", "card", "card_foreground", "muted",
         "muted_foreground", "border", "destructive", "on_destructive", "ring")
REQUIRED_COLORS = ("primary", "on_primary", "background", "foreground")
CONTRAST_PAIRS = (("foreground", "background"), ("on_primary", "primary"),
                  ("card_foreground", "card"), ("muted_foreground", "background"))
MIN_CONTRAST = 4.5

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_KV = re.compile(r"^\s*[-*]\s*([A-Za-z_][\w ]*?)\s*:\s*(.*?)\s*$")
_DECISION = (("chosen_by", "Chosen by"), ("alternatives", "Alternatives shown"), ("why", "Why"))


def _sections(text):
    """Map lowercase `## heading` -> body text (stripped)."""
    out, name, buf = {}, None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if name is not None:
                out.setdefault(name, "\n".join(buf).strip())
            name, buf = line[3:].strip().lower(), []
        elif name is not None:
            buf.append(line)
    if name is not None:
        out.setdefault(name, "\n".join(buf).strip())
    return out


def _bullets(body):
    pairs = []
    for line in body.splitlines():
        m = _KV.match(line)
        if m:
            pairs.append((m.group(1).strip().lower().replace(" ", "_"), m.group(2)))
    return pairs


def _lum(hex_color):
    def chan(i):
        c = int(hex_color[1 + 2 * i:3 + 2 * i], 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * chan(0) + 0.7152 * chan(1) + 0.0722 * chan(2)


def contrast_ratio(a, b):
    """WCAG 2 contrast ratio of two #RRGGBB colors."""
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def parse_master(text):
    secs = _sections(text)
    errors = []

    colors = {}
    for role, value in _bullets(secs.get("colors", "")):
        if role not in ROLES:
            errors.append(f"Colors: unknown role '{role}'")
        else:
            colors[role] = value
    for role in REQUIRED_COLORS:
        if role not in colors:
            errors.append(f"Colors: missing required role '{role}'")
    for role, value in colors.items():
        if not _HEX.match(value):
            errors.append(f"Colors: '{role}' must be a #RRGGBB hex, got '{value}'")
    for fg, bg in CONTRAST_PAIRS:
        if fg in colors and bg in colors and _HEX.match(colors[fg]) and _HEX.match(colors[bg]):
            ratio = contrast_ratio(colors[fg], colors[bg])
            if ratio < MIN_CONTRAST:
                errors.append(f"Contrast: {fg} on {bg} is {ratio:.2f}:1, "
                              f"below the {MIN_CONTRAST} minimum")

    typo = dict(_bullets(secs.get("typography", "")))
    typography = {"heading": typo.get("heading", ""), "body": typo.get("body", "")}
    for k in ("heading", "body"):
        if not typography[k]:
            errors.append(f"Typography: missing '{k}' font")

    dec_raw = {k.lower(): v for k, v in
               (m.groups() for m in (re.match(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$", l)
                                     for l in secs.get("decision", "").splitlines()) if m)}
    decision = {}
    for key, label in _DECISION:
        decision[key] = dec_raw.get(label.lower(), "")
        if not decision[key]:
            errors.append(f"Decision: missing '{label}'")

    style = secs.get("style", "")
    if not style:
        errors.append("Style: section is missing or empty")

    system = {"style": style, "colors": colors, "typography": typography,
              "decision": decision, "spacing": secs.get("spacing", ""),
              "motion": secs.get("motion", ""),
              "anti_patterns": secs.get("anti-patterns", "")}
    return system, errors


def tokens_from_system(system):
    tokens = {"color": {r: {"$type": "color", "$value": v}
                        for r, v in system.get("colors", {}).items()},
              "font": {}}
    for k, v in system.get("typography", {}).items():
        if v:
            tokens["font"][k] = {"$type": "fontFamily", "$value": v}
    return tokens


def ds_dir(context_dir):
    return Path(context_dir) / "design-system"


def load_design_system(context_dir):
    path = ds_dir(context_dir) / "MASTER.md"
    if not path.is_file():
        return None
    return parse_master(path.read_text(encoding="utf-8"))[0]
