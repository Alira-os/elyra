"""
elyra_engineer.py — Elyra Engineer agent thin glue.

Architecture:
- Python (thin glue): loads gap ledger + BuildManifest artifacts, builds
  prompt, calls Kilo via tools.kilo.invoke_kilo_safe, validates output
  with the shared json_extract.extract_json, delegates PR creation to
  Kilo's github MCP (no direct GitHub HTTP calls from Python).
- Kilo CLI: loads the persona, drives LLM reasoning, and creates the
  draft PR via the github MCP server.

This module is the canonical implementation. The root ``elyra_engineer.py``
is a 50-line debug CLI that delegates here.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from memory.gap_ledger import export_for_elyra_engineer, query_gaps
from skills.agentic.json_extract import extract_json, JSONExtractionError
from tools.execution import ToolResult, invoke_kilo_safe


MEMORY_DIR = Path("memory/site_understandings")
BUILD_DIR = Path("memory/site_builds")
PERSONA_PATH = Path("registry/personas/elyra_engineer.md")
REPORT_DIR = Path("memory/elyra_engineer_reports")
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def _load_build_manifests(migration_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load BuildManifest files from memory."""
    if not BUILD_DIR.exists():
        return []
    out: List[Dict[str, Any]] = []
    for f in BUILD_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if migration_id is None or data.get("migration_id") == migration_id:
                out.append(data)
        except Exception:
            continue
    return out


def _build_prompt(gap_data: Dict[str, Any], manifests: List[Dict[str, Any]], migration_id: str) -> str:
    """Compose the prompt that Kilo CLI will execute."""
    persona = PERSONA_PATH.read_text(encoding="utf-8") if PERSONA_PATH.exists() else ""
    return f"""{persona}

## Task
Analyze post-run migration data for a specific migration run and produce an Elyra Engineer Report.

## Migration ID
{migration_id}

## Gap Ledger Data
{json.dumps(gap_data, indent=2, default=str)}

## BuildManifest Files ({len(manifests)} total)
{json.dumps(manifests[:5], indent=2, default=str)}

## Analysis Guidance
- Identify systematic issues: gaps appearing in >=50% of runs or >=3 occurrences
- Focus on data extraction gaps + visual/implementation gaps ONLY (v1 scope)
- Do NOT propose strategic/routing changes in v1
- Calculate quality score trends across all manifests
- Identify token fidelity violations from quality gate results
- Match issues to specific persona charter sections that need improvement
- Propose concrete, actionable fixes with rationale
- When candidates exist, draft the PR via the github MCP (push_files +
  create_pull_request on a fresh branch); mark the PR draft.

## Output
Your final response must include a complete Elyra Engineer Report JSON
following the schema in the persona above.

Begin analysis now."""


def _save_report(report: Dict[str, Any], migration_id: str) -> Path:
    """Persist the parsed Elyra Engineer Report."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"{migration_id}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    return path


def analyze(migration_id: str) -> Optional[Dict[str, Any]]:
    """Run the Elyra Engineer persona against one migration_id.

    Returns the parsed report dict on success, or None on any failure
    (Kilo error, JSON extraction failure, etc.).
    """
    print(f"\n[ENGINEER] Analyzing migration: {migration_id}")
    print("=" * 60)

    gap_data = export_for_elyra_engineer(migration_id)
    manifests = _load_build_manifests(migration_id)
    print(f"[GAP] {gap_data.get('gap_count', 0)} gaps logged")
    print(f"[BUILD] {len(manifests)} BuildManifest files found")

    if gap_data.get("gap_count", 0) == 0 and not manifests:
        print("[WARN] No data available for analysis")
        return None

    prompt = _build_prompt(gap_data, manifests, migration_id)
    context = {"migration_id": migration_id}

    try:
        result: ToolResult = invoke_kilo_safe(
            prompt=prompt,
            context=context,
            working_dir=".",
            persona="elyra_engineer",
            timeout=600,
        )
    except Exception as e:
        print(f"[ERROR] invoke_kilo_safe raised: {type(e).__name__}: {e}")
        return None

    if not result.success:
        print(f"[ERROR] Kilo run failed: {result.errors[:1] if result.errors else result.summary}")
        return None

    try:
        report = extract_json(result.summary or "")
    except JSONExtractionError as e:
        print(f"[ERROR] Could not extract JSON from Kilo output: {e.reason}")
        return None

    path = _save_report(report, migration_id)
    print(f"  [OK] Elyra Engineer Report -> {path}")

    candidates = report.get("persona_improvement_candidates", []) or []
    if candidates:
        print(f"  [ISSUES] {len(candidates)} systematic issues identified")
        for issue in candidates[:3]:
            print(f"    - {issue.get('persona')}: {str(issue.get('proposed_fix', ''))[:80]}")
    else:
        print("  [OK] No systematic issues found - pipeline healthy")

    return report


def list_migration_ids() -> List[str]:
    """Return all migration IDs known to the gap ledger, sorted ascending."""
    ids: set[str] = set()
    for entry in query_gaps():
        if entry.migration_id:
            ids.add(entry.migration_id)
    return sorted(ids)


if __name__ == "__main__":
    mid = sys.argv[1] if len(sys.argv) > 1 else None
    if not mid:
        known = list_migration_ids()
        if known:
            mid = known[-1]
            print(f"[AUTO] Analyzing most recent migration: {mid}")
        else:
            print("Usage: python elyra_engineer.py <migration_id>")
            print("Available migration IDs: none")
            sys.exit(1)
    out = analyze(mid)
    if out:
        print("\n" + json.dumps(out, indent=2)[:2000])
    else:
        print("Analysis failed.")
        sys.exit(1)
