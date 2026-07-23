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
    output_root: str = "C:/Users/micha/DevProjects",
    stitch_project_id: Optional[str] = None,
    stitch_project_url: Optional[str] = None,
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

    stitch_section = ""
    if stitch_project_id:
        stitch_section = f"""

## Design Reference (Stitch)
This site has a Stitch design project: `{stitch_project_id}` ({stitch_project_url or "url unavailable"}).
Use the Stitch MCP (`stitch.listScreens`, `stitch.getScreen`) to fetch the screens
the ui_designer created. Treat those screens as the design reference for layout,
component choices, and spacing. Apply the BrandSpec tokens (colors, fonts,
spacing) on top of the Stitch layouts — Stitch is the *layout* reference,
BrandSpec is the *token* contract.
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

## Output Contract (CRITICAL)
Output ONLY a single valid JSON object matching the `BuildManifest` schema below.
- No markdown fences. No prose. No commentary. No code samples in the response.
- All schema fields are optional with defaults — populate only what you have evidence for.
- At minimum, set `output_dir` (e.g. `"{output_root}/{site_slug}/"`), `build_timestamp` (ISO-8601), `personas_used` (include `"frontend_architect"`), and `overall_quality_score` (0-100).
- The orchestrator will run your JSON through Pydantic. Anything outside the JSON object is dropped.

Code-writing is a SIDE EFFECT: use your file tools to write actual files under `{output_root}/{site_slug}/`, but your response itself is the BuildManifest JSON describing what you did.

Minimal required-shape example (not exhaustive):
```json
{{
  "output_dir": "{output_root}/{site_slug}/",
  "build_timestamp": "2026-06-08T18:16:46-04:00",
  "personas_used": ["frontend_architect"],
  "overall_quality_score": 0,
  "ui_polish_version": "v1",
  "ui_polish_changes": [],
  "self_critique": {{
    "visual_weight_issues": [],
    "typography_hierarchy_suggestions": [],
    "emotional_resonance_gaps": [],
    "brand_token_violations": [],
    "motion_philosophy_alignment": "aligned",
    "severity": "low",
    "recommended_action": "None - acceptable trade-off"
  }},
  "lighthouse_scores": {{}},
  "deployment_readiness": {{}}
}}
```

## BuildManifest Schema (authoritative)
{schema_json}

## Code Output (side effect, not your response)
Write all generated files to the directory: `{output_root}/{site_slug}/`
Key files to generate (per the architecture's `target_stack`):
- pages for each route in the architecture
- global styles + tokens from brand_spec
- per-component files
- package.json + framework config

{stitch_section}

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
    output_root: str = "C:/Users/micha/DevProjects",
    stitch_project_id: Optional[str] = None,
    stitch_project_url: Optional[str] = None,
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
        output_root=output_root,
        stitch_project_id=stitch_project_id,
        stitch_project_url=stitch_project_url,
    )

    # Frontend architect is the heaviest prompt (everything converges
    # here). The forge_common helper's timeout guard-rails apply. We
    # also do one bounded retry on Pydantic validation failure — the
    # previous "first try or give up" path wasted the 600s budget on
    # near-misses that a corrective re-prompt can usually fix.
    json_str = _invoke_with_validation_retry(
        persona=persona,
        prompt=prompt,
        migration_id=migration_id,
        site_slug=site_slug,
    )
    if json_str is None:
        return None, site_slug

    try:
        data = json.loads(json_str)
        # Be lenient: strip unknown fields the LLM might add.
        allowed = {k: v for k, v in data.items() if k in BuildManifest.model_fields}
        manifest = BuildManifest(**allowed)
    except Exception as e:
        # _invoke_with_validation_retry already gave Kilo one chance to
        # fix this; the only way we land here is a second failure
        # (which is the abort condition documented in the persona
        # markdown). Log and bail.
        make_failed_invocation_gap(
            migration_id=migration_id,
            persona=persona,
            description=f"BuildManifest JSON parsed but failed Pydantic validation after retry: {e}",
        )
        return None, site_slug

    # Default the output_dir to {output_root}/{site_slug}/ if the LLM didn't specify.
    if not getattr(manifest, "output_dir", None):
        manifest.output_dir = f"{output_root.rstrip('/')}/{site_slug}/"

    return manifest, site_slug


def _invoke_with_validation_retry(
    *,
    persona: str,
    prompt: str,
    migration_id: str,
    site_slug: str,
) -> Optional[str]:
    """Call Kilo once; on Pydantic-validation failure, re-prompt with
    the precise error and try once more. Returns the JSON string on
    success, or None if extraction OR validation failed twice.

    Why a one-shot retry: in the legacy personas, the dominant
    failure mode for the convergence persona was "Kilo produced a
    JSON object that was 90% correct — wrong field name, a string
    where a number was expected, etc." A focused corrective prompt
    ("here is the exact validation error; fix it") usually succeeds
    in a single follow-up. Two retries were considered and rejected
    because the 600s budget is already at its hard cap.
    """
    json_str, _last_text = invoke_kilo_for_persona(
        persona=persona,
        prompt=prompt,
        context={"migration_id": migration_id, "site_slug": site_slug},
        migration_id=migration_id,
        timeout_s=PERSONA_TIMEOUTS_S[persona],
    )
    if json_str is None:
        return None

    if _try_validate_manifest(json_str) is not None:
        return json_str

    # First attempt failed validation. Build a corrective follow-up
    # that shows the exact error and re-issues the OUTPUT-ONLY
    # contract so the model doesn't drift into prose.
    err = _validation_error_for(json_str) or "unknown Pydantic validation error"
    corrective = (
        f"{prompt}\n\n"
        f"## CORRECTION (previous response failed validation)\n"
        f"Your previous JSON output failed Pydantic validation:\n"
        f"```\n{err}\n```\n\n"
        f"Re-emit a single corrected JSON object that satisfies the schema. "
        f"Remember: OUTPUT ONLY the JSON object. No markdown fences, no prose. "
        f"Reuse the same shape you produced, but fix the failing field(s).\n"
    )
    json_str2, _ = invoke_kilo_for_persona(
        persona=persona,
        prompt=corrective,
        context={"migration_id": migration_id, "site_slug": site_slug, "retry": True},
        migration_id=migration_id,
        timeout_s=PERSONA_TIMEOUTS_S[persona],
    )
    if json_str2 is None:
        return None
    if _try_validate_manifest(json_str2) is not None:
        return json_str2
    return None


def _try_validate_manifest(json_str: str) -> Optional[BuildManifest]:
    """Parse + validate a JSON string against BuildManifest. Returns
    the manifest on success, or None on any failure. Never raises."""
    try:
        data = json.loads(json_str)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    allowed = {k: v for k, v in data.items() if k in BuildManifest.model_fields}
    try:
        return BuildManifest(**allowed)
    except Exception:
        return None


def _validation_error_for(json_str: str) -> Optional[str]:
    """Return the Pydantic ValidationError string for a JSON string
    that fails BuildManifest validation, or None if parsing itself
    failed. Truncated to 800 chars to keep the corrective prompt
    from doubling in size."""
    try:
        data = json.loads(json_str)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    allowed = {k: v for k, v in data.items() if k in BuildManifest.model_fields}
    try:
        BuildManifest(**allowed)
    except Exception as e:
        return str(e)[:800]
    return None
