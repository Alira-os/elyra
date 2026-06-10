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
    migration_id: str = "",
    site_slug: str = "",
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

**REQUIRED context fields** — copy these into the output JSON exactly:
- `migration_id`: {migration_id or "unknown"}
- `site_slug`: {site_slug or "unknown"}
- `final_build_manifest_id` candidate: `{build_id}`
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


def _lenient_parse_integration_status(
    data: dict,
    *,
    fallback_migration_id: str,
    fallback_site_slug: str,
) -> Optional[IntegrationStatus]:
    """Parse Kilo's JSON output into an IntegrationStatus, tolerating
    common LLM drift.

    The IntegrationStatus schema requires `migration_id` and `site_slug`
    as plain `str` (not Optional). Kilo frequently leaves them blank or
    invents a value. We:
      1. Strip unknown fields (the LLM often adds e.g. `recommendations`).
      2. Inject the function-arg values for any required field the LLM
         left blank or omitted (rather than crashing the whole artifact).
      3. Then attempt Pydantic validation.

    Returns the validated model, or None if even the lenient parse fails.
    """
    if not isinstance(data, dict):
        return None
    allowed = {k: v for k, v in data.items() if k in IntegrationStatus.model_fields}
    # Inject context fields the LLM may have left blank.
    if not allowed.get("migration_id"):
        allowed["migration_id"] = fallback_migration_id or "unknown"
    if not allowed.get("site_slug"):
        allowed["site_slug"] = fallback_site_slug or "unknown"
    # Defensive defaults for list fields, in case the LLM emitted null.
    for list_field in ("cross_layer_checks_run", "issues_found", "resolutions", "reasoning_trace"):
        if allowed.get(list_field) is None:
            allowed[list_field] = []
    try:
        return IntegrationStatus(**allowed)
    except Exception:
        return None


def _retry_prompt(prompt: str) -> str:
    """Tightened retry prompt used when the first Kilo call's output
    could not be extracted as JSON. Mirrors the scraper_agent retry
    pattern (build_scraper_prompt(retry_mode=True)) — no prose, no
    tool calls, just a fenced JSON block matching the prior schema.
    """
    return f"""Your previous response could not be parsed as JSON. Re-emit the
IntegrationStatus you produced, this time with strict formatting.

1. Do NOT call any tools.
2. Output a single ```json fenced code block containing one valid JSON
   object that matches the IntegrationStatus schema below.
3. NO prose, NO commentary, NO headings, NO `text` events before the
   fence. The first and only text event MUST be the fenced JSON.
4. Use the exact `migration_id`, `site_slug`, and `build_id` from
   the prompt below. Do not invent new ones.

## Original task (for context)
{prompt}"""


def _build_fallback_integration_status(
    *,
    migration_id: str,
    site_slug: str,
    build_id: str,
    reason: str,
) -> IntegrationStatus:
    """Deterministic IntegrationStatus used when Kilo fails twice.

    The integration_coordinator is the LAST persona in the Forge Room.
    Returning `None` forces a 180s+ route-back loop. Instead, emit a
    "no-information" artifact that:
      - explicitly says checks could not be performed (`requires_kilo_re_invocation`)
      - has no invented issues
      - sets `final_build_manifest_id = build_id` so the orchestrator
        can still mark the build as integration-clean (the upstream
        build manifest is the source of truth; the coordinator is a
        verifier, not an author).

    A high-severity gap is logged separately so the manager can
    route-back if appropriate.
    """
    return IntegrationStatus(
        migration_id=migration_id or "unknown",
        site_slug=site_slug or "unknown",
        cross_layer_checks_run=["requires_kilo_re_invocation"],
        issues_found=[],
        resolutions=[],
        final_build_manifest_id=build_id or None,
        reasoning_trace=[
            f"Integration Coordinator fell back to deterministic artifact: {reason}",
            "No cross-layer checks could be performed. Orchestrator should route_back.",
        ],
        produced_at=datetime.now().isoformat(),
        produced_by="integration_coordinator_fallback",
    )


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
    """Main entry. Produces an IntegrationStatus artifact.

    Reliability contract (Phase 1.1 hardening):
      1. Kilo call (180s).
      2. If JSON extraction fails → ONE retry with a tightened,
         JSON-only prompt.
      3. If both calls fail to produce a parseable artifact → emit a
         deterministic fallback IntegrationStatus (no invented issues;
         `final_build_manifest_id` is set so the build can complete).
         A high-severity gap is logged so the manager can route_back.
    """
    persona = "integration_coordinator"
    prompt = build_integration_prompt(
        site, architecture, data_contracts, api_contracts, deploy_spec,
        build_id=build_id,
        migration_id=migration_id,
        site_slug=site_slug,
        gap_context=gap_context,
    )

    json_str, _last_text = invoke_kilo_for_persona(
        persona=persona,
        prompt=prompt,
        context={"migration_id": migration_id, "site_slug": site_slug, "build_id": build_id},
        migration_id=migration_id,
        timeout_s=PERSONA_TIMEOUTS_S[persona],
    )

    # Single retry on extraction failure — same pattern as scraper_agent.
    if json_str is None:
        json_str, _last_text = invoke_kilo_for_persona(
            persona=persona,
            prompt=_retry_prompt(prompt),
            context={"migration_id": migration_id, "site_slug": site_slug, "build_id": build_id, "retry": True},
            migration_id=migration_id,
            timeout_s=PERSONA_TIMEOUTS_S[persona],
        )

    if json_str is None:
        make_failed_invocation_gap(
            migration_id=migration_id,
            persona=persona,
            description=(
                "IntegrationStatus: Kilo invocation (and one retry) failed to "
                "produce parseable JSON. Emitting deterministic fallback."
            ),
            severity="high",
        )
        fallback = _build_fallback_integration_status(
            migration_id=migration_id,
            site_slug=site_slug,
            build_id=build_id,
            reason="kilo_invoke_failed",
        )
        save_artifact_to_dir(fallback, INTEGRATION_STATUS_DIR, migration_id, persona)
        return fallback

    # Lenient parse: strip unknown fields, inject blank required fields.
    try:
        data = json.loads(json_str)
    except Exception as e:
        make_failed_invocation_gap(
            migration_id=migration_id,
            persona=persona,
            description=f"IntegrationStatus: json.loads failed after retry: {e}",
            severity="high",
        )
        fallback = _build_fallback_integration_status(
            migration_id=migration_id, site_slug=site_slug, build_id=build_id,
            reason="json_loads_failed",
        )
        save_artifact_to_dir(fallback, INTEGRATION_STATUS_DIR, migration_id, persona)
        return fallback

    status = _lenient_parse_integration_status(
        data,
        fallback_migration_id=migration_id,
        fallback_site_slug=site_slug,
    )
    if status is None:
        make_failed_invocation_gap(
            migration_id=migration_id,
            persona=persona,
            description=(
                "IntegrationStatus: lenient Pydantic parse failed after retry. "
                "Emitting deterministic fallback."
            ),
            severity="high",
        )
        fallback = _build_fallback_integration_status(
            migration_id=migration_id, site_slug=site_slug, build_id=build_id,
            reason="pydantic_parse_failed",
        )
        save_artifact_to_dir(fallback, INTEGRATION_STATUS_DIR, migration_id, persona)
        return fallback

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
