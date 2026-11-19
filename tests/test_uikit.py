"""`_shared/uikit.py` — MASTER.md parse, validate, DTCG tokens."""
import pytest

from _shared import uikit

GOOD = """\
# Design system — Acme
## Style
Calm and dense.
## Colors
- primary: #1D4ED8
- on_primary: #FFFFFF
- background: #FFFFFF
- foreground: #111111
## Typography
- heading: Fraunces
- body: Inter
## Spacing
4px base
## Decision
Chosen by: Renato
Alternatives shown: A, B, C
Why: fits the brand
"""


def test_parse_master_reads_roles_and_fonts():
    s, errors = uikit.parse_master(GOOD)
    assert errors == []
    assert s["style"] == "Calm and dense."
    assert s["colors"]["primary"] == "#1D4ED8"
    assert s["typography"] == {"heading": "Fraunces", "body": "Inter"}
    assert s["decision"]["chosen_by"] == "Renato"
    assert s["spacing"] == "4px base"


def test_parse_master_reports_missing_required_role():
    _, errors = uikit.parse_master(GOOD.replace("- foreground: #111111\n", ""))
    assert any("foreground" in e for e in errors)


def test_parse_master_rejects_bad_hex():
    _, errors = uikit.parse_master(GOOD.replace("#1D4ED8", "#12345"))
    assert any("primary" in e and "#12345" in e for e in errors)


def test_unknown_role_is_an_error():
    _, errors = uikit.parse_master(GOOD.replace("## Typography", "- sparkle: #FFFFFF\n## Typography"))
    assert any("sparkle" in e for e in errors)


def test_low_contrast_pair_is_an_error():
    _, errors = uikit.parse_master(GOOD.replace("#111111", "#999999"))
    assert any("foreground" in e and "background" in e and "2.85" in e and "4.5" in e
               for e in errors)


def test_contrast_ratio_black_white_is_21():
    assert uikit.contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)


def test_tokens_from_system_shape():
    s, _ = uikit.parse_master(GOOD)
    t = uikit.tokens_from_system(s)
    assert t["color"]["primary"] == {"$type": "color", "$value": "#1D4ED8"}
    assert t["font"]["heading"] == {"$type": "fontFamily", "$value": "Fraunces"}


def test_missing_decision_chosen_by_is_an_error():
    _, errors = uikit.parse_master(GOOD.replace("Chosen by: Renato\n", ""))
    assert any("Chosen by" in e for e in errors)


def test_load_design_system(tmp_path):
    assert uikit.load_design_system(tmp_path) is None
    uikit.ds_dir(tmp_path).mkdir()
    (uikit.ds_dir(tmp_path) / "MASTER.md").write_text("## Colors\n- primary: nope\n", encoding="utf-8")
    assert uikit.load_design_system(tmp_path)["colors"] == {"primary": "nope"}
