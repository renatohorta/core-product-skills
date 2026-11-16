"""Skill contract of the cp-* SKILL.md files (ADR-0019).

Two rules taken from measuring agent behaviour (superpowers, writing-skills):
the `description` is the only text a harness always shows, so it states WHEN to
use the skill and never summarizes its workflow (an agent that reads a summary
follows the summary instead of opening the skill); and a SKILL.md that grows past
the harness' compaction cut loses its tail after a compaction. Both are cheap to
guard here.
"""
import re

import pytest

from conftest import SKILLS_DIR

SKILL_FILES = sorted(SKILLS_DIR.glob("cp-*/SKILL.md"))
DESCRIPTION_MAX = 400        # characters; the harness caps at 1024, we stay tighter
COMPACTION_CUT = 20_000      # bytes; past this the skill is truncated after a compaction


def _description(path):
    text = path.read_text(encoding="utf-8")
    head = text.split("---", 2)[1]
    line = next(l for l in head.splitlines() if l.startswith("description:"))
    return line.split(":", 1)[1].strip().strip('"'), text


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_description_states_when_to_use_it_first(path):
    description, _ = _description(path)
    assert description.lower().startswith("use when"), (
        f"{path.parent.name}: the description must open with the trigger "
        f"(\"Use when …\"), not with the discipline or the workflow")
    assert len(description) <= DESCRIPTION_MAX, (
        f"{path.parent.name}: description has {len(description)} chars "
        f"(limit {DESCRIPTION_MAX})")


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_description_is_one_line_and_quoted(path):
    description, text = _description(path)
    assert "\n" not in description
    assert not re.search(r'[\u201c\u201d]', description), "use plain quotes"


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_stays_under_the_compaction_cut(path):
    size = len(path.read_bytes())
    assert size < COMPACTION_CUT, (
        f"{path.parent.name}: {size} bytes — move what the agent only needs "
        f"sometimes into references/ (the harness truncates past {COMPACTION_CUT})")


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_documents_its_own_exit_codes(path):
    """Every cp-* skill is a CLI the agent runs; the contract must be in the file."""
    _, text = _description(path)
    assert "Exit codes" in text or "exit `" in text.lower(), (
        f"{path.parent.name}: SKILL.md must state the exit-code contract")
