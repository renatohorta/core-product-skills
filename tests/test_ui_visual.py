"""cp-ui optional visual audit: run_visual, packet candidates, record header, template."""
import json
import shutil
import subprocess
import pytest
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
    r = ui(["--audit", "--visual"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "visual: ran (2 viewports)" in r.stdout
    assert "Rule: visual:horizontal-overflow" in r.stdout
    assert "Location: mobile-360 div.hero" in r.stdout
    assert "(screenshot: .ui-audit/s/m.png)" in r.stdout
    last = json.loads((ctx / "ui" / "visual-last.json").read_text())
    assert last["status"] == "ran (2 viewports)" and last["scope"] == "" and last["at"]
    assert len(last["findings"]) == 1


def test_record_uses_last_run_and_opens_one_bug_per_check(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env, python_cmd)
    ui(["--audit", "--visual"], ctx_env, python_cmd)
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd, stdin=_finding())
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "visual: ran (2 viewports)" in r.stdout
    bugs = [c for c in cards.load_all(ctx).values() if c.type == "bug"]
    assert [b.meta["ui_key"] for b in bugs] == ["visual:horizontal-overflow::(page)"]
    assert bugs[0].meta["ui_viewports"] == "mobile-360"


def test_record_lists_unaddressed_visual_and_does_not_rerun(ctx_env, python_cmd):
    ctx, root = _project(ctx_env, python_cmd)
    ui(["--audit", "--visual"], ctx_env, python_cmd)
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
    ui(["--audit", "--visual"], ctx_env, python_cmd)  # scope "" now stored
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


def test_packet_without_visual_does_not_run_and_says_skipped(ctx_env, python_cmd):
    ctx, root = _project(ctx_env, python_cmd, command="marker.py")
    _script(root, "marker.py", "import pathlib\npathlib.Path('ran.marker').write_text('x')\n")
    r = ui(["--audit"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert not (root / "ran.marker").exists()
    assert "visual: skipped (--visual not given)" in r.stdout
    last = json.loads((ctx / "ui" / "visual-last.json").read_text())
    assert last["status"] == "skipped (--visual not given)"


def test_skipped_packet_invalidates_older_ran(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env, python_cmd)
    ui(["--audit", "--visual"], ctx_env, python_cmd)
    ui(["--audit"], ctx_env, python_cmd)
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd,
           stdin="## Checklist\n- dark-mode: not-verified — x\n")
    assert "visual: skipped (--visual not given)" in r.stdout and "visual: ran" not in r.stdout


def test_packet_without_visual_and_no_profile_not_configured(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env, python_cmd)
    (ctx / "ui" / "profile.json").write_text("{}")
    r = ui(["--audit"], ctx_env, python_cmd)
    assert "visual: not configured" in r.stdout


def test_packet_visual_prints_command_and_cwd(ctx_env, python_cmd):
    ctx, root = _project(ctx_env, python_cmd)
    r = ui(["--audit", "--visual"], ctx_env, python_cmd)
    assert "ok.py" in r.stdout.split("Running visual audit")[1].split("\n")[0:3].__str__()
    assert str(root) in r.stdout


def test_record_prints_visual_run_at(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env, python_cmd)
    ui(["--audit", "--visual"], ctx_env, python_cmd)
    at = json.loads((ctx / "ui" / "visual-last.json").read_text())["at"]
    ui(["--audit", "--record", "-"], ctx_env, python_cmd,
       stdin="## Checklist\n- dark-mode: not-verified — x\n")
    lines = sorted((ctx / "ui" / "audits").glob("*.md"))[-1].read_text().splitlines()
    assert lines[1] == f"Visual run at: {at}"


def _load_run():
    import importlib.util
    spec = importlib.util.spec_from_file_location("cpui_run", SKILLS_DIR / "cp-ui" / "scripts" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, str(SKILLS_DIR))
    sys.path.insert(0, str(SKILLS_DIR / "cp-ui" / "scripts"))
    spec.loader.exec_module(mod)
    return mod


def test_persist_failure_never_leaves_older_ran(ctx_env, python_cmd, monkeypatch, capsys):
    ctx, root = _project(ctx_env, python_cmd)
    ui(["--audit", "--visual"], ctx_env, python_cmd)  # pre-existing "ran"
    assert json.loads((ctx / "ui" / "visual-last.json").read_text())["status"].startswith("ran")
    real = Path.write_text
    state = {"n": 0}

    def flaky(self, *a, **k):
        if self.name == "visual-last.json":
            state["n"] += 1
            if state["n"] == 1:
                raise OSError("disk full")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "write_text", flaky)
    uicheck.save_visual_last(ctx, "ran (2 viewports)", "", [])
    assert "visual run not persisted" in capsys.readouterr().err
    status, _ = uicheck.visual_status_for_record(ctx, {"visual_audit": {}}, "")
    assert status == "failed (visual run not persisted)"


def test_persist_total_failure_removes_old_file(ctx_env, python_cmd, monkeypatch, capsys):
    ctx, _ = _project(ctx_env, python_cmd)
    ui(["--audit", "--visual"], ctx_env, python_cmd)
    real = Path.write_text
    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: (_ for _ in ()).throw(OSError("ro"))
                        if self.name == "visual-last.json" else real(self, *a, **k))
    uicheck.save_visual_last(ctx, "ran (2 viewports)", "", [])
    assert "not persisted" in capsys.readouterr().err
    status, _ = uicheck.visual_status_for_record(ctx, {"visual_audit": {}}, "")
    assert not status.startswith("ran")


def test_stale_other_scope_not_ran(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env, python_cmd)
    uicheck.save_visual_last(ctx, "ran (2 viewports)", "other", [])
    status, _ = uicheck.visual_status_for_record(ctx, {"visual_audit": {"command": "x"}}, "")
    assert not status.startswith("ran")


def test_report_path_outside_project_fails_and_is_not_unlinked(tmp_path, python_cmd):
    root = tmp_path / "proj"
    root.mkdir()
    victim = tmp_path / "x.json"
    victim.write_text("keep")
    _script(root, "ok.py", "pass\n")
    prof = {"visual_audit": {"command": f'"{python_cmd}" ok.py', "report": "../x.json"}}
    assert uicheck.run_visual(root, prof) == ("failed (report path outside project)", [])
    assert victim.read_text() == "keep"


def test_exit_code_failure_includes_stderr_tail(tmp_path, python_cmd):
    _script(tmp_path, "bad.py", "import sys\nprint('x', file=sys.stderr)\n"
            "print('Error: net::ERR_CONNECTION_REFUSED', file=sys.stderr)\nsys.exit(1)\n")
    status, _ = uicheck.run_visual(tmp_path, _profile(python_cmd, "bad.py"))
    assert status == "failed (exit code 1: Error: net::ERR_CONNECTION_REFUSED)"
    _script(tmp_path, "long.py", "import sys\nprint('y'*500, file=sys.stderr)\nsys.exit(3)\n")
    status, _ = uicheck.run_visual(tmp_path, _profile(python_cmd, "long.py"))
    assert len(status) < 160 and status.startswith("failed (exit code 3: yyy")


def test_template_hardening_and_node_check():
    path = SKILLS_DIR / "cp-ui" / "templates" / "ui-audit.mjs"
    text = path.read_text(encoding="utf-8")
    assert "finally" in text and "is the app running?" in text and "response.ok()" in text.replace("resp.ok()", "response.ok()")
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


VPS = ["mobile-360", "mobile-390", "tablet-768", "laptop-1024", "desktop-1440", "wide-1920"]
SIX = {"viewports": VPS,
       "findings": [{"check": "horizontal-overflow", "severity": "High", "viewport": vp,
                     "selector": "div.hero", "detail": f"Page overflows at {vp}",
                     "screenshot": ""} for vp in VPS]}


def _six(ctx_env, python_cmd):
    ctx, root = _project(ctx_env, python_cmd)
    _script(root, "ok.py", "import json, pathlib\np = pathlib.Path('out'); p.mkdir(exist_ok=True)\n"
            f"(p / 'report.json').write_text(json.dumps({SIX!r}))\n")
    return ctx, root


def _six_doc(verdict="confirmed"):
    return "".join(
        f"## Finding\nRule: visual:horizontal-overflow\nLocation: {vp} div.hero\n"
        f"Evidence: Page overflows at {vp}\nVerdict: {verdict}\nSeverity: High\n\n" for vp in VPS)


def test_six_viewports_one_bug_with_occurrences(ctx_env, python_cmd):
    ctx, _ = _six(ctx_env, python_cmd)
    ui(["--audit", "--visual"], ctx_env, python_cmd)
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd, stdin=_six_doc())
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    bugs = [c for c in cards.load_all(ctx).values() if c.type == "bug"]
    assert len(bugs) == 1
    assert bugs[0].meta["ui_key"] == f"visual:horizontal-overflow::{uicheck.VISUAL_PAGE}"
    assert bugs[0].meta["ui_viewports"] == ",".join(VPS)
    assert all(vp in bugs[0].body for vp in VPS)


def test_dismissed_visual_candidate_hidden_next_packet(ctx_env, python_cmd):
    ctx, _ = _six(ctx_env, python_cmd)
    ui(["--audit", "--visual"], ctx_env, python_cmd)
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd,
           stdin=_six_doc("dismissed — intentional marquee"))
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    r = ui(["--audit", "--visual"], ctx_env, python_cmd)
    assert "Visual candidates (0" in r.stdout and "hidden as dismissed" in r.stdout
    assert "Rule: visual:horizontal-overflow" not in r.stdout


def _vprofile(python_cmd, root, report):
    (root / "fake.py").write_text(
        "import json, pathlib\np = pathlib.Path('out'); p.mkdir(exist_ok=True)\n"
        f"(p / 'report.json').write_text(json.dumps({report!r}))\n")
    return _profile(python_cmd, "fake.py")


def test_verify_visual_requires_check_absent_at_every_viewport(tmp_path, python_cmd):
    clean = {"viewports": ["mobile-360", "desktop-1440"], "findings": []}
    prof = _vprofile(python_cmd, tmp_path, clean)
    assert uicheck.verify_visual(tmp_path, prof, "horizontal-overflow",
                                 ["mobile-360", "desktop-1440"])[0] == "pass"
    other = {"viewports": ["mobile-360", "desktop-1440"],
             "findings": [dict(SIX["findings"][0], viewport="desktop-1440")]}
    prof = _vprofile(python_cmd, tmp_path, other)
    res, ev = uicheck.verify_visual(tmp_path, prof, "horizontal-overflow", ["mobile-360"])
    assert res == "fail" and "desktop-1440" in ev


def test_verify_visual_fails_when_report_covers_fewer_viewports(tmp_path, python_cmd):
    prof = _vprofile(python_cmd, tmp_path, {"viewports": ["mobile-360"], "findings": []})
    res, ev = uicheck.verify_visual(tmp_path, prof, "x", ["mobile-360", "desktop-1440"])
    assert res == "fail" and "desktop-1440 not exercised" in ev
    prof = _vprofile(python_cmd, tmp_path, {"viewports": [], "findings": []})
    assert uicheck.verify_visual(tmp_path, prof, "x", [])[0] == "fail"
