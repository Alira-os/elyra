"""
backend_architect.py — Phase 1.1 Forge Room persona.

Produces an APIContracts artifact describing the API surface of the
migrated site. Runs after the Data Engineer and DevOps Engineer, and
before the Frontend Architect (which consumes the API contracts).
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
    APIEndpoint,
    APIContracts,
    DataContracts,
    DeploySpec,
    SiteArchitecture,
)
from skills.agentic.forge_common import (  # noqa: E402
    API_CONTRACTS_DIR,
    PERSONA_TIMEOUTS_S,
    _serialize_compact,
    get_latest_artifact_id,
    invoke_kilo_for_persona,
    load_persona_markdown,
    make_failed_invocation_gap,
    save_artifact_to_dir,
)
from skills.agentic.prompt_budget import (  # noqa: E402
    compact_site_architecture,
    compact_site_understanding,
)


def build_backend_prompt(
    site,
    architecture: SiteArchitecture,
    data_contracts: Optional[DataContracts] = None,
    deploy_spec: Optional[DeploySpec] = None,
    *,
    gap_context: Optional[str] = None,
) -> str:
    """Build the backend architect's prompt."""
    persona = load_persona_markdown("backend_architect")
    if not persona:
        # The persona markdown file might not exist for the new
        # backend_architect (only the legacy backend_architect.md from
        # the previous version of elyra). Fall back to a thin inline
        # system prompt that captures the role.
        persona = (
            "You are the Backend Architect in Elyra's Forge Room. "
            "You own the API surface and server-side business logic of "
            "the migrated site. You produce an APIContracts artifact "
            "(Pydantic schema below). Most marketing sites are static "
            "and have no APIs — that's fine, return an empty list of "
            "endpoints. But if the site has a CMS, an auth flow, a "
            "newsletter, a search API, a webhook, or any other server-"
            "side concern, define the endpoints precisely."
        )

    site_json, arch_json, data_json, deploy_json = _serialize_compact(
        compact_site_understanding(site),
        compact_site_architecture(architecture),
        data_contracts.model_dump(mode="json") if data_contracts is not None else {},
        deploy_spec.model_dump(mode="json") if deploy_spec is not None else {},
    )
    # Note: compact_site_understanding is a dict, _serialize_compact
    # needs to handle that. We just call json.dumps on the dicts.

    schema_json = json.dumps(APIContracts.model_json_schema(), indent=2)

    gap_section = ""
    if gap_context:
        gap_section = f"""

## Prioritized Rework Instructions (from Quality Gate)
{gap_context}

Apply these changes first.
"""

    return f"""{persona}

## Task
Produce an `APIContracts` artifact (Pydantic schema below) describing
the API surface of the migrated site. If the site is purely static,
return an empty `endpoints` list with `base_url=null`.
{gap_section}

## Input DeploySpec (from DevOps Engineer)
{deploy_json}

## Input DataContracts (from Data Engineer)
{data_json}

## Input SiteArchitecture (compact view)
{arch_json}

## Input SiteUnderstanding (compact view)
{site_json}

## Output Contract
Output ONLY valid JSON matching the schema below — no markdown, no commentary,
no text outside the JSON object:
{schema_json}

Begin API design now."""


def design_api_contracts(
    site,
    architecture: SiteArchitecture,
    data_contracts: Optional[DataContracts] = None,
    deploy_spec: Optional[DeploySpec] = None,
    *,
    migration_id: str = "",
    site_slug: str = "",
    gap_context: Optional[str] = None,
) -> Optional[APIContracts]:
    """Main entry point. Produces an APIContracts artifact."""
    persona = "backend_architect"
    prompt = build_backend_prompt(
        site, architecture, data_contracts, deploy_spec, gap_context=gap_context
    )
    json_str, _last_text = invoke_kilo_for_persona(
        persona=persona,
        prompt=prompt,
        context={"migration_id": migration_id, "site_slug": site_slug},
        migration_id=migration_id,
        timeout_s=PERSONA_TIMEOUTS_S[persona],
    )
    if json_str is None:
        return None

    try:
        data = json.loads(json_str)
        contracts = APIContracts(**data)
    except Exception as e:
        make_failed_invocation_gap(
            migration_id=migration_id,
            persona=persona,
            description=f"APIContracts JSON parsed but failed Pydantic validation: {e}",
        )
        return None

    contracts.produced_at = contracts.produced_at or datetime.now().isoformat()
    contracts.produced_by = persona
    save_artifact_to_dir(contracts, API_CONTRACTS_DIR, migration_id, persona)
    return contracts


def load_latest_api_contracts(migration_id: str = "") -> Optional[APIContracts]:
    artifact_id = get_latest_artifact_id(API_CONTRACTS_DIR)
    if not artifact_id:
        return None
    path = API_CONTRACTS_DIR / f"{artifact_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return APIContracts(**data)
    except Exception as e:
        print(f"[WARN] Failed to load APIContracts {path}: {e}")
        return None
