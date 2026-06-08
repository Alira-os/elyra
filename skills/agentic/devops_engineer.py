"""
devops_engineer.py — Phase 1.1 Forge Room persona (Deployment Guardian).

Produces a DeploySpec artifact describing the deployment, scaling,
monitoring, and CI/CD setup for the migrated site. Runs EARLY in
the Forge Room (per the design) so its constraints inform the
Data Engineer's and Backend Architect's decisions.

This is a NEW persona, distinct from `github_strategy_agent.py`:
  - `github_strategy_agent` runs AFTER the build, creates the GitHub
    repo, sets up CI workflow files, and creates GitHub issues for
    failed migrations. It uses the deploy_specialist.md persona
    markdown.
  - `devops_engineer` runs EARLY in the Forge Room, before any code
    is written. It produces a DeploySpec (Pydantic schema) that the
    rest of the Forge Room reads.
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
    DeploySpec,
    SiteArchitecture,
    SiteUnderstanding,
)

from skills.agentic.forge_common import (  # noqa: E402
    DEPLOY_SPECS_DIR,
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


def build_devops_prompt(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
    *,
    gap_context: Optional[str] = None,
) -> str:
    """Build the devops engineer's prompt — runs FIRST in the Forge Room."""
    persona = load_persona_markdown("deploy_specialist")
    if not persona:
        # Fallback if the persona markdown is missing.
        persona = (
            "You are the DevOps Engineer (Deployment Guardian) in Elyra's "
            "Forge Room. You produce a DeploySpec (Pydantic schema below) "
            "that constrains the rest of the Forge Room. You run EARLY so "
            "the Data Engineer and Backend Architect can design their "
            "artifacts to match the deploy target. For most sites this "
            "is a static deploy (Vercel, Netlify, Cloudflare Pages, or "
            "fly.io with a small machine). For CMS-driven or e-commerce "
            "sites this may include a managed database, edge functions, "
            "or a custom auth layer."
        )

    site_json, arch_json = _serialize_compact(
        compact_site_understanding(site),
        compact_site_architecture(architecture),
    )
    schema_json = json.dumps(DeploySpec.model_json_schema(), indent=2)

    gap_section = ""
    if gap_context:
        gap_section = f"""

## Prioritized Rework Instructions
{gap_context}

Apply these changes first. The orchestrator may route you back here if the Data Engineer or Backend Architect find your spec unworkable.
"""

    return f"""{persona}

## Task
Produce a `DeploySpec` artifact (Pydantic schema below) describing the
deployment, scaling, monitoring, and CI/CD setup for the migrated site.
{gap_section}

## Input SiteUnderstanding (compact view)
{site_json}

## Input SiteArchitecture (compact view)
{arch_json}

## Output Contract
Output ONLY valid JSON matching the schema below — no markdown, no commentary,
no text outside the JSON object:
{schema_json}

Begin deploy design now."""


def design_deploy_spec(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
    *,
    migration_id: str = "",
    site_slug: str = "",
    gap_context: Optional[str] = None,
) -> Optional[DeploySpec]:
    """Main entry. Produces a DeploySpec artifact."""
    persona = "deploy_specialist"
    prompt = build_devops_prompt(site, architecture, gap_context=gap_context)
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
        spec = DeploySpec(**data)
    except Exception as e:
        make_failed_invocation_gap(
            migration_id=migration_id,
            persona=persona,
            description=f"DeploySpec JSON parsed but failed Pydantic validation: {e}",
        )
        return None

    spec.produced_at = spec.produced_at or datetime.now().isoformat()
    spec.produced_by = persona
    save_artifact_to_dir(spec, DEPLOY_SPECS_DIR, migration_id, persona)
    return spec


def load_latest_deploy_spec(migration_id: str = "") -> Optional[DeploySpec]:
    artifact_id = get_latest_artifact_id(DEPLOY_SPECS_DIR)
    if not artifact_id:
        return None
    path = DEPLOY_SPECS_DIR / f"{artifact_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DeploySpec(**data)
    except Exception as e:
        print(f"[WARN] Failed to load DeploySpec {path}: {e}")
        return None
