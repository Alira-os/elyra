"""
integration_coordinator.py — Phase 1.1 Forge Steward.

Receives outputs from Data Engineer, Backend Architect, Frontend
Architect, and DevOps Engineer. Smooths cross-layer rough edges,
runs the cross-layer checks, and produces an IntegrationStatus
artifact. Also updates the BuildManifest with the final manifest_id.

The integration coordinator is the "steward" of the Forge Room —
per the design, the Integration Coordinator has first-line authority
to make small fixes (typos, missing alt text, env var name sync)
without route_back. Big fixes (e.g. data contract shape mismatch
that needs the data_engineer to redo) trigger route_back.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import (  # noqa: E402
    APIContracts,
    DataContracts,
    DeploySpec,
    IntegrationStatus,
    SiteArchitecture,
    SiteUnderstanding,
)

from skills.agentic.forge_common import (  # noqa: E402
    INTEGRATION_STATUS_DIR,
    PERSONA_TIMEOUTS_S,
    _serialize_compact,
    get_latest_artifact_id,
    invoke_kilo_for_persona,
    load_persona_markdown,
    make_failed_invocation_gap,
    save_artifact_to_dir,
)
from skills.agentic.prompt_budget import (  # noqa: E402
    compact_site_understanding,
    compact_site_architecture,
)


def build_integration_prompt(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
    data_contracts: Optional[DataContracts] = None,
    api_contracts: Optional[APIContracts] = None,
    deploy_spec: Optional[DeploySpec] = None,
    *,
    build_id: str = "",
    gap_context: Optional[str] = None,
) -> str:
    """Build the integration coordinator's prompt."""
    persona = load_persona_markdown("integration_coordinator")
    site_json, arch_json, data_json, api_json, deploy_json = _serialize_compact(
        compact_site_understanding(site),
        compact_site_architecture(architecture),
        data_contracts.model_dump(mode="json") if data_contracts is not None else {},
        api_contracts.model_dump(mode="json") if api_contracts is not None else {},
        deploy_spec.model_dump(mode="json") if deploy_spec is not None else {},
    )
    schema_json = json.dumps(IntegrationStatus.model_json_schema(), indent=2)

    gap_section = ""
    if gap_context:
        gap_section = f"""

## Prioritized Rework Instructions
{gap_context}

These are the issues the previous Integration Coordinator run flagged but did not resolve. Apply these checks first.
"""

    return f"""{persona}

## Task
Verify cross-layer consistency across the Forge Room outputs and produce
an `IntegrationStatus` artifact. Run every applicable check, list the
issues you found, and the resolutions you applied. If everything is
clean, set `final_build_manifest_id` to `{build_id}`.
{gap_section}

## Input BuildManifest ID (from Frontend Architect)
{build_id}

## Input DataContracts (from Data Engineer)
{data_json}

## Input APIContracts (from Backend Architect)
{api_json}

## Input DeploySpec (from DevOps Engineer)
{deploy_json}

## Input SiteArchitecture (compact view)
{arch_json}

## Input SiteUnderstanding (compact view)
{site_json}

## Output Contract
Output ONLY valid JSON matching the schema below — no markdown, no commentary,
no text outside the JSON object:
{schema_json}

Begin integration review now."""


def coordinate_integration(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
    data_contracts: Optional[DataContracts] = None,
    api_contracts: Optional[APIContracts] = None,
    deploy_spec: Optional[DeploySpec] = None,
    *,
    migration_id: str = "",
    site_slug: str = "",
    build_id: str = "",
    gap_context: Optional[str] = None,
) -> Optional[IntegrationStatus]:
    """Main entry. Produces an IntegrationStatus artifact."""
    persona = "integration_coordinator"
    prompt = build_integration_prompt(
        site, architecture, data_contracts, api_contracts, deploy_spec,
        build_id=build_id, gap_context=gap_context,
    )
    json_str, _last_text = invoke_kilo_for_persona(
        persona=persona,
        prompt=prompt,
        context={"migration_id": migration_id, "site_slug": site_slug, "build_id": build_id},
        migration_id=migration_id,
        timeout_s=PERSONA_TIMEOUTS_S[persona],
    )
    if json_str is None:
        return None

    try:
        data = json.loads(json_str)
        status = IntegrationStatus(**data)
    except Exception as e:
        make_failed_invocation_gap(
            migration_id=migration_id,
            persona=persona,
            description=f"IntegrationStatus JSON parsed but failed Pydantic validation: {e}",
        )
        return None

    status.produced_at = status.produced_at or datetime.now().isoformat()
    status.produced_by = persona
    save_artifact_to_dir(status, INTEGRATION_STATUS_DIR, migration_id, persona)
    return status


def load_latest_integration_status(migration_id: str = "") -> Optional[IntegrationStatus]:
    artifact_id = get_latest_artifact_id(INTEGRATION_STATUS_DIR)
    if not artifact_id:
        return None
    path = INTEGRATION_STATUS_DIR / f"{artifact_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return IntegrationStatus(**data)
    except Exception as e:
        print(f"[WARN] Failed to load IntegrationStatus {path}: {e}")
        return None
