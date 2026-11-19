"""cp-ui --audit packet and --audit --record (findings -> grouped BUGs, dismissals, report)."""
import json
import re
from pathlib import Path

from conftest import EXIT_OK, EXIT_USAGE, SKILLS_DIR
from test_context_persistence import run_skill

from _shared import cards, uicheck


def ui(args, env, python_cmd, stdin=None):
    return run_skill("cp-ui", args, env, python_cmd, stdin=stdin)


def _project(ctx_env, body=None):
    ctx = Path(ctx_env["RUP_CONTEXT_DIR"])
    root = ctx.parent
    page = root / "src" / "Home.tsx"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(body or ('<img src="a.png">\n<div>\n<img src="b.png">\n'
                             '<p>x</p>\n<img src="c.png">\n'), encoding="utf-8")
    return ctx, root


def _finding(line=1, rule="img-no-alt", verdict="confirmed", sev="High",
             loc="src/Home.tsx", ev="no alt on a content image"):
    return (f"## Finding\nRule: {rule}\nLocation: {loc}:{line}\nEvidence: {ev}\n"
            f"Verdict: {verdict}\nSeverity: {sev}\n\n")


def _bugs(ctx):
    return [c for c in cards.load_all(ctx).values() if c.type == "bug"]


def _record(env, python_cmd, doc, *extra):
    return ui(["--audit", "--record", "-", *extra], env, python_cmd, stdin=doc)


def _report(ctx):
    files = sorted((ctx / "ui" / "audits").glob("*.md"), key=lambda p: (len(p.name), p.name))
    return files[-1].read_text(encoding="utf-8") if files else ""


def test_confirmed_findings_group_per_rule_and_file(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    doc = _finding(1, sev="Medium") + _finding(3, sev="High") + _finding(5, sev="Low")
    r = _record(ctx_env, python_cmd, doc)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    bugs = _bugs(ctx)
    assert len(bugs) == 1
    bug = bugs[0]
    assert bug.title == "[ui] img-no-alt in src/Home.tsx"
    assert bug.meta["source"] == "cp-ui"
    assert bug.meta["ui_key"] == "img-no-alt::src/Home.tsx"
    assert bug.meta["priority"] == "Must"  # highest severity of the group
    assert all(f"src/Home.tsx:{n}" in bug.body for n in (1, 3, 5))
    assert "## Symptom" in bug.body and "## Reproduction" in bug.body
    assert "Accessibility" in bug.body


def test_rerecord_does_not_duplicate_open_bug(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    _record(ctx_env, python_cmd, _finding(1))
    r = _record(ctx_env, python_cmd, _finding(3))
    assert r.returncode == EXIT_OK
    bugs = _bugs(ctx)
    assert len(bugs) == 1
    assert f"already open: {bugs[0].id}" in r.stdout
    assert "src/Home.tsx:3" in _report(ctx)


def test_finding_after_bug_done_opens_new_bug(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    _record(ctx_env, python_cmd, _finding(1))
    first = _bugs(ctx)[0]
    done = ctx / "kanban" / "7-done"
    done.mkdir(parents=True, exist_ok=True)
    first.path.rename(done / first.path.name)
    r = _record(ctx_env, python_cmd, _finding(1))
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert len(_bugs(ctx)) == 2


def test_dismissed_candidate_not_shown_next_packet(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    packet = ui(["--audit"], ctx_env, python_cmd)
    assert packet.returncode == EXIT_OK, packet.stdout + packet.stderr
    assert "img-no-alt" in packet.stdout and "src/Home.tsx:1" in packet.stdout
    doc = _finding(1, verdict="dismissed — decorative image, alt would be noise")
    r = _record(ctx_env, python_cmd, doc, "--by", "Ana")
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert not _bugs(ctx)
    data = json.loads((ctx / "ui" / "dismissals.json").read_text(encoding="utf-8"))
    assert data[0]["rule"] == "img-no-alt" and data[0]["by"] == "Ana"
    assert data[0]["reason"].startswith("decorative")
    packet2 = ui(["--audit"], ctx_env, python_cmd)
    assert "src/Home.tsx:1 " not in packet2.stdout and "src/Home.tsx:1:" not in packet2.stdout
    assert "src/Home.tsx:3" in packet2.stdout
    assert re.search(r"1 .*hidden|hidden.*1", packet2.stdout)


def test_dismissal_by_defaults_to_agent(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    _record(ctx_env, python_cmd, _finding(1, verdict="dismissed — decorative"))
    data = json.loads((ctx / "ui" / "dismissals.json").read_text(encoding="utf-8"))
    assert data[0]["by"] == "agent"


def test_report_header_states_what_was_verified(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    doc = _finding(1) + "## Checklist\n- width-360: ok — screenshot at 360px, no overflow\n"
    r = _record(ctx_env, python_cmd, doc)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    first = _report(ctx).splitlines()[0]
    assert first.startswith("Verified — static: 1 files")
    assert "2 candidates not addressed" in first
    assert "visual: not configured · checklist: 1/7 answered, 6 not-verified" in first
    assert "visual: not configured" in first and "6 not-verified" in first


def test_checklist_finding_opens_bug(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    doc = (_finding(1, rule="checklist:touch-targets", loc="src/Home.tsx",
                    ev="icon buttons are 24px", sev="Medium")
           + "## Checklist\n- touch-targets: finding — 24px buttons\n")
    r = _record(ctx_env, python_cmd, doc)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    bugs = _bugs(ctx)
    assert len(bugs) == 1
    assert bugs[0].title == "[ui] checklist:touch-targets in src/Home.tsx"
    assert bugs[0].meta["priority"] == "Should"


def test_checklist_finding_without_block_is_error(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    r = _record(ctx_env, python_cmd, "## Checklist\n- dark-mode: finding — low contrast\n")
    assert r.returncode == EXIT_USAGE
    assert "dark-mode" in r.stdout
    assert not _bugs(ctx)


def test_unknown_checklist_id_is_error(ctx_env, python_cmd):
    _project(ctx_env)
    r = _record(ctx_env, python_cmd, "## Checklist\n- nope: ok — x\n")
    assert r.returncode == EXIT_USAGE and "nope" in r.stdout


def test_record_exits_0_with_findings(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    r = _record(ctx_env, python_cmd, _finding(1))
    assert r.returncode == EXIT_OK
    assert "BUG-" in r.stdout


def test_cannot_verify_creates_nothing_and_is_listed(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    r = _record(ctx_env, python_cmd, _finding(1, verdict="cannot verify — needs a browser"))
    assert r.returncode == EXIT_OK
    assert not _bugs(ctx)
    assert not (ctx / "ui" / "dismissals.json").exists()
    rep = _report(ctx)
    assert "## Not verified" in rep and "needs a browser" in rep


def test_invalid_document_exits_1_and_creates_nothing(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    bad = _finding(1) + "## Finding\nRule: img-no-alt\nLocation: src/Home.tsx:3\nSeverity: High\n"
    r = _record(ctx_env, python_cmd, bad)
    assert r.returncode == EXIT_USAGE
    assert not _bugs(ctx)
    assert not (ctx / "ui" / "audits").exists()


def test_report_path_gets_a_suffix_on_same_day(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    _record(ctx_env, python_cmd, _finding(1))
    _record(ctx_env, python_cmd, _finding(3))
    names = sorted(p.name for p in (ctx / "ui" / "audits").glob("*.md"))
    assert len(names) == 2 and sum(n.endswith("-2.md") for n in names) == 1


def test_exclude_from_profile(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    (ctx / "ui").mkdir(exist_ok=True)
    (ctx / "ui" / "profile.json").write_text(
        json.dumps({"exclude": ["src/*"], "visual_audit": {"x": 1}}), encoding="utf-8")
    r = ui(["--audit"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "static: 0 files" in r.stdout


def test_packet_header_and_checklist_items(ctx_env, python_cmd):
    _project(ctx_env)
    r = ui(["--audit"], ctx_env, python_cmd)
    assert "visual: not configured" in r.stdout
    for item in uicheck.CHECKLIST_IDS:
        assert item in r.stdout
    assert "--audit --record" in r.stdout


def test_modes_are_mutually_exclusive(ctx_env, python_cmd):
    _project(ctx_env)
    r = ui(["--audit", "--design-system"], ctx_env, python_cmd)
    assert r.returncode == EXIT_USAGE


def test_checklist_ids_match_reference_and_static_checks_documented():
    refs = SKILLS_DIR / "cp-ui" / "references"
    ids = re.findall(r"^### (\S+)\s*$", (refs / "checklist.md").read_text(encoding="utf-8"), re.M)
    assert ids == list(uicheck.CHECKLIST_IDS)
    static = (refs / "static-checks.md").read_text(encoding="utf-8")
    for rule in uicheck.CHECKS:
        assert f"### {rule}\n" in static


def test_visual_finding_never_claims_a_visual_run(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    doc = _finding(1, rule="visual:contrast", verdict="cannot verify — no browser")
    r = _record(ctx_env, python_cmd, doc)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    first = _report(ctx).splitlines()[0]
    assert "visual: not configured" in first and "ran" not in first


def test_dismissal_survives_a_line_shift_when_snippet_in_evidence(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    doc = _finding(2, verdict="dismissed — decorative", ev='<img src="a.png"> is decorative')
    r = _record(ctx_env, python_cmd, doc)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    out = ui(["--audit"], ctx_env, python_cmd).stdout
    assert "src/Home.tsx:1 " not in out and "src/Home.tsx:1:" not in out
    assert "src/Home.tsx:3" in out


def test_dismissal_with_wrong_line_and_no_snippet_is_rejected(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    r = _record(ctx_env, python_cmd, _finding(2, verdict="dismissed — decorative"))
    assert r.returncode == EXIT_USAGE
    assert "src/Home.tsx" in r.stdout and "1" in r.stdout and "3" in r.stdout
    assert not (ctx / "ui" / "dismissals.json").exists()
    assert not (ctx / "ui" / "audits").exists()


def test_record_scope_matches_packet_path(ctx_env, python_cmd):
    ctx, root = _project(ctx_env)
    (root / "lib").mkdir()
    (root / "lib" / "x.tsx").write_text('<img src="z.png">\n', encoding="utf-8")
    packet = ui(["--audit", "--path", "src"], ctx_env, python_cmd).stdout
    assert "--path src" in packet
    r = _record(ctx_env, python_cmd, _finding(1), "--path", "src")
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert _report(ctx).splitlines()[0].startswith("Verified — static: 1 files")


def test_unaddressed_candidates_are_listed_not_verified(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    r = _record(ctx_env, python_cmd, _finding(1))
    rep = _report(ctx)
    assert "2 candidates not addressed" in rep.splitlines()[0]
    not_verified = rep.split("## Not verified")[1].split("## Checklist")[0]
    assert "src/Home.tsx:3" in not_verified and "src/Home.tsx:5" in not_verified
    assert "src/Home.tsx:1 " not in not_verified


def test_paths_are_normalized_for_grouping(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    doc = _finding(1, loc="./src/Home.tsx") + _finding(3, loc="src/Home.tsx")
    _record(ctx_env, python_cmd, doc)
    bugs = _bugs(ctx)
    assert len(bugs) == 1 and bugs[0].meta["ui_key"] == "img-no-alt::src/Home.tsx"


def test_ok_without_evidence_counts_as_not_verified(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    _record(ctx_env, python_cmd, "## Checklist\n- width-360: ok\n- dark-mode: ok — checked\n")
    first = _report(ctx).splitlines()[0]
    assert "1/7 answered, 6 not-verified" in first


def test_not_applicable_without_reason_counts_as_not_verified(ctx_env, python_cmd):
    ctx, _ = _project(ctx_env)
    _record(ctx_env, python_cmd,
            "## Checklist\n- width-360: not-applicable\n- dark-mode: not-applicable — no dark theme\n")
    assert "1/7 answered, 6 not-verified" in _report(ctx).splitlines()[0]


def test_match_candidate_ambiguous_asks_for_line():
    cands = [uicheck.Candidate("img-no-alt", "src/A.tsx", n, f"<img src={n}>", "High")
             for n in (3, 9)]
    f = uicheck.Finding("img-no-alt", "src/A.tsx", "no alt text", "confirmed", "High")
    cand, err = uicheck.match_candidate(f, cands)
    assert cand is None and "ambiguous — add :line (candidates:" in err
    assert "src/A.tsx:3" in err and "src/A.tsx:9" in err
    f = uicheck.Finding("img-no-alt", "src/A.tsx:42", "x", "confirmed", "High")
    assert "matches no current candidate" in uicheck.match_candidate(f, cands)[1]


def test_dismissal_in_same_second_as_start_is_ignored():
    from datetime import datetime, timezone
    at = "2026-11-19T10:00:00+00:00"
    after = datetime.fromisoformat(at).astimezone(timezone.utc)
    row = {"rule": "img-no-alt", "file": "src/A.tsx", "at": at}
    assert uicheck._dismissed_after_start(row, "img-no-alt", "src/A.tsx", after) is True


def test_save_visual_last_at_is_utc_with_offset(tmp_path):
    from datetime import timedelta, datetime
    uicheck.save_visual_last(tmp_path, "ran (1 viewports)", "", [])
    at = json.loads((tmp_path / "ui" / "visual-last.json").read_text())["at"]
    assert datetime.fromisoformat(at).utcoffset() == timedelta(0)
