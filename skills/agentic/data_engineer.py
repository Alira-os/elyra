"""
data_engineer.py — Phase 1.1 Forge Room persona.

Produces a DataContracts artifact (Pydantic-validated) describing the
data layer of the migrated site. Runs early in the Forge Room —
after DevOps (which provides the DeploySpec constraints) and before
the Backend / Frontend specialists (which consume the data contracts).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Path setup: see forge_common.py for rationale.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import (  # noqa: E402
    DataContract,
    DataContracts,
    SiteArchitecture,
    DeploySpec,
)

from skills.agentic.forge_common import (  # noqa: E402
    DATA_CONTRACTS_DIR,
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


def build_data_engineer_prompt(
    site,
    architecture: SiteArchitecture,
    deploy_spec: Optional[DeploySpec] = None,
    *,
    gap_context: Optional[str] = None,
) -> str:
    """Build the data engineer's prompt.

    Inputs (in order of importance):
      - DeploySpec (if available) — constrains platform / scaling / security
      - SiteUnderstanding — source platform signals
      - SiteArchitecture — the data-model sketch (pages, components, nav)

    The persona markdown is the system prompt; the artifact info
    above is the task. Both are passed in compact form.
    """
    persona = load_persona_markdown("data_engineer")

    site_json, arch_json, deploy_json = _serialize_compact(
        compact_site_understanding(site),
        compact_site_architecture(architecture),
        deploy_spec.model_dump(mode="json") if deploy_spec is not None else {},
    )

    schema_json = json.dumps(DataContracts.model_json_schema(), indent=2)

    gap_section = ""
    if gap_context:
        gap_section = f"""

## Prioritized Rework Instructions (from Quality Gate)
{gap_context}

Apply these changes first. The orchestrator will route you back here if the Integration Coordinator finds an unresolved cross-layer issue.
"""

    return f"""{persona}

## Task
Produce a `DataContracts` artifact (Pydantic schema below) describing
the data layer of the migrated site.
{gap_section}

## Input DeploySpec (from DevOps Engineer — early constraint)
{deploy_json}

## Input SiteUnderstanding (compact view)
{site_json}

## Input SiteArchitecture (compact view)
{arch_json}

## Output Contract
Output ONLY valid JSON matching the schema below — no markdown, no commentary,
no text outside the JSON object:
{schema_json}

Begin data modeling now."""


def design_data_contracts(
    site,
    architecture: SiteArchitecture,
    deploy_spec: Optional[DeploySpec] = None,
    *,
    migration_id: str = "",
    site_slug: str = "",
    gap_context: Optional[str] = None,
) -> Optional[DataContracts]:
    """Main entry point. Builds the prompt, calls Kilo, validates the
    response against DataContracts, persists to disk, returns the artifact.

    On any failure, returns None and logs a high-severity gap with
    target_persona="data_engineer" so the manager routes back here.
    """
    persona = "data_engineer"
    prompt = build_data_engineer_prompt(
        site, architecture, deploy_spec, gap_context=gap_context
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
        contracts = DataContracts(**data)
    except Exception as e:
        make_failed_invocation_gap(
            migration_id=migration_id,
            persona=persona,
            description=f"DataContracts JSON parsed but failed Pydantic validation: {e}",
        )
        return None

    # Stamp produced_at and produced_by since the LLM may forget.
    contracts.produced_at = contracts.produced_at or datetime.now().isoformat()
    contracts.produced_by = persona

    save_artifact_to_dir(contracts, DATA_CONTRACTS_DIR, migration_id, persona)
    return contracts


def load_latest_data_contracts(migration_id: str = "") -> Optional[DataContracts]:
    """Load the most recent DataContracts artifact (or the one matching
    `migration_id` if provided). For now we just return the latest;
    per-migration scoping is a follow-up."""
    artifact_id = get_latest_artifact_id(DATA_CONTRACTS_DIR)
    if not artifact_id:
        return None
    path = DATA_CONTRACTS_DIR / f"{artifact_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DataContracts(**data)
    except Exception as e:
        print(f"[WARN] Failed to load DataContracts {path}: {e}")
        return None
