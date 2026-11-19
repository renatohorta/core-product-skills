"""cp-ui end to end, through the real CLIs: design system -> audit -> BUG -> start -> fix -> verify -> finish."""
import json
import sys
from pathlib import Path

from conftest import EXIT_OK, SKILLS_DIR
from test_context_persistence import run_skill
from test_ui_verify import _backdate

from _shared import cards

sys.path.insert(0, str(SKILLS_DIR / "cp-ui" / "scripts"))
import directions  # noqa: E402

PAGE = ('<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>Acme</title>\n</head>\n<body>\n'
        '<img src="x.png">\n'
        '<button class="outline-none">Go</button>\n'
        '</body>\n</html>\n')
FIXED = PAGE.replace('<img src="x.png">', '<img src="x.png" alt="Acme logo">')
DELIVERY = ("## What was done\n\nAdded alt text to the logo.\n\n## Files changed\n\n- index.html\n\n"
            "## Tests\n\n(none: UI BUG, verified by cp-ui re-check)\n\n"
            "## Red evidence\n\n(none)\n\n"
            "## Verification\n\nCommand: cp-ui --audit --verify {bug}\nResult: pass\n"
            "Commit: deadbee\n")


def ui(args, env, python_cmd, stdin=None):
    return run_skill("cp-ui", args, env, python_cmd, stdin=stdin)


def build(args, env, python_cmd, stdin=None):
    return run_skill("cp-build", args, env, python_cmd, stdin=stdin)


def test_design_system_audit_bug_verify_finish(ctx_env, python_cmd, tmp_path):
    ctx = Path(ctx_env["RUP_CONTEXT_DIR"])
    root = ctx.parent
    (root / "index.html").write_text(PAGE, encoding="utf-8")

    # 1. design-system packet, then record the operator's choice
    r = ui(["--design-system", "legal saas dashboard", "--out", str(tmp_path / "prev")],
           ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "Direction A" in r.stdout and "side by side" in r.stdout
    draft = directions.to_master(directions.compose("legal saas dashboard", "Acme")[0], "Acme")
    for label, value in (("Chosen by:", "Renato"), ("Alternatives shown:", "A, B, C"),
                         ("Why:", "fits the brand")):
        draft = draft.replace(label, f"{label} {value}", 1)
    master = tmp_path / "master.md"
    master.write_text(draft, encoding="utf-8")
    r = ui(["--design-system", "--record", str(master), "--chosen-by", "Renato"],
           ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert (ctx / "design-system" / "MASTER.md").is_file()
    assert (ctx / "design-system" / "tokens.json").is_file()

    # 2. audit packet lists the img-no-alt candidate
    r = ui(["--audit"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "img-no-alt" in r.stdout and "index.html" in r.stdout

    # 3. record: confirm it -> exactly one BUG from cp-ui
    line = PAGE.splitlines().index('<img src="x.png">') + 1
    doc = (f"## Finding\nRule: img-no-alt\nLocation: index.html:{line}\n"
           'Evidence: <img src="x.png"> has no alt\nVerdict: confirmed\nSeverity: High\n')
    r = ui(["--audit", "--record", "-"], ctx_env, python_cmd, stdin=doc)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    bugs = [c for c in cards.load_all(ctx).values() if c.type == "bug"]
    assert len(bugs) == 1 and bugs[0].meta.get("source") == "cp-ui"
    bug = bugs[0].id

    # 4. start it, record the root cause (cp-debug), the fix is not made yet so verify fails
    r = build(["--start", bug], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    cause = ("## Root cause\n\nThe logo image has no alt attribute.\n"
             "Evidence: index.html line 7 <img src=\"x.png\"> without alt\n")
    r = run_skill("cp-debug", ["--diagnose", bug, "--doc", "-"], ctx_env, python_cmd, stdin=cause)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    # verify must be strictly later than --start (1-second resolution); real flows have
    # natural latency between start and verify, so the test backdates the marker instead.
    _backdate(ctx, bug)
    assert ui(["--audit", "--verify", bug], ctx_env, python_cmd).returncode == 1

    # 5. fix, verify passes, finish accepts a delivery with no tests
    (root / "index.html").write_text(FIXED, encoding="utf-8")
    r = ui(["--audit", "--verify", bug], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    rec = json.loads((ctx / "ui" / "verify" / f"{bug}.json").read_text())
    assert rec["result"] == "pass" and rec["rule"] == "img-no-alt"
    r = build(["--finish", bug, "--delivery", "-"], ctx_env, python_cmd,
              stdin=DELIVERY.format(bug=bug))
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert cards.get(ctx, bug).status == "4-review"
