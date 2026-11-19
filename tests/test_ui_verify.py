"""cp-ui --audit --verify BUG-NNN and cp-build --finish accepting it for cp-ui BUGs."""
import json
from pathlib import Path

from conftest import EXIT_OK
from test_context_persistence import run_skill

from _shared import cards, uicheck

ROOT_CAUSE = "## Symptom\n\nx\n\n## Reproduction\n\nopen it\n\n## Root cause\n\nmissing alt\n"
DELIVERY = ("## What was done\n\nAdded alt.\n\n## Files changed\n\n- src/Home.tsx\n\n"
            "## Tests\n\n(none: UI BUG, verified by cp-ui re-check)\n\n"
            "## Red evidence\n\n(none)\n\n"
            "## Verification\n\nCommand: cp-ui --audit --verify BUG-001\nResult: pass\n"
            "Commit: deadbee\n")
BAD = '<img src="a.png">\n'
GOOD = '<img src="a.png" alt="logo">\n'


def ui(args, env, python_cmd, stdin=None):
    return run_skill("cp-ui", args, env, python_cmd, stdin=stdin)


def build(args, env, python_cmd, stdin=None):
    return run_skill("cp-build", args, env, python_cmd, stdin=stdin)


def _bug(ctx_env, key="img-no-alt::src/Home.tsx", source="cp-ui", src_text=BAD):
    ctx = Path(ctx_env["RUP_CONTEXT_DIR"])
    root = ctx.parent
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "Home.tsx").write_text(src_text, encoding="utf-8")
    card = cards.create(ctx, "bug", "[ui] bug", ROOT_CAUSE, source=source)
    if key:
        cards.set_meta(card, "ui_key", key)
    return ctx, root, card.id


def _record(ctx, bug):
    return json.loads((ctx / "ui" / "verify" / f"{bug}.json").read_text())


def test_verify_pass_writes_record(ctx_env, python_cmd):
    ctx, root, bug = _bug(ctx_env, src_text=GOOD)
    r = ui(["--audit", "--verify", bug], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    rec = _record(ctx, bug)
    assert set(rec) == {"bug", "rule", "result", "at", "evidence"}
    assert rec["bug"] == bug and rec["rule"] == "img-no-alt" and rec["result"] == "pass"
    assert uicheck.verify_record(ctx, bug) == rec
    assert uicheck.verify_record(ctx, "BUG-999") is None


def test_verify_fail_exits_1(ctx_env, python_cmd):
    ctx, _, bug = _bug(ctx_env)
    r = ui(["--audit", "--verify", bug], ctx_env, python_cmd)
    assert r.returncode == 1
    assert _record(ctx, bug)["result"] == "fail"


def test_verify_rejects_non_ui_bug_and_visual_without_flag(ctx_env, python_cmd):
    ctx, _, bug = _bug(ctx_env, source="")
    assert ui(["--audit", "--verify", bug], ctx_env, python_cmd).returncode == 1
    assert not (ctx / "ui" / "verify" / f"{bug}.json").exists()


def test_visual_verify_needs_flag(ctx_env, python_cmd):
    ctx, _, bug = _bug(ctx_env, key="visual:horizontal-overflow::mobile-360")
    r = ui(["--audit", "--verify", bug], ctx_env, python_cmd)
    assert r.returncode == 1 and "needs --visual" in r.stdout + r.stderr


def test_checklist_bug_verify_needs_evidence_file(ctx_env, python_cmd):
    ctx, root, bug = _bug(ctx_env, key="checklist:dark-mode::")
    r = ui(["--audit", "--verify", bug], ctx_env, python_cmd)
    assert r.returncode == 1
    r = ui(["--audit", "--verify", bug, "--evidence", "shots/none.png"], ctx_env, python_cmd)
    assert r.returncode == 1 and not (ctx / "ui" / "verify" / f"{bug}.json").exists()
    (root / "shots").mkdir()
    (root / "shots" / "dark.png").write_bytes(b"x")
    r = ui(["--audit", "--verify", bug, "--evidence", "shots/dark.png"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    rec = _record(ctx, bug)
    assert rec["result"] == "pass" and rec["evidence"] == "shots/dark.png"


def _doing(ctx_env, python_cmd, **kw):
    ctx, root, bug = _bug(ctx_env, **kw)
    r = build(["--start", bug], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    return ctx, root, bug, r


def test_start_marks_ui_verify_after_and_prints_instruction(ctx_env, python_cmd):
    ctx, _, bug, r = _doing(ctx_env, python_cmd)
    assert cards.get(ctx, bug).meta["ui_verify_after"]
    assert f"cp-ui --audit --verify {bug}" in r.stdout and "regression test is optional" in r.stdout


def test_finish_accepts_cp_ui_bug_with_passing_verify_and_no_tests(ctx_env, python_cmd):
    ctx, root, bug, _ = _doing(ctx_env, python_cmd)
    (root / "src" / "Home.tsx").write_text(GOOD, encoding="utf-8")
    assert ui(["--audit", "--verify", bug], ctx_env, python_cmd).returncode == EXIT_OK
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "UI BUG verified by cp-ui re-check at" in r.stdout
    card = cards.get(ctx, bug)
    assert card.status == "4-review"
    assert "cp-ui re-check: img-no-alt — pass at" in cards.section_text(card, "Regression test")


def test_finish_rejects_cp_ui_bug_without_verify_or_tests(ctx_env, python_cmd):
    ctx, _, bug, _ = _doing(ctx_env, python_cmd)
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
    assert r.returncode == 1 and "lists no tests" in r.stdout
    assert cards.get(ctx, bug).status == "3-doing"


def test_finish_rejects_failing_verify(ctx_env, python_cmd):
    ctx, _, bug, _ = _doing(ctx_env, python_cmd)
    assert ui(["--audit", "--verify", bug], ctx_env, python_cmd).returncode == 1
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
    assert r.returncode == 1


def test_finish_rejects_non_cp_ui_bug_with_only_verify(ctx_env, python_cmd):
    ctx, root, bug, _ = _doing(ctx_env, python_cmd, source="")
    (ctx / "ui" / "verify").mkdir(parents=True)
    (ctx / "ui" / "verify" / f"{bug}.json").write_text(json.dumps(
        {"bug": bug, "rule": "img-no-alt", "result": "pass",
         "at": "2999-01-01T00:00:00", "evidence": ""}))
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
    assert r.returncode == 1 and "lists no tests" in r.stdout


def test_stale_verify_before_start_is_ignored(ctx_env, python_cmd):
    ctx, root, bug = _bug(ctx_env, src_text=GOOD)
    assert ui(["--audit", "--verify", bug], ctx_env, python_cmd).returncode == EXIT_OK
    rec = ctx / "ui" / "verify" / f"{bug}.json"
    data = json.loads(rec.read_text())
    data["at"] = "2000-01-01T00:00:00"
    rec.write_text(json.dumps(data))
    assert build(["--start", bug], ctx_env, python_cmd).returncode == EXIT_OK
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
    assert r.returncode == 1 and "lists no tests" in r.stdout
