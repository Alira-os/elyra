"""
forge_common.py — Shared utilities for the Phase 1.1 Forge Room personas.

The 5 new personas (Data Engineer, Backend Architect, Frontend Architect,
Integration Coordinator, DevOps Engineer) all follow the same shape:

  1. Build a prompt from the persona markdown + upstream artifacts
  2. Call Kilo via invoke_kilo_safe
  3. Extract + validate JSON against a Pydantic schema
  4. Save to memory/<dir>/<id>.json
  5. Return the artifact (or None on failure)

This module centralizes the boilerplate (loaders, savers, prompt
helpers, error-gap logging) so each persona file is short and
focused. The persona-specific logic (what the prompt asks, what
schema the LLM should produce) lives in each persona's own module.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Path setup: this file lives at skills/agentic/forge_common.py. The
# elyra root is parents[2] of this file.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory.gap_ledger import log_gap  # noqa: E402
from skills.agentic.json_extract import extract_json, JSONExtractionError  # noqa: E402
from skills.agentic.kilo_callbacks import make_timeout_callback  # noqa: E402
from skills.agentic.prompt_budget import (  # noqa: E402
    compact_site_understanding,
    compact_site_architecture,
    compact_visual_direction,
    compact_content_recommendation,
)
from tools.execution import invoke_kilo_safe  # noqa: E402


# In-memory artifact dirs for the 4 typed Forge artifacts.
DATA_CONTRACTS_DIR = Path("memory/data_contracts")
API_CONTRACTS_DIR = Path("memory/api_contracts")
DEPLOY_SPECS_DIR = Path("memory/deploy_specs")
INTEGRATION_STATUS_DIR = Path("memory/integration_status")

# Per-persona timeout defaults. Each is the budget the persona gets
# before its Kilo call is aborted by invoke_kilo_safe.
PERSONA_TIMEOUTS_S = {
    "data_engineer": 240,
    "backend_architect": 300,
    "frontend_architect": 600,
    "integration_coordinator": 180,
    "deploy_specialist": 240,
    "deploy_engineer": 240,
}


def _to_jsonable(obj: Any) -> Any:
    """Coerce Pydantic models + datetimes to JSON-safe forms for json.dumps."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def _serialize_compact(*objs: Any) -> list[str]:
    """Serialize a sequence of compact-artifact dicts to JSON strings.
    Used by every persona's prompt builder so the prompt budget stays
    under 40K characters (per invoke_kilo_safe's guard-rail).
    """
    return [json.dumps(_to_jsonable(o), indent=2, default=str) for o in objs]


def load_persona_markdown(persona_short: str) -> str:
    """Read a persona's markdown from registry/personas/. The 5 new
    personas use the same registry directory as the planning personas.

    Falls back to a system-default encoding (utf-8 with errors='replace')
    so non-ASCII bytes don't crash the loader on Windows cp1252.
    """
    md_path = Path(f"registry/personas/{persona_short}.md")
    if not md_path.exists():
        return ""
    try:
        return md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return md_path.read_text(encoding="cp1252", errors="replace")


def save_artifact_to_dir(
    artifact: Any,
    artifact_dir: Path,
    migration_id: str,
    persona: str,
) -> str:
    """Save a Pydantic model or dict to memory/<artifact_dir>/<id>.json.

    Returns the timestamp ID used for the file. The orchestrator
    reads this back via the bundle.
    """
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = artifact_dir / f"{artifact_id}.json"
    if hasattr(artifact, "model_dump_json"):
        content = artifact.model_dump_json(indent=2)
    else:
        content = json.dumps(artifact, indent=2, default=str)
    filepath.write_text(content, encoding="utf-8")
    return artifact_id


def get_latest_artifact_id(artifact_dir: Path) -> Optional[str]:
    """Return the timestamp ID of the most recent file in
    memory/<artifact_dir>/, or None if the dir is empty."""
    if not artifact_dir.exists():
        return None
    files = sorted(artifact_dir.glob("*.json"), reverse=True)
    return files[0].stem if files else None


def invoke_kilo_for_persona(
    *,
    persona: str,
    prompt: str,
    context: dict,
    migration_id: str,
    timeout_s: int,
) -> tuple[Optional[str], Optional[str]]:
    """Call Kilo via invoke_kilo_safe and return (json_str, last_text)
    or (None, last_text) on extraction failure.

    Logs a high-severity gap with target_persona=<persona> on extraction
    failure so the manager's deterministic short-circuit routes back.
    """
    result = invoke_kilo_safe(
        prompt=prompt,
        context=context,
        working_dir=".",
        persona=persona,
        timeout=timeout_s,
        on_timeout=make_timeout_callback(
            persona=persona,
            migration_id_fn=lambda: migration_id,
            default_timeout_s=timeout_s,
        ),
    )
    if not result.success:
        print(f"[ERROR] Kilo invocation failed for {persona}: {result.errors}")
        return None, None

    stdout = result.summary or ""
    last_text: Optional[str] = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if isinstance(event, dict) and event.get("type") == "text":
                t = event.get("part", {}).get("text", "")
                if isinstance(t, str):
                    last_text = t
        except json.JSONDecodeError:
            continue

    try:
        data = extract_json(stdout)
    except JSONExtractionError as e:
        log_gap(
            migration_id=migration_id,
            gap_type="gate_failure",
            source_persona=persona,
            target_persona=persona,
            description=f"Could not extract JSON from Kilo output: {e.reason}",
            suggested_fix="Check Kilo output format and prompt instructions",
            severity="high",
        )
        return None, last_text

    return json.dumps(data, default=str), last_text


def make_failed_invocation_gap(
    migration_id: str,
    persona: str,
    description: str,
    severity: str = "high",
):
    """Helper: log a gap for a persona-invocation failure (e.g. missing
    upstream artifact, timeout, schema validation)."""
    log_gap(
        migration_id=migration_id,
        gap_type="gate_failure",
        source_persona=persona,
        target_persona=persona,
        description=description,
        suggested_fix="Investigate the upstream persona or relax the schema",
        severity=severity,
    )
