"""Audit closure (ADR-0018): which source modules the audit never reached.

The gate answers a question a mutation score cannot: a score over three modules
says nothing about the forty that were never mutated. `blocked` (mutants ran,
none was graded) is deliberately not covered, and the caveats are generated from
the ledger instead of hand-written.
"""
import json
import sys
from pathlib import Path

import pytest

from conftest import EXIT_OK, EXIT_USAGE, load_skill
from test_context_persistence import run_skill

from _shared import auditclosure, mutation

SKILL = "cp-test"


# ─── fixtures: a project with a surface bigger than what the audit touched ──

def make_project(root: Path) -> Path:
    (root / "app" / "legacy").mkdir(parents=True, exist_ok=True)
    (root / "app" / "calc.py").write_text("def f(a):\n    return a + 1\n", encoding="utf-8")
    (root / "app" / "pricing.py").write_text("def g(a):\n    return a * 2\n", encoding="utf-8")
    (root / "app" / "legacy" / "old.py").write_text("X = 1\n", encoding="utf-8")
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_calc.py").write_text("from app.calc import f\n"
                                                 "def test_f():\n    assert f(1) == 2\n",
                                                 encoding="utf-8")
    (root / ".venv").mkdir(exist_ok=True)
    (root / ".venv" / "vendored.py").write_text("Y = 2\n", encoding="utf-8")
    return root


def write_results(context: Path, rows) -> None:
    out = context / "tests" / "mutation"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def result(file, idx=1, status="killed"):
    return {"file": file, "idx": idx, "line": 2, "kind": "bin", "desc": "+ -> -",
            "status": status, "secs": 1}


@pytest.fixture
def project(tmp_path):
    root = make_project(tmp_path / "project")
    return root, root / ".context"


# ─── surface ─────────────────────────────────────────────────────────────

def test_surface_is_non_test_source_without_vendored_trees(project):
    root, _ = project
    files = auditclosure.source_files(root, {})
    assert files == ["app/calc.py", "app/legacy/old.py", "app/pricing.py"]
    assert "tests/test_calc.py" not in files      # test code never owes a verdict
    assert ".venv/vendored.py" not in files       # copy_ignore applies


def test_audit_exclude_and_source_extensions_narrow_the_surface(project):
    root, _ = project
    files = auditclosure.source_files(root, {"audit_exclude": ["app/legacy/**"]})
    assert files == ["app/calc.py", "app/pricing.py"]
    assert auditclosure.source_files(root, {"source_extensions": [".ts"]}) == []


@pytest.mark.parametrize("pattern,path,hit", [
    ("app/calc.py", "app/calc.py", True),
    ("app/calc.py", "app/calc.pyc", False),
    ("*.py", "app/calc.py", False),          # one segment only
    ("*.py", "calc.py", True),
    ("app/**", "app/calc.py", True),         # any depth
    ("app/**", "app/legacy/old.py", True),
    ("**/migrations/**", "app/migrations/0001.py", True),
    ("app", "app/calc.py", True),            # a bare directory covers its subtree
    ("app", "apps/calc.py", False),          # …but not a sibling prefix
])
def test_wildcard_matching_is_segment_aware(pattern, path, hit):
    assert auditclosure._matches(pattern, path) is hit


# ─── verdicts ────────────────────────────────────────────────────────────

def test_a_module_with_a_graded_mutant_is_audited_and_the_rest_is_a_gap(project):
    root, context = project
    write_results(context, [result("app/calc.py")])
    ev = auditclosure.evaluate(root, context / "tests" / "mutation", context / "tests", {})
    assert ev["counts"] == {"audited": 1, "waived": 0, "blocked": 0,
                            "never_audited": 2, "files": 3}
    assert not ev["clean"] and "2 module(s) with no verdict" in ev["reason"]
    states = {r["path"]: r["state"] for r in ev["rows"]}
    assert states["app/calc.py"] == "audited"
    assert states["app/pricing.py"] == "never_audited"


def test_mutants_that_only_errored_are_blocked_not_audited(project):
    root, context = project
    write_results(context, [result("app/calc.py", status="error2"),
                            result("app/calc.py", idx=2, status="invalid")])
    ev = auditclosure.evaluate(root, context / "tests" / "mutation", context / "tests", {})
    row = next(r for r in ev["rows"] if r["path"] == "app/calc.py")
    assert row["state"] == "blocked" and row["score"] is None
    assert "none was graded" in row["note"]
    assert not ev["clean"]


def test_a_waiver_closes_a_module_only_with_its_reason(project):
    root, context = project
    ledger = context / "tests"
    with pytest.raises(ValueError):
        auditclosure.add_waiver(ledger, "app/legacy/**", "because")
    entry = auditclosure.add_waiver(
        ledger, "app/legacy/**", "generated compatibility shim, no behaviour of ours")
    assert entry["pattern"] == "app/legacy/**"
    ev = auditclosure.evaluate(root, context / "tests" / "mutation", ledger, {})
    waived = [r for r in ev["rows"] if r["state"] == "waived"]
    assert [r["path"] for r in waived] == ["app/legacy/old.py"]
    assert "compatibility shim" in waived[0]["note"]


def test_every_module_with_a_verdict_closes_the_audit_clean(project):
    root, context = project
    ledger = context / "tests"
    write_results(context, [result("app/calc.py"), result("app/pricing.py")])
    auditclosure.add_waiver(ledger, "app/legacy/**", "no behaviour: constants only")
    ev = auditclosure.evaluate(root, context / "tests" / "mutation", ledger, {})
    assert ev["clean"] and not ev["gaps"]
    assert "complete" in auditclosure.render(ev)


def test_mutations_outside_the_declared_surface_are_reported(project):
    root, context = project
    write_results(context, [result("app/calc.py"), result("scripts/tool.py")])
    ev = auditclosure.evaluate(root, context / "tests" / "mutation", context / "tests", {})
    assert ev["outside_surface"] == ["scripts/tool.py"]


# ─── the report ──────────────────────────────────────────────────────────

def test_report_says_what_was_not_audited_and_never_reads_as_passing(project):
    root, context = project
    write_results(context, [result("app/calc.py")])
    ev = auditclosure.evaluate(root, context / "tests" / "mutation", context / "tests", {})
    text = auditclosure.render(ev, project="demo", sha="abc123")
    assert "Closure: INCOMPLETE" in text
    assert "## Not audited — do not read as passing" in text
    assert "`app/pricing.py`" in text
    assert "not evidence that the tests would catch a bug" in text
    assert "| `app/calc.py` | 1 | 1 |" in text


# ─── CLI ─────────────────────────────────────────────────────────────────

def _project_of(env) -> Path:
    return Path(env["RUP_CONTEXT_DIR"]).parent


def test_cli_fails_while_a_module_is_silent_then_passes_after_a_waiver(ctx_env, python_cmd):
    make_project(_project_of(ctx_env))
    r = run_skill(SKILL, ["--audit-closure"], ctx_env, python_cmd)
    assert r.returncode == EXIT_USAGE, r.stdout + r.stderr
    report = Path(ctx_env["RUP_CONTEXT_DIR"]) / "tests" / "closure.md"
    assert report.is_file() and "INCOMPLETE" in report.read_text(encoding="utf-8")

    r = run_skill(SKILL, ["--waive", "**", "--reason", "no test suite worth mutating yet"],
                  ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    r = run_skill(SKILL, ["--audit-closure"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "closure OK" in r.stdout
    assert "complete" in report.read_text(encoding="utf-8").lower()


def test_cli_waive_without_a_reason_writes_nothing(ctx_env, python_cmd):
    make_project(_project_of(ctx_env))
    r = run_skill(SKILL, ["--waive", "app/legacy/**"], ctx_env, python_cmd)
    assert r.returncode == EXIT_USAGE
    assert not (Path(ctx_env["RUP_CONTEXT_DIR"]) / "tests" / "closure-waivers.json").exists()


def test_packet_embeds_the_closure_evidence():
    spec = load_skill(SKILL).SPEC
    assert "tests/closure.md" in spec["context_files"]
    assert any("--audit-closure" in ins for ins in spec["instructions"])


def test_profile_template_declares_the_surface_keys(capsys, ctx_env, python_cmd):
    r = run_skill(SKILL, ["--profile-template"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK
    template = json.loads(r.stdout.split("\n\n")[0])
    assert template["source_extensions"] == [".py"] and template["audit_exclude"] == []
    assert "audit-closure" in mutation.TEMPLATE_HELP
