"""cp-ui --audit --verify BUG-NNN and cp-build --finish accepting it for cp-ui BUGs."""
import json
import os
from datetime import datetime, timedelta, timezone
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
    ctx, root, bug, _ = _doing(ctx_env, python_cmd, key="checklist:dark-mode::")
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


def _backdate(ctx, bug, seconds=60):
    """Move ui_verify_after into the past so a verify right after counts (strict `>`)."""
    when = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    cards.set_meta(cards.get(ctx, bug), "ui_verify_after", when.isoformat(timespec="seconds"))
    return when


def _doing(ctx_env, python_cmd, **kw):
    ctx, root, bug = _bug(ctx_env, **kw)
    r = build(["--start", bug], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    _backdate(ctx, bug)
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
         "at": "2999-01-01T00:00:00+00:00", "evidence": ""}))
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
    assert r.returncode == 1 and "lists no tests" in r.stdout


def test_stale_verify_before_start_is_ignored(ctx_env, python_cmd):
    ctx, root, bug = _bug(ctx_env, src_text=GOOD)
    assert ui(["--audit", "--verify", bug], ctx_env, python_cmd).returncode == EXIT_OK
    rec = ctx / "ui" / "verify" / f"{bug}.json"
    data = json.loads(rec.read_text())
    data["at"] = "2000-01-01T00:00:00+00:00"
    rec.write_text(json.dumps(data))
    assert build(["--start", bug], ctx_env, python_cmd).returncode == EXIT_OK
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
    assert r.returncode == 1 and "lists no tests" in r.stdout


# ─── fix round 1 ────────────────────────────────────────────────────────────

def _verify_fail(ctx_env, python_cmd, ctx, bug, needle, extra=()):
    r = ui(["--audit", "--verify", bug, *extra], ctx_env, python_cmd)
    assert r.returncode == 1, r.stdout + r.stderr
    rec = _record(ctx, bug)
    assert rec["result"] == "fail" and needle in rec["evidence"], rec
    return rec


def test_static_verify_fails_when_file_deleted_or_renamed(ctx_env, python_cmd):
    ctx, root, bug = _bug(ctx_env)
    (root / "src" / "Home.tsx").rename(root / "src" / "Index.tsx")
    _verify_fail(ctx_env, python_cmd, ctx, bug, "does not exist")
    (root / "src" / "Index.tsx").unlink()
    _verify_fail(ctx_env, python_cmd, ctx, bug, "does not exist")


def test_static_verify_fails_when_file_excluded_or_not_ui(ctx_env, python_cmd):
    ctx, root, bug = _bug(ctx_env, src_text=GOOD)
    (ctx / "ui").mkdir(exist_ok=True)
    (ctx / "ui" / "profile.json").write_text(json.dumps({"exclude": ["src"]}))
    _verify_fail(ctx_env, python_cmd, ctx, bug, "excluded")
    (ctx / "ui" / "profile.json").write_text("{}")
    ctx2, root2, bug2 = _bug(ctx_env, key="img-no-alt::src/notes.txt")
    (root2 / "src" / "notes.txt").write_text("x")
    _verify_fail(ctx_env, python_cmd, ctx2, bug2, "not a UI file")


def test_static_verify_fails_in_ignored_dir(ctx_env, python_cmd):
    ctx, root, bug = _bug(ctx_env, key="img-no-alt::node_modules/x/A.tsx")
    (root / "node_modules" / "x").mkdir(parents=True)
    (root / "node_modules" / "x" / "A.tsx").write_text(GOOD)
    _verify_fail(ctx_env, python_cmd, ctx, bug, "ignored")


def test_raw_color_verify_fails_without_design_system(ctx_env, python_cmd):
    ctx, root, bug = _bug(ctx_env, key="raw-color::src/Home.tsx", src_text="<p>x</p>\n")
    _verify_fail(ctx_env, python_cmd, ctx, bug, "design system")


def test_scannable_helper(tmp_path):
    (tmp_path / "a.tsx").write_text("<p/>")
    assert uicheck.scannable(tmp_path, "a.tsx", [], None) is None
    assert "does not exist" in uicheck.scannable(tmp_path, "b.tsx", [], None)
    assert "excluded" in uicheck.scannable(tmp_path, "a.tsx", ["a.tsx"], None)
    assert "design system" in uicheck.scannable(tmp_path, "a.tsx", [], None, rule="raw-color")


def test_record_rejects_confirmed_static_finding_without_candidate(ctx_env, python_cmd):
    ctx = Path(ctx_env["RUP_CONTEXT_DIR"])
    (ctx.parent / "src").mkdir(parents=True, exist_ok=True)
    (ctx.parent / "src" / "Home.tsx").write_text(GOOD, encoding="utf-8")
    doc = ("## Finding\nRule: img-no-alt\nLocation: src/Home.tsx:1\nEvidence: x\n"
           "Verdict: confirmed\nSeverity: High\n")
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd, stdin=doc)
    assert r.returncode == 1 and "checklist:" in r.stdout + r.stderr
    assert not [c for c in cards.load_all(ctx).values() if c.type == "bug"]


def test_record_uses_candidate_normalized_file_in_ui_key(ctx_env, python_cmd):
    ctx = Path(ctx_env["RUP_CONTEXT_DIR"])
    (ctx.parent / "src").mkdir(parents=True, exist_ok=True)
    (ctx.parent / "src" / "Home.tsx").write_text(BAD, encoding="utf-8")
    doc = ("## Finding\nRule: img-no-alt\nLocation: ./src/Home.tsx:1\nEvidence: <img src=\"a.png\">\n"
           "Verdict: confirmed\nSeverity: High\n")
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd, stdin=doc)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    bug = [c for c in cards.load_all(ctx).values() if c.type == "bug"][0]
    assert bug.meta["ui_key"] == "img-no-alt::src/Home.tsx"


VISUAL_REPORT = {"viewports": ["desktop-1440"], "findings": []}


def test_visual_verify_fails_when_viewport_not_exercised(ctx_env, python_cmd):
    ctx, root, bug = _bug(ctx_env, key="visual:horizontal-overflow::mobile-360")
    (root / "fake.py").write_text(
        "import json, pathlib\np = pathlib.Path('out'); p.mkdir(exist_ok=True)\n"
        f"(p / 'report.json').write_text(json.dumps({VISUAL_REPORT!r}))\n")
    (ctx / "ui").mkdir(exist_ok=True)
    (ctx / "ui" / "profile.json").write_text(json.dumps({"visual_audit": {
        "command": f'"{python_cmd}" fake.py', "report": "out/report.json"}}))
    _verify_fail(ctx_env, python_cmd, ctx, bug, "viewport mobile-360 not exercised", ["--visual"])


def _set_record(ctx, bug, rule, at, result="pass", bug_id=None):
    d = ctx / "ui" / "verify"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{bug}.json").write_text(json.dumps({"bug": bug_id or bug, "rule": rule,
                                               "result": result, "at": at, "evidence": ""}))


def test_start_writes_utc_offset_timestamp(ctx_env, python_cmd):
    ctx2, _, bug2 = _bug(ctx_env)
    assert build(["--start", bug2], ctx_env, python_cmd).returncode == EXIT_OK
    after = datetime.fromisoformat(cards.get(ctx2, bug2).meta["ui_verify_after"])
    assert after.utcoffset() == timedelta(0)
    ui(["--audit", "--verify", bug2], ctx_env, python_cmd)
    assert datetime.fromisoformat(_record(ctx2, bug2)["at"]).utcoffset() == timedelta(0)


def test_ui_verified_predicate_rules(ctx_env, python_cmd):
    ctx, _, bug, _ = _doing(ctx_env, python_cmd)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    card = cards.get(ctx, bug)
    _set_record(ctx, bug, "img-no-alt", now)
    assert uicheck.ui_verified(ctx, card)["rule"] == "img-no-alt"
    _set_record(ctx, bug, "other-rule", now)
    assert uicheck.ui_verified(ctx, card) is None
    _set_record(ctx, bug, "img-no-alt", now, bug_id="BUG-099")
    assert uicheck.ui_verified(ctx, card) is None
    _set_record(ctx, bug, "img-no-alt", now, result="fail")
    assert uicheck.ui_verified(ctx, card) is None
    _set_record(ctx, bug, "img-no-alt", "2999-01-01T00:00:00")  # naive: not verified
    assert uicheck.ui_verified(ctx, card) is None


def test_finish_rejects_utc_earlier_but_string_greater_and_same_second(ctx_env, python_cmd):
    ctx, _, bug, _ = _doing(ctx_env, python_cmd)
    cards.set_meta(cards.get(ctx, bug), "ui_verify_after", "2026-01-01T10:00:00+00:00")
    _set_record(ctx, bug, "img-no-alt", "2026-01-01T10:30:00+05:00")  # 05:30Z
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
    assert r.returncode == 1 and "lists no tests" in r.stdout
    _set_record(ctx, bug, "img-no-alt", "2026-01-01T10:00:00+00:00")  # same second
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
    assert r.returncode == 1


def test_finish_rejects_record_for_other_rule(ctx_env, python_cmd):
    ctx, _, bug, _ = _doing(ctx_env, python_cmd)
    _set_record(ctx, bug, "tiny-font", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
    assert r.returncode == 1


def test_review_packet_shows_recheck_and_no_test_problems(ctx_env, python_cmd):
    ctx, root, bug, _ = _doing(ctx_env, python_cmd)
    (root / "src" / "Home.tsx").write_text(GOOD, encoding="utf-8")
    assert ui(["--audit", "--verify", bug], ctx_env, python_cmd).returncode == EXIT_OK
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    r = run_skill("cp-review", [bug], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "Re-checked by cp-ui: img-no-alt pass at" in r.stdout
    assert "Not covered by any delivery test" not in r.stdout
    assert "Test checks: OK" in r.stdout


def test_checklist_evidence_outside_root_or_old_is_rejected(ctx_env, python_cmd, tmp_path):
    ctx, root, bug, _ = _doing(ctx_env, python_cmd, key="checklist:dark-mode::")
    outside = tmp_path / "outside-proof.png"
    outside.write_bytes(b"x")
    _verify_fail(ctx_env, python_cmd, ctx, bug, "outside the project", ["--evidence", str(outside)])
    (root / "old.png").write_bytes(b"x")
    old = (datetime.now(timezone.utc) - timedelta(days=2)).timestamp()
    os.utime(root / "old.png", (old, old))
    _verify_fail(ctx_env, python_cmd, ctx, bug, "older than", ["--evidence", "old.png"])


# ─── fix round 2 ────────────────────────────────────────────────────────────

def test_dismissal_after_start_does_not_pass_verify_and_review_lists_it(ctx_env, python_cmd):
    ctx, root, bug, _ = _doing(ctx_env, python_cmd)
    doc = ("## Finding\nRule: img-no-alt\nLocation: src/Home.tsx:1\n"
           "Evidence: <img src=\"a.png\">\nVerdict: dismissed — decorative\nSeverity: Low\n")
    r = ui(["--audit", "--record", "-", "--by", "sneaky"], ctx_env, python_cmd, stdin=doc)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    r = ui(["--audit", "--verify", bug], ctx_env, python_cmd)
    assert r.returncode == 1 and _record(ctx, bug)["result"] == "fail"
    # a (forged) passing record still shows the dismissal to the reviewer
    _set_record(ctx, bug, "img-no-alt", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    (root / "src" / "Home.tsx").write_text(GOOD, encoding="utf-8")
    assert build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd,
                 stdin=DELIVERY).returncode == EXIT_OK
    r = run_skill("cp-review", [bug], ctx_env, python_cmd)
    assert "sneaky" in r.stdout and "decorative" in r.stdout


def test_dismissal_before_start_still_counts(ctx_env, python_cmd):
    ctx, root, bug = _bug(ctx_env)
    doc = ("## Finding\nRule: img-no-alt\nLocation: src/Home.tsx:1\n"
           "Evidence: <img src=\"a.png\">\nVerdict: dismissed — decorative\nSeverity: Low\n")
    assert ui(["--audit", "--record", "-"], ctx_env, python_cmd, stdin=doc).returncode == EXIT_OK
    assert build(["--start", bug], ctx_env, python_cmd).returncode == EXIT_OK
    _backdate(ctx, bug, -3600)  # the fix "started" after the dismissal
    assert ui(["--audit", "--verify", bug], ctx_env, python_cmd).returncode == EXIT_OK


def test_rejected_record_writes_no_dismissals(ctx_env, python_cmd):
    ctx = Path(ctx_env["RUP_CONTEXT_DIR"])
    (ctx.parent / "src").mkdir(parents=True, exist_ok=True)
    (ctx.parent / "src" / "Home.tsx").write_text(BAD, encoding="utf-8")
    doc = ("## Finding\nRule: img-no-alt\nLocation: src/Home.tsx:1\nEvidence: <img src=\"a.png\">\n"
           "Verdict: dismissed — decorative\nSeverity: Low\n\n"
           "## Finding\nRule: tiny-font\nLocation: src/Home.tsx:1\nEvidence: x\n"
           "Verdict: confirmed\nSeverity: High\n")
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd, stdin=doc)
    assert r.returncode == 1
    assert not (ctx / "ui" / "dismissals.json").exists()


def test_finish_explains_why_a_verify_record_is_rejected(ctx_env, python_cmd):
    ctx, _, bug, _ = _doing(ctx_env, python_cmd)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for rec_kw, needle in (({"rule": "tiny-font", "at": now}, "re-checked rule tiny-font"),
                           ({"rule": "img-no-alt", "at": now, "result": "fail"}, "result is fail"),
                           ({"rule": "img-no-alt", "at": now, "bug_id": "BUG-099"}, "BUG-099"),
                           ({"rule": "img-no-alt", "at": "2000-01-01T00:00:00+00:00"}, "not after the start"),
                           ({"rule": "img-no-alt", "at": "garbage"}, "unparsable")):
        _set_record(ctx, bug, **rec_kw)
        r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd, stdin=DELIVERY)
        assert r.returncode == 1 and needle in r.stdout, (needle, r.stdout)
        assert r.stdout.index(needle) < r.stdout.index("Delivery rejected")
