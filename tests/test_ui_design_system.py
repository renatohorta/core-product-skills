"""cp-ui --design-system packet and record."""
import json
from pathlib import Path

from conftest import EXIT_NEEDS_CONSENT, EXIT_OK
from test_context_persistence import run_skill

QUERY = "legal saas dashboard"
GOOD = """# Design system — Acme

## Style
Calm, dense, trustworthy.

## Colors
- primary: #1D4ED8
- on_primary: #FFFFFF
- background: #FFFFFF
- foreground: #111827

## Typography
- heading: Inter
- body: Inter

## Decision
Chosen by: Renato
Alternatives shown: A, B, C
Why: fits the brand
"""


def ui(args, env, python_cmd, stdin=None):
    return run_skill("cp-ui", args, env, python_cmd, stdin=stdin)


def _ctx(env):
    return Path(env["RUP_CONTEXT_DIR"])


def _doc(tmp_path, text=GOOD):
    p = tmp_path / "master.md"
    p.write_text(text, encoding="utf-8")
    return str(p)


def _record(env, python_cmd, tmp_path, *extra, text=GOOD):
    return ui(["--design-system", "--record", _doc(tmp_path, text), *extra], env, python_cmd)


def test_packet_lists_directions_and_preview_paths(ctx_env, python_cmd, tmp_path):
    out = tmp_path / "prev"
    r = ui(["--design-system", QUERY, "--out", str(out)], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "Direction A" in r.stdout and "Direction B" in r.stdout
    assert str(out / "direction-A.html") in r.stdout
    assert (out / "direction-A.html").is_file()
    assert "## Decision" in r.stdout and "--record" in r.stdout
    assert "none — ask the operator" in r.stdout
    assert "side by side" in r.stdout


def test_packet_says_unknown_stack_when_none_detected(ctx_env, python_cmd):
    r = ui(["--design-system", QUERY], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "unknown — ask" in r.stdout


def test_packet_detects_stack_and_discovery(ctx_env, python_cmd):
    ctx = _ctx(ctx_env)
    (ctx.parent / "package.json").write_text(
        json.dumps({"dependencies": {"react": "18"}}), encoding="utf-8")
    d = ctx / "docs" / "01-inception"
    d.mkdir(parents=True)
    (d / "cp-discover.md").write_text("# Disc\n\nA tool for lawyers to track cases.\n",
                                      encoding="utf-8")
    r = ui(["--design-system"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "react" in r.stdout and "lawyers" in r.stdout


def test_packet_without_briefing_or_discovery_exits_1(ctx_env, python_cmd):
    assert ui(["--design-system"], ctx_env, python_cmd).returncode == 1


def test_packet_works_without_authorization(ctx_env, python_cmd):
    (_ctx(ctx_env) / ".rup-standard").unlink()
    assert ui(["--design-system", QUERY], ctx_env, python_cmd).returncode == EXIT_OK


def test_record_writes_master_and_tokens(ctx_env, python_cmd, tmp_path):
    r = _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "renato")
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    ds = _ctx(ctx_env) / "design-system"
    assert "Chosen by: Renato" in (ds / "MASTER.md").read_text(encoding="utf-8")
    tokens = json.loads((ds / "tokens.json").read_text(encoding="utf-8"))
    assert tokens["color"]["primary"]["$value"] == "#1D4ED8"


def test_record_without_chosen_by_exits_1(ctx_env, python_cmd, tmp_path):
    r = _record(ctx_env, python_cmd, tmp_path)
    assert r.returncode == 1
    assert not (_ctx(ctx_env) / "design-system" / "MASTER.md").exists()


def test_record_chosen_by_mismatch_exits_1(ctx_env, python_cmd, tmp_path):
    assert _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Bob").returncode == 1


def test_record_invalid_document_exits_1(ctx_env, python_cmd, tmp_path):
    r = _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Renato",
                text=GOOD.replace("#111827", "#EEEEEE"))
    assert r.returncode == 1 and "Contrast" in r.stdout


def test_record_refuses_overwrite_without_force(ctx_env, python_cmd, tmp_path):
    assert _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Renato").returncode == 0
    master = _ctx(ctx_env) / "design-system" / "MASTER.md"
    before = master.read_bytes()
    other = GOOD.replace("#1D4ED8", "#0B3D91")
    r = _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Renato", text=other)
    assert r.returncode == 1
    assert master.read_bytes() == before


def test_record_force_requires_reason(ctx_env, python_cmd, tmp_path):
    assert _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Renato").returncode == 0
    assert _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Renato",
                   "--force").returncode == 1
    r = _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Renato", "--force",
                "--reason", "rebrand")
    assert r.returncode == 0, r.stdout
    dec = (_ctx(ctx_env) / "tracking" / "decisions.md").read_text(encoding="utf-8")
    assert "rebrand" in dec


def test_record_appends_decision_entry(ctx_env, python_cmd, tmp_path):
    _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Renato")
    ctx = _ctx(ctx_env)
    dec = (ctx / "tracking" / "decisions.md").read_text(encoding="utf-8")
    assert "## Design system — Acme (" in dec
    assert "Chosen by: Renato" in dec and "fits the brand" in dec and "A, B, C" in dec
    assert "cp-ui" in (ctx / "tracking" / "rup-log.md").read_text(encoding="utf-8")


def test_record_page_leaves_master_and_tokens(ctx_env, python_cmd, tmp_path):
    assert _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Renato").returncode == 0
    ds = _ctx(ctx_env) / "design-system"
    master, tokens = ds / "MASTER.md", ds / "tokens.json"
    mb, tb = master.read_bytes(), tokens.read_bytes()
    other = GOOD.replace("#1D4ED8", "#0B3D91")
    r = _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Renato", "--page",
                "Landing Page", text=other)
    assert r.returncode == 0, r.stdout
    assert (ds / "pages" / "landing-page.md").is_file()
    assert master.read_bytes() == mb and tokens.read_bytes() == tb
    again = _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Renato", "--page",
                    "landing page", text=other)
    assert again.returncode == 1


def test_record_without_authorization_exits_5(ctx_env, python_cmd, tmp_path):
    (_ctx(ctx_env) / ".rup-standard").unlink()
    r = _record(ctx_env, python_cmd, tmp_path, "--chosen-by", "Renato")
    assert r.returncode == EXIT_NEEDS_CONSENT
    assert not (_ctx(ctx_env) / "design-system").exists()
