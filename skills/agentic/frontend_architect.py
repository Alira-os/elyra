"""
frontend_architect.py — Phase 1.1 Forge Room persona.

Produces the actual site code. Runs after Data Engineer, Backend
Architect, and DevOps Engineer. The Frontend Architect consumes:

  - DataContracts (from Data Engineer)
  - APIContracts (from Backend Architect)
  - VisualDirection + BrandSpec (from Planning Room, in HandoffBundle)
  - ContentRecommendation (from Planning Room, in HandoffBundle)
  - DeploySpec (from DevOps Engineer, for env vars + build target)

…and writes all generated code to the build site directory
(`sites/<slug>/`). The Integration Coordinator later verifies
cross-layer consistency.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import (  # noqa: E402
    APIContracts,
    BuildManifest,
    ContentRecommendation,
    DataContracts,
    DeploySpec,
    SiteArchitecture,
    SiteUnderstanding,
    VisualDirection,
)
from skills.agentic.forge_common import (  # noqa: E402
    PERSONA_TIMEOUTS_S,
    _serialize_compact,
    invoke_kilo_for_persona,
    load_persona_markdown,
    make_failed_invocation_gap,
)
from skills.agentic.prompt_budget import (  # noqa: E402
    compact_site_understanding,
    compact_site_architecture,
    compact_visual_direction,
    compact_content_recommendation,
)


def build_frontend_prompt(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
    recommendation: ContentRecommendation,
    site_slug: str,
    visual_direction: Optional[VisualDirection] = None,
    data_contracts: Optional[DataContracts] = None,
    api_contracts: Optional[APIContracts] = None,
    deploy_spec: Optional[DeploySpec] = None,
    *,
    gap_context: Optional[str] = None,
) -> str:
    """Build the frontend architect's prompt — the convergence point.

    The Frontend Architect is the largest persona in the Forge Room
    because it's where all upstream artifacts come together. Compact
    views are used to keep the prompt under the 40K character guard.
    """
    persona = load_persona_markdown("frontend_developer")
    if not persona:
        persona = (
            "You are the Frontend Architect in Elyra's Forge Room. "
            "You own the implementation: components, state management, "
            "responsiveness, accessibility, and design-token application. "
            "You write all generated code to the build site directory and "
            "produce a BuildManifest describing what you did."
        )

    site_json, arch_json, rec_json = _serialize_compact(
        compact_site_understanding(site),
        compact_site_architecture(architecture),
        compact_content_recommendation(recommendation, keep_brand=True),
    )

    vd_json = json.dumps(
        compact_visual_direction(visual_direction) if visual_direction else {},
        indent=2, default=str,
    )

    data_json = json.dumps(
        data_contracts.model_dump(mode="json") if data_contracts is not None else {},
        indent=2, default=str,
    )
    api_json = json.dumps(
        api_contracts.model_dump(mode="json") if api_contracts is not None else {},
        indent=2, default=str,
    )
    deploy_json = json.dumps(
        deploy_spec.model_dump(mode="json") if deploy_spec is not None else {},
        indent=2, default=str,
    )

    schema_json = json.dumps(BuildManifest.model_json_schema(), indent=2)

    gap_section = ""
    if gap_context:
        gap_section = f"""

## Prioritized Rework Instructions (from Quality Gate)
{gap_context}

Apply these changes first. Re-run your local build verification before reporting complete.
"""

    return f"""{persona}

## Task
Build a complete, production-ready site implementation from the artifacts
below. Write all generated code to the build site directory.
{gap_section}

## Input DeploySpec (from DevOps Engineer)
{deploy_json}

## Input DataContracts (from Data Engineer)
{data_json}

## Input APIContracts (from Backend Architect)
{api_json}

## Input VisualDirection (compact view, from Planning Room)
{vd_json}

## Input SiteUnderstanding (compact view)
{site_json}

## Input SiteArchitecture (compact view)
{arch_json}

## Input ContentRecommendation (compact view, with chosen variant + brand_spec)
{rec_json}

The chosen variant is already decided. Apply it fully. Apply the brand_spec as the design system contract.
Run a polish pass after initial generation. Log every polish change with reason + brand_spec_reference.
Run a structured self-critique after polish.

_Full upstream JSON is available at `memory/site_understandings/`, `memory/site_architectures/`, `memory/site_recommendations/`, `memory/visual_specs/<slug>/`, `memory/data_contracts/`, `memory/api_contracts/`, and `memory/deploy_specs/` — re-read via your tools if you need per-page component detail._

## Output
Your final response must include:
1. A complete BuildManifest JSON matching the schema below
2. All generated code files written to `sites/{site_slug}/`

## BuildManifest Schema
{schema_json}

## Code Output
Write all generated files to the directory: `sites/{site_slug}/`
Key files to generate (per the architecture's `target_stack`):
- pages for each route in the architecture
- global styles + tokens from brand_spec
- per-component files
- package.json + framework config

Begin building now."""


def design_frontend(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
    recommendation: ContentRecommendation,
    site_slug: str,
    visual_direction: Optional[VisualDirection] = None,
    data_contracts: Optional[DataContracts] = None,
    api_contracts: Optional[APIContracts] = None,
    deploy_spec: Optional[DeploySpec] = None,
    *,
    migration_id: str = "",
    gap_context: Optional[str] = None,
) -> tuple[Optional[BuildManifest], str]:
    """Build the site. Returns (BuildManifest, site_slug).

    The persona writes actual code via Kilo CLI; this is the only
    persona that produces files on disk besides the artifact JSON.
    """
    persona = "frontend_architect"
    prompt = build_frontend_prompt(
        site, architecture, recommendation, site_slug,
        visual_direction=visual_direction,
        data_contracts=data_contracts,
        api_contracts=api_contracts,
        deploy_spec=deploy_spec,
        gap_context=gap_context,
    )
    # Frontend architect is the heaviest prompt (everything converges
    # here). The forge_common helper's timeout guard-rails apply.
    json_str, _last_text = invoke_kilo_for_persona(
        persona=persona,
        prompt=prompt,
        context={"migration_id": migration_id, "site_slug": site_slug},
        migration_id=migration_id,
        timeout_s=PERSONA_TIMEOUTS_S[persona],
    )
    if json_str is None:
        return None, site_slug

    try:
        data = json.loads(json_str)
        # Be lenient: strip unknown fields the LLM might add.
        allowed = {k: v for k, v in data.items() if k in BuildManifest.model_fields}
        manifest = BuildManifest(**allowed)
    except Exception as e:
        make_failed_invocation_gap(
            migration_id=migration_id,
            persona=persona,
            description=f"BuildManifest JSON parsed but failed Pydantic validation: {e}",
        )
        return None, site_slug

    # Default the output_dir to sites/<slug>/ if the LLM didn't specify.
    if not getattr(manifest, "output_dir", None):
        manifest.output_dir = f"sites/{site_slug}/"

    return manifest, site_slug
