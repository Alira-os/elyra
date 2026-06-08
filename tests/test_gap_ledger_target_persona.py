"""
Unit tests for memory/gap_ledger.py — Phase 0 target_persona round-trip.

Phase 0 added target_persona to GapEntry and log_gap(). The previous code
silently dropped it. These tests lock in the new behavior so the regression
doesn't sneak back.

Run:
    python -m pytest tests/test_gap_ledger_target_persona.py -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory import gap_ledger  # noqa: E402
from memory.gap_ledger import log_gap, GapEntry  # noqa: E402


def test_log_gap_persists_target_persona(tmp_path_factory=None):
    """log_gap with target_persona must round-trip to the JSONL file."""
    # Use a temporary LEDGER_FILE so we don't pollute the real one.
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "gaps.jsonl"
        original_ledger = gap_ledger.LEDGER_FILE
        gap_ledger.LEDGER_FILE = tmp
        try:
            entry = log_gap(
                migration_id="test-mig-001",
                gap_type="gate_failure",
                source_persona="ui_designer",
                target_persona="ui_designer",
                description="test gap",
                suggested_fix="fix it",
                severity="high",
                write_to_site_ledger=False,
            )
            assert entry.target_persona == "ui_designer"
            # Read the JSONL line back.
            with open(tmp, "r", encoding="utf-8") as f:
                line = f.readline().strip()
            data = json.loads(line)
            assert data["target_persona"] == "ui_designer", (
                f"target_persona missing from JSONL: {data}"
            )
            assert data["source_persona"] == "ui_designer"
            assert data["severity"] == "high"
        finally:
            gap_ledger.LEDGER_FILE = original_ledger


def test_log_gap_omits_target_persona_when_none():
    """When target_persona is not provided, the JSONL must NOT include the key
    (we want it to be absent rather than null — downstream consumers can use
    key-presence to distinguish 'no recoverable target' from 'target unknown')."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        from pathlib import Path
        tmp = Path(tmpdir) / "gaps.jsonl"
        original_ledger = gap_ledger.LEDGER_FILE
        gap_ledger.LEDGER_FILE = tmp
        try:
            entry = log_gap(
                migration_id="test-mig-002",
                gap_type="informational",
                source_persona="orchestrator",
                description="informational note",
                severity="low",
                write_to_site_ledger=False,
            )
            assert entry.target_persona is None
            with open(tmp, "r", encoding="utf-8") as f:
                line = f.readline().strip()
            data = json.loads(line)
            assert "target_persona" not in data, (
                f"target_persona should be absent when not provided: {data}"
            )
        finally:
            gap_ledger.LEDGER_FILE = original_ledger


def test_gap_entry_to_dict_includes_target_persona_when_set():
    e = GapEntry(
        migration_id="x",
        gap_type="gate_failure",
        source_persona="builder",
        target_persona="builder",
        description="x",
        severity="high",
    )
    d = e.to_dict()
    assert d["target_persona"] == "builder"


def test_gap_entry_to_dict_omits_target_persona_when_none():
    e = GapEntry(
        migration_id="x",
        gap_type="informational",
        source_persona="orchestrator",
        description="x",
    )
    d = e.to_dict()
    assert "target_persona" not in d


if __name__ == "__main__":
    import traceback
    tests = [
        test_log_gap_persists_target_persona,
        test_log_gap_omits_target_persona_when_none,
        test_gap_entry_to_dict_includes_target_persona_when_set,
        test_gap_entry_to_dict_omits_target_persona_when_none,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(0 if failures == 0 else 1)
