"""cp-ui hooks: cp-build ## UI section, cp-review ## UI audit, uikit.touches_ui."""
from pathlib import Path
from types import SimpleNamespace

from conftest import EXIT_OK
from test_context_persistence import run_skill

from _shared import cards, uikit

MASTER = """\
# Design system
## Style
Calm.
## Colors
- primary: #1D4ED8
- on_primary: #FFFFFF
- background: #FFFFFF
- foreground: #111111
## Typography
- heading: Fraunces
- body: Inter
## Decision
Chosen by: R
Alternatives shown: A, B
Why: fits
"""
EPIC = "## Goal\n\nx\n\n## Scope\n\ny\n"
STORY = ("## User story\n\nAs a user I want x so that y.\n\n## Acceptance criteria\n\n- a\n\n"
         "## Definition of Done\n\n- ok\n")


def _task(targets, title="Add thing", desc="Do it."):
    return (f"## Description\n\n{desc}\n\n## Target files\n\n{targets}\n\n"
            "## Covers\n\n- ST-001/AC-1\n")


def _proj(ctx_env, targets, title="Add thing", desc="Do it.", ds=False):
    ctx = Path(ctx_env["RUP_CONTEXT_DIR"])
    cards.create(ctx, "epic", "E", EPIC)
    cards.create(ctx, "story", "S", STORY, parent="EP-001")
    cards.create(ctx, "task", title, _task(targets, desc=desc), parent="ST-001")
    if ds:
        d = uikit.ds_dir(ctx)
        d.mkdir(parents=True)
        (d / "MASTER.md").write_text(MASTER, encoding="utf-8")
    return ctx


def test_build_start_prints_ui_section_with_tokens(ctx_env, python_cmd):
    _proj(ctx_env, "- src/Home.tsx", ds=True)
    r = run_skill("cp-build", ["--start", "TK-001"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    out = r.stdout
    assert "## UI" in out
    assert ".context/design-system/MASTER.md" in out
    assert "primary: #1D4ED8" in out and "Fraunces" in out and "Inter" in out
    assert "Accessibility: text contrast ≥ 4.5:1, visible focus, labels/alt for every " \
           "control and image, full keyboard path." in out
    assert "Touch: targets ≥ 44×44 px with ≥ 8 px spacing; loading feedback on every " \
           "async action." in out
    assert "Performance: reserve space for media (no layout shift), lazy-load below the " \
           "fold, no animation of width/height." in out
    assert "Use only the tokens above — no raw colors or fonts outside the design system." in out
    assert "When done, run `cp-ui --audit` (add `--visual` if configured)." in out


def test_build_start_warns_without_design_system(ctx_env, python_cmd):
    _proj(ctx_env, "- src/Home.tsx")
    r = run_skill("cp-build", ["--start", "TK-001"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "⚠️ no design system: run cp-ui --design-system first (not blocking)" in r.stdout
    assert "Accessibility: text contrast" in r.stdout


def test_build_start_no_ui_section_for_backend_task(ctx_env, python_cmd):
    _proj(ctx_env, "- app/booking.py", ds=True)
    r = run_skill("cp-build", ["--start", "TK-001"], ctx_env, python_cmd)
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    assert "## UI" not in r.stdout.replace("## UI BUG", "")


def test_review_packet_mentions_ui_audit_for_ui_card(ctx_env, python_cmd):
    ctx = _proj(ctx_env, "- src/Home.tsx")
    task = cards.get(ctx, "TK-001")
    cards.set_meta(task, "branch", "tk-001")
    cards.move(ctx, "TK-001", "4-review", "delivered")
    r = run_skill("cp-review", ["TK-001"], ctx_env, python_cmd)
    assert "## UI audit" in r.stdout
    assert "cp-ui --audit" in r.stdout and "none yet" in r.stdout
    aud = ctx / "ui" / "audits"
    aud.mkdir(parents=True)
    (aud / "2026-01-01.md").write_text("old header\nx\n", encoding="utf-8")
    (aud / "2026-02-01.md").write_text("newest header\nx\n", encoding="utf-8")
    r = run_skill("cp-review", ["TK-001"], ctx_env, python_cmd)
    assert "newest header" in r.stdout and "old header" not in r.stdout


def test_review_packet_no_ui_audit_for_backend_card(ctx_env, python_cmd):
    ctx = _proj(ctx_env, "- app/booking.py")
    cards.move(ctx, "TK-001", "4-review", "delivered")
    r = run_skill("cp-review", ["TK-001"], ctx_env, python_cmd)
    assert "## UI audit" not in r.stdout


def _card(title="", body="", **meta):
    return SimpleNamespace(title=title, body=body, meta=meta, type="task")


def test_touches_ui_rules():
    t = uikit.touches_ui
    assert t(_card(body="## Target files\n\n- `src/a.vue`\n"))
    assert t(_card(title="Fix the Login Page"))
    assert t(_card(body="ajustar a tela de login"))
    assert t(_card(title="CSS cleanup"))
    assert not t(_card(title="Build the pager", body="guide users? rebuild uipath"))
    assert not t(_card(body="## Target files\n\n- app/booking.py\n"))
    assert t(_card(title="x", source="cp-ui"))
    assert t(_card(title="x", body="", **{"source": "cp-ui"}))


def test_touches_ui_ignores_target_file_names_and_acceptance_criteria():
    t = uikit.touches_ui
    assert not t(_card(title="Cache the report", body="## Target files\n\n- app/Page.py\n"))
    assert not t(_card(title="Paginate", body="## Description\n\nPaginate the export.\n\n"
                       "## Acceptance criteria\n\n- the page size is 50\n"))
    assert t(_card(title="Paginate", body="## Description\n\nFix the layout of the export.\n\n"
                   "## Acceptance criteria\n\n- ok\n"))


def test_review_latest_audit_orders_by_date_then_numeric_suffix(ctx_env, python_cmd):
    ctx = _proj(ctx_env, "- src/Home.tsx")
    cards.move(ctx, "TK-001", "4-review", "delivered")
    aud = ctx / "ui" / "audits"
    aud.mkdir(parents=True)
    for name, head in (("2026-11-19.md", "first"), ("2026-11-19-2.md", "second"),
                       ("2026-11-19-10.md", "tenth")):
        (aud / name).write_text(f"{head} header\nx\n", encoding="utf-8")
    r = run_skill("cp-review", ["TK-001"], ctx_env, python_cmd)
    assert "tenth header" in r.stdout and "second header" not in r.stdout


def test_review_latest_audit_orders_across_days(ctx_env, python_cmd):
    """A later day wins over any same-day suffix of an earlier day (honest 'latest')."""
    ctx = _proj(ctx_env, "- src/Home.tsx")
    cards.move(ctx, "TK-001", "4-review", "delivered")
    aud = ctx / "ui" / "audits"
    aud.mkdir(parents=True)
    for name, head in (("2026-11-19.md", "d19"), ("2026-11-19-2.md", "d19b"),
                       ("2026-11-19-10.md", "d19j"), ("2026-11-20.md", "d20")):
        (aud / name).write_text(f"{head} header\nx\n", encoding="utf-8")
    r = run_skill("cp-review", ["TK-001"], ctx_env, python_cmd)
    assert "d20 header" in r.stdout and "d19j header" not in r.stdout
