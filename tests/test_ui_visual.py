"""cp-ui optional visual audit: run_visual, packet candidates, record header, template."""
import json
from pathlib import Path

from conftest import EXIT_OK, SKILLS_DIR
from test_context_persistence import run_skill

from _shared import cards, uicheck

REPORT = {"viewports": ["mobile-360", "desktop-1440"],
          "findings": [{"check": "horizontal-overflow", "severity": "High",
                        "viewport": "mobile-360", "selector": "div.hero",
                        "detail": "Page is 500px wide at 360px", "screenshot": ".ui-audit/s/m.png"}]}


def ui(args, env, python_cmd, stdin=None):
    return run_skill("cp-ui", args, env, python_cmd, stdin=stdin)


def _script(root: Path, name: str, body: str) -> str:
    (root / name).write_text(body, encoding="utf-8")
    return name


def _profile(py, command, **extra):
    return {"visual_audit": {"command": f'"{py}" {command}', "report": "out/report.json", **extra}}


WRITE = ("import json, pathlib\np = pathlib.Path('out'); p.mkdir(exist_ok=True)\n"
         f"(p / 'report.json').write_text(json.dumps({REPORT!r}))\n")


def test_visual_not_configured(tmp_path):
    assert uicheck.run_visual(tmp_path, {}) == ("not configured", [])
    assert uicheck.run_visual(tmp_path, {"visual_audit": {}}) == ("not configured", [])


def test_visual_ran_reads_findings(tmp_path, python_cmd):
    _script(tmp_path, "ok.py", WRITE)
    status, findings = uicheck.run_visual(tmp_path, _profile(python_cmd, "ok.py"))
    assert status == "ran (2 viewports)"
    assert findings[0]["check"] == "horizontal-overflow" and findings[0]["viewport"] == "mobile-360"


def test_visual_timeout_reports_failed(tmp_path, python_cmd):
    _script(tmp_path, "slow.py", "import time\ntime.sleep(30)\n")
    status, findings = uicheck.run_visual(tmp_path, _profile(python_cmd, "slow.py", timeout_s=1))
    assert status == "failed (timeout after 1s)" and findings == []


def test_visual_nonzero_exit_reports_failed(tmp_path, python_cmd):
    _script(tmp_path, "bad.py", "import sys\nsys.exit(2)\n")
    assert uicheck.run_visual(tmp_path, _profile(python_cmd, "bad.py"))[0] == "failed (exit code 2)"


def test_visual_missing_report_reports_failed(tmp_path, python_cmd):
    _script(tmp_path, "none.py", "pass\n")
    status, _ = uicheck.run_visual(tmp_path, _profile(python_cmd, "none.py"))
    assert status == "failed (report not found: out/report.json)"


def test_visual_stale_report_is_not_trusted(tmp_path, python_cmd):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "report.json").write_text(json.dumps(REPORT))
    _script(tmp_path, "none.py", "pass\n")
    assert uicheck.run_visual(tmp_path, _profile(python_cmd, "none.py"))[0].startswith("failed (report not found")


def test_visual_invalid_report_and_missing_command(tmp_path, python_cmd):
    _script(tmp_path, "junk.py", "import pathlib\np=pathlib.Path('out');p.mkdir(exist_ok=True)\n"
            "(p/'report.json').write_text('{nope')\n")
    assert uicheck.run_visual(tmp_path, _profile(python_cmd, "junk.py"))[0].startswith("failed (invalid report:")
    s, _ = uicheck.run_visual(tmp_path, {"visual_audit": {"command": "no-such-binary-xyz --a"}})
    assert s == "failed (command not found: no-such-binary-xyz)"


def _project(ctx_env, python_cmd, command="ok.py", scripts=True):
    ctx = Path(ctx_env["RUP_CONTEXT_DIR"])
    root = ctx.parent
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "A.tsx").write_text("<p>x</p>\n", encoding="utf-8")
    _script(root, "ok.py", WRITE)
    (ctx / "ui").mkdir(parents=True, exist_ok=True)
    (ctx / "ui" / "profile.json").write_text(json.dumps(_profile(python_cmd, command)))
    return ctx, root


def _finding(verdict="confirmed"):
    return ("## Finding\nRule: visual:horizontal-overflow\nLocation: mobile-360 div.hero\n"
            f"Evidence: Page is 500px wide\nVerdict: {verdict}\nSeverity: High\n\n")


def test_packet_lists_visual_candidates_and_persists(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env, python_cmd)
    r = ui(["--audit"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "visual: ran (2 viewports)" in r.stdout
    assert "Rule: visual:horizontal-overflow" in r.stdout
    assert "Location: mobile-360 div.hero" in r.stdout
    assert "(screenshot: .ui-audit/s/m.png)" in r.stdout
    last = json.loads((ctx / "ui" / "visual-last.json").read_text())
    assert last["status"] == "ran (2 viewports)" and last["scope"] == "" and last["at"]
    assert len(last["findings"]) == 1


def test_record_uses_last_run_and_opens_bug_per_viewport(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env, python_cmd)
    ui(["--audit"], ctx_env, python_cmd)
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd, stdin=_finding())
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "visual: ran (2 viewports)" in r.stdout
    bugs = [c for c in cards.load_all(ctx).values() if c.type == "bug"]
    assert [b.meta["ui_key"] for b in bugs] == ["visual:horizontal-overflow::mobile-360"]


def test_record_lists_unaddressed_visual_and_does_not_rerun(ctx_env, python_cmd):
    ctx, root = _project(ctx_env, python_cmd)
    ui(["--audit"], ctx_env, python_cmd)
    (root / "ok.py").write_text("raise SystemExit(9)\n")  # a re-run would now fail
    doc = "## Checklist\n- dark-mode: not-verified — x\n"
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd, stdin=doc)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "visual: ran (2 viewports)" in r.stdout
    report = sorted((ctx / "ui" / "audits").glob("*.md"))[-1].read_text()
    assert "visual candidate visual:horizontal-overflow at mobile-360 div.hero" in report


def test_record_without_run_never_claims_ran(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env, python_cmd)
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd, stdin=_finding("cannot verify — x"))
    assert "visual: failed (no visual run for this scope — run the packet first)" in r.stdout
    ui(["--audit"], ctx_env, python_cmd)  # scope "" now stored
    r = ui(["--audit", "--record", "-", "--path", "src"], ctx_env, python_cmd,
           stdin=_finding("cannot verify — x"))
    assert "failed (no visual run for this scope" in r.stdout


def test_record_not_configured_without_profile(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env, python_cmd)
    (ctx / "ui" / "profile.json").write_text("{}")
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd,
           stdin="## Checklist\n- dark-mode: not-verified — x\n")
    assert "visual: not configured" in r.stdout


def test_template_ui_audit_mjs():
    text = (SKILLS_DIR / "cp-ui" / "templates" / "ui-audit.mjs").read_text(encoding="utf-8")
    assert "--url" in text and "--file" not in text.replace("`--file` mode", "")
    for vp in ("mobile-360", "mobile-390", "tablet-768", "laptop-1024", "desktop-1440", "wide-1920"):
        assert vp in text
    for key in ("viewports", "findings", "check", "severity", "viewport", "selector",
                "detail", "screenshot", "report.json"):
        assert key in text
    assert "MIT" in text and "NextLevelBuilder" in text and "playwright install chromium" in text
