"""`_shared/memory.py` — a small cross-session outcome ledger for the cp-* family.

Append-only, stdlib, so a skill can learn across runs what has already been tried and
how it went — without ever deciding to skip work on its own.
"""
import pytest

from _shared import memory


def test_record_and_tally(tmp_path):
    memory.record_outcome(tmp_path, skill="cp-operation-pentest", subject="ssrf", outcome="clean")
    memory.record_outcome(tmp_path, skill="cp-operation-pentest", subject="ssrf", outcome="clean")
    memory.record_outcome(tmp_path, skill="cp-operation-pentest", subject="injection",
                          outcome="finding", detail="app/db.py:1")
    t = memory.tally(tmp_path, skill="cp-operation-pentest")
    assert t["ssrf"]["clean"] == 2
    assert t["injection"]["finding"] == 1


def test_tally_is_scoped_by_skill(tmp_path):
    memory.record_outcome(tmp_path, skill="cp-operation-pentest", subject="ssrf", outcome="clean")
    memory.record_outcome(tmp_path, skill="other-skill", subject="ssrf", outcome="clean")
    assert memory.tally(tmp_path, skill="cp-operation-pentest")["ssrf"]["clean"] == 1


def test_quiet_subjects_need_enough_cleans_and_zero_findings(tmp_path):
    for _ in range(3):
        memory.record_outcome(tmp_path, skill="s", subject="cors", outcome="clean")
    memory.record_outcome(tmp_path, skill="s", subject="xss", outcome="clean")
    memory.record_outcome(tmp_path, skill="s", subject="xss", outcome="clean")
    memory.record_outcome(tmp_path, skill="s", subject="xss", outcome="clean")
    memory.record_outcome(tmp_path, skill="s", subject="xss", outcome="finding")
    quiet = memory.quiet_subjects(tmp_path, skill="s", threshold=3)
    assert "cors" in quiet            # 3 cleans, 0 findings
    assert "xss" not in quiet         # has a finding, never quiet


def test_record_tolerates_a_corrupt_ledger(tmp_path):
    (tmp_path / memory.LEDGER).write_text("not json\n", encoding="utf-8")
    # must not raise; a corrupt line is skipped, the new row still lands
    memory.record_outcome(tmp_path, skill="s", subject="ssti", outcome="clean")
    assert memory.tally(tmp_path, skill="s")["ssti"]["clean"] == 1
