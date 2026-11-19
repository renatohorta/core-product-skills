"""cp-ui direction composer: n distinct, accessible directions + previews + MASTER draft."""
import json
import subprocess
import sys

import pytest

from conftest import SKILLS_DIR
from _shared import uikit

UI_SCRIPTS = SKILLS_DIR / "cp-ui" / "scripts"
sys.path.insert(0, str(UI_SCRIPTS))
import directions  # noqa: E402
import uupm  # noqa: E402

QUERY = "legal saas dashboard"
FILL = {"Chosen by:": "Renato", "Alternatives shown:": "A, B, C", "Why:": "fits the brand"}


def test_compose_returns_distinct_directions():
    ds = directions.compose(QUERY, "Acme")
    assert len(ds) >= 2
    assert [d["id"] for d in ds] == ["A", "B", "C"][:len(ds)]
    pairs = {(d["colors"]["primary"], d["typography"]["heading"]) for d in ds}
    assert len(pairs) == len(ds)


def test_compose_directions_are_accessible():
    for d in directions.compose(QUERY, "Acme"):
        c = d["colors"]
        for fg, bg in uikit.CONTRAST_PAIRS:
            if fg in c and bg in c and c[fg].startswith("#") and c[bg].startswith("#"):
                assert uikit.contrast_ratio(c[fg], c[bg]) >= uikit.MIN_CONTRAST


def test_compose_skips_inaccessible_palette(monkeypatch):
    m = uupm.load()
    real = m.core.search

    def fake(query, domain=None, max_results=10, **kw):
        out = real(query, domain, max_results, **kw)
        if domain == "color":
            bad = dict(out["results"][0])
            bad.update({"Primary": "#ABCDEF", "On Primary": "#ABCDEE",
                        "Foreground": "#EEEEEE", "Background": "#FFFFFF"})
            out = dict(out, results=[bad] + out["results"])
        return out

    monkeypatch.setattr(m.core, "search", fake)
    ds = directions.compose(QUERY, "Acme")
    assert ds and all(d["colors"]["primary"] != "#ABCDEF" for d in ds)


def test_n_limits_and_minimum_one():
    assert len(directions.compose(QUERY, "Acme", n=1)) == 1


def test_write_previews_creates_one_html_each(tmp_path):
    ds = directions.compose(QUERY, "Acme")
    paths = directions.write_previews(ds, tmp_path / "out")
    assert [p.name for p in paths] == [f"direction-{d['id']}.html" for d in ds]
    for p in paths:
        assert "<html" in p.read_text(encoding="utf-8").lower()


def test_to_master_round_trips_through_parse_master():
    d = directions.compose(QUERY, "Acme")[0]
    text = directions.to_master(d, "Acme")
    assert "## Decision" in text
    for label in FILL:
        assert label in text
    _, errors = uikit.parse_master(text)
    assert all(e.startswith("Decision:") for e in errors) and len(errors) == 3
    head, decision = text.split("## Decision")
    for label, value in FILL.items():
        decision = decision.replace(label, f"{label} {value}", 1)
    text = head + "## Decision" + decision
    system, errors = uikit.parse_master(text)
    assert errors == []
    assert system["colors"]["primary"].upper() == d["colors"]["primary"].upper()
    assert system["typography"]["heading"] == d["typography"]["heading"]
    assert set(system["colors"]) <= set(uikit.ROLES)


def test_composer_runs_offline_under_python_S_I(python_cmd, tmp_path):
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(UI_SCRIPTS)!r})\n"
        "import directions\n"
        f"ds = directions.compose({QUERY!r}, 'Acme')\n"
        f"ps = directions.write_previews(ds, __import__('pathlib').Path({str(tmp_path)!r}))\n"
        "print(json.dumps([len(ds), len(ps), directions.to_master(ds[0], 'Acme')[:20]]))\n"
    )
    r = subprocess.run([python_cmd, "-S", "-I", "-c", code],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    n, p, head = json.loads(r.stdout.strip().splitlines()[-1])
    assert n >= 2 and p == n and head.startswith("# Design system")
