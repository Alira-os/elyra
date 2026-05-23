"""
Gap Ledger v1: Structured log for data extraction gaps and visual/implementation failures.

Gap types:
- missing_data: Required data not available from scrape
- gate_failure: Quality gate failed (build, Impeccable, accessibility)
- visual_mismatch: Design implementation diverges from BrandSpec/VisualDirection
- persona_gap: Persona lacks capability to handle a case

v1 Scope: data extraction + visual/implementation gaps only
v2 Scope: strategic gaps, routing decisions, performance patterns
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum


class GapType(str, Enum):
    MISSING_DATA = "missing_data"
    GATE_FAILURE = "gate_failure"
    VISUAL_MISMATCH = "visual_mismatch"
    PERSONA_GAP = "persona_gap"


class GapSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GapEntry:
    """Gap Ledger Entry — plain Python class to avoid circular imports."""

    def __init__(
        self,
        gap_id: Optional[str] = None,
        timestamp: Optional[str] = None,
        migration_id: str = "",
        gap_type: str = "",
        source_persona: str = "",
        description: str = "",
        suggested_fix: str = "",
        severity: str = "medium",
        resolved: bool = False,
        resolution_note: str = "",
    ):
        self.gap_id = gap_id or str(uuid.uuid4())[:8]
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.migration_id = migration_id
        self.gap_type = gap_type
        self.source_persona = source_persona
        self.description = description
        self.suggested_fix = suggested_fix
        self.severity = severity
        self.resolved = resolved
        self.resolution_note = resolution_note

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "timestamp": self.timestamp,
            "migration_id": self.migration_id,
            "type": self.gap_type,
            "source_persona": self.source_persona,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "severity": self.severity,
            "resolved": self.resolved,
            "resolution_note": self.resolution_note,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GapEntry":
        return cls(
            gap_id=data.get("gap_id"),
            timestamp=data.get("timestamp"),
            migration_id=data.get("migration_id", ""),
            gap_type=data.get("type", ""),
            source_persona=data.get("source_persona", ""),
            description=data.get("description", ""),
            suggested_fix=data.get("suggested_fix", ""),
            severity=data.get("severity", "medium"),
            resolved=data.get("resolved", False),
            resolution_note=data.get("resolution_note", ""),
        )


LEDGER_DIR = Path(__file__).parent.parent / "memory" / "gap_ledger"
LEDGER_FILE = LEDGER_DIR / "gaps.jsonl"


def get_site_ledger_path(migration_id: str) -> Path:
    """Return the per-site Gap Ledger path for a given migration_id.

    Format: memory/gap_ledger/[migration_id]/gaps.jsonl
    Falls back to the global LEDGER_FILE if the per-site directory doesn't exist yet.
    """
    site_dir = LEDGER_DIR / migration_id
    return site_dir / "gaps.jsonl"


def _ensure_ledger_dir(migration_id: Optional[str] = None) -> None:
    """Ensure the global ledger dir and optionally the per-site dir exist."""
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    if not LEDGER_FILE.exists():
        LEDGER_FILE.write_text("")
    if migration_id:
        site_dir = LEDGER_DIR / migration_id
        site_dir.mkdir(parents=True, exist_ok=True)
        site_file = site_dir / "gaps.jsonl"
        if not site_file.exists():
            site_file.write_text("")


def log_gap(
    migration_id: str,
    gap_type: str,
    source_persona: str,
    description: str,
    suggested_fix: str = "",
    severity: str = "medium",
    write_to_site_ledger: bool = True,
) -> GapEntry:
    """Log a new gap entry to the Gap Ledger JSONL file.

    Writes to both the global gaps.jsonl and the per-site [migration_id]/gaps.jsonl
    to support concurrent multi-site runs without entry interleaving.
    """
    _ensure_ledger_dir(migration_id)
    entry = GapEntry(
        migration_id=migration_id,
        gap_type=gap_type,
        source_persona=source_persona,
        description=description,
        suggested_fix=suggested_fix,
        severity=severity,
    )

    json_line = json.dumps(entry.to_dict(), indent=None) + "\n"

    with open(LEDGER_FILE, "a", encoding="utf-8") as f:
        f.write(json_line)

    if write_to_site_ledger and migration_id:
        site_file = get_site_ledger_path(migration_id)
        with open(site_file, "a", encoding="utf-8") as f:
            f.write(json_line)

    return entry


def query_gaps(
    migration_id: Optional[str] = None,
    gap_type: Optional[str] = None,
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    source_persona: Optional[str] = None,
    read_from_site_ledger: bool = True,
) -> List[GapEntry]:
    """Query gap entries by optional filters.

    If migration_id is provided and read_from_site_ledger is True, reads from
    the per-site [migration_id]/gaps.jsonl for that migration only.
    Otherwise reads from the global gaps.jsonl.
    """
    _ensure_ledger_dir()
    ledger_file = get_site_ledger_path(migration_id) if (migration_id and read_from_site_ledger) else LEDGER_FILE
    entries: List[GapEntry] = []
    if not ledger_file.exists():
        return entries
    with open(ledger_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entry = GapEntry.from_dict(data)
            except Exception:
                continue

            if migration_id and entry.migration_id != migration_id:
                continue
            if gap_type and entry.gap_type != gap_type:
                continue
            if severity and entry.severity != severity:
                continue
            if resolved is not None and entry.resolved != resolved:
                continue
            if source_persona and entry.source_persona != source_persona:
                continue

            entries.append(entry)
    return entries


def resolve_gap(gap_id: str, resolution_note: str = "") -> bool:
    """Mark a gap entry as resolved."""
    _ensure_ledger_dir()
    if not LEDGER_FILE.exists():
        return False

    resolved = False
    lines: List[str] = []
    with open(LEDGER_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("gap_id") == gap_id:
                    data["resolved"] = True
                    data["resolution_note"] = resolution_note
                    resolved = True
                lines.append(json.dumps(data, indent=None))
            except Exception:
                lines.append(line)

    with open(LEDGER_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    return resolved


def get_aggregate_stats(migration_id: Optional[str] = None) -> Dict[str, Any]:
    """Get aggregated statistics for gap analysis."""
    entries = query_gaps(migration_id=migration_id) if migration_id else _get_all_entries()
    by_type: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    by_persona: Dict[str, int] = {}
    resolved_count = 0
    for entry in entries:
        by_type[entry.gap_type] = by_type.get(entry.gap_type, 0) + 1
        by_severity[entry.severity] = by_severity.get(entry.severity, 0) + 1
        by_persona[entry.source_persona] = by_persona.get(entry.source_persona, 0) + 1
        if entry.resolved:
            resolved_count += 1

    return {
        "total": len(entries),
        "resolved": resolved_count,
        "unresolved": len(entries) - resolved_count,
        "by_type": by_type,
        "by_severity": by_severity,
        "by_persona": by_persona,
    }


def _get_all_entries() -> List[GapEntry]:
    _ensure_ledger_dir()
    entries: List[GapEntry] = []
    if not LEDGER_FILE.exists():
        return entries
    with open(LEDGER_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(GapEntry.from_dict(json.loads(line)))
            except Exception:
                continue
    return entries


def export_for_elyra_engineer(migration_id: str) -> Dict[str, Any]:
    """Export gaps + stats for Elyra Engineer consumption."""
    entries = query_gaps(migration_id=migration_id)
    stats = get_aggregate_stats(migration_id=migration_id)
    return {
        "migration_id": migration_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "gap_count": len(entries),
        "stats": stats,
        "gaps": [e.to_dict() for e in entries],
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_migration_id = "test-001"
        log_gap(
            migration_id=test_migration_id,
            gap_type="missing_data",
            source_persona="scraper",
            description="Hero image not accessible — requires auth",
            suggested_fix="Use fallback hero from BrandSpec",
            severity="medium",
        )
        log_gap(
            migration_id=test_migration_id,
            gap_type="gate_failure",
            source_persona="builder",
            description="npm run build failed — missing dependency",
            suggested_fix="Add dependency to package.json",
            severity="high",
        )
        gaps = query_gaps(migration_id=test_migration_id)
        print(f"Logged {len(gaps)} gaps for {test_migration_id}:")
        for g in gaps:
            print(f"  [{g.gap_id}] {g.gap_type} ({g.severity}): {g.description}")

        stats = get_aggregate_stats(test_migration_id)
        print(f"Stats: {stats}")

        resolved = resolve_gap(gaps[0].gap_id, "Fixed by adding fallback image")
        print(f"Resolved gap {gaps[0].gap_id}: {resolved}")
    else:
        print("Gap Ledger v1 — usage: python gap_ledger.py test")
        print(f"Ledger file: {LEDGER_FILE}")