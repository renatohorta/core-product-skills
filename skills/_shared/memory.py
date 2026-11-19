#!/usr/bin/env python3
"""
memory.py — a small cross-session outcome ledger for the cp-* family.

A skill often repeats work across sessions: the same vulnerability class audited again,
the same module revisited. This records what was tried and how it went, so a skill can
show its track record and *deprioritise* (never silently skip) provably-quiet work.

    .context/memory/outcomes.jsonl   one JSON row per outcome:
        {at, skill, subject, outcome, detail}

`outcome` is a short tag the caller defines (cp-operation-pentest uses "finding" / "clean").
Append-only, tolerant of a corrupt line, size-guarded. Pure standard library.

Adapted from Claude-BugHunter's engine/memory.py (the "skip provably-wasteful work" idea),
reframed for a defensive audit: we deprioritise, we do not skip.
"""
import json
from datetime import datetime
from pathlib import Path

LEDGER = "outcomes.jsonl"
FINDING = "finding"
CLEAN = "clean"
MAX_BYTES = 5 * 1024 * 1024        # rotate past 5 MB, keep one backup


def ledger_path(memory_dir) -> Path:
    return Path(memory_dir) / LEDGER


def _rotate_if_big(path: Path) -> None:
    try:
        if path.is_file() and path.stat().st_size > MAX_BYTES:
            path.replace(path.with_suffix(path.suffix + ".1"))
    except OSError:
        pass


def record_outcome(memory_dir, *, skill, subject, outcome, detail="", now=None) -> dict:
    """Append one outcome row. Creates `memory/` as needed; never raises on a bad existing file."""
    path = ledger_path(memory_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_big(path)
    row = {"at": (now or datetime.now()).isoformat(timespec="seconds"),
           "skill": str(skill), "subject": str(subject), "outcome": str(outcome),
           "detail": str(detail)}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _rows(memory_dir, skill=None):
    path = ledger_path(memory_dir)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue                       # a corrupt line never breaks a read
        if not isinstance(row, dict):
            continue
        if skill is not None and row.get("skill") != skill:
            continue
        yield row


def tally(memory_dir, skill=None) -> dict:
    """{subject: {outcome: count}} over the ledger (optionally scoped to one skill)."""
    out = {}
    for row in _rows(memory_dir, skill):
        subj = row.get("subject", "")
        out.setdefault(subj, {})
        tag = row.get("outcome", "")
        out[subj][tag] = out[subj].get(tag, 0) + 1
    return out


def quiet_subjects(memory_dir, skill, threshold=3) -> list:
    """Subjects audited clean at least `threshold` times with no finding ever.

    These are candidates to *deprioritise* — the caller still covers them; a defensive
    audit never skips on this signal alone.
    """
    out = []
    for subject, counts in tally(memory_dir, skill).items():
        if counts.get(FINDING, 0) == 0 and counts.get(CLEAN, 0) >= threshold:
            out.append(subject)
    return sorted(out)
