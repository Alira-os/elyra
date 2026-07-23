"""
prompts.py — Centralized prompt builders for Elyra personas.

Phase 1 of PLAN.md moved persona invocation out of thin-glue
``*_agent.py`` files into a single triple:

    (persona.md charter) + (Pydantic output model) + (backend.invoke(...))

The Manager (and root CLIs like ``scrape.py``, ``architect.py``,
``marketing.py``) call ``backend.invoke(persona, prompt, output_model)``
directly. The prompt itself is the only non-trivial glue left, so this
module owns it: one builder function per persona, each composing the
charter + upstream artifacts + output contract.

Why a dedicated module instead of inline strings in the orchestrator?
The persona prompts are 200-1000 lines each — they encode schema dumps,
compact-view rules, retry hints, and per-persona reliability contracts
that have been tuned over many E2E runs. Inlining them into the
orchestrator would balloon the file and scatter persona knowledge
across the codebase. Centralizing here keeps the prompts reviewable
in one place and makes them easy to version/test.

Public API:

    build_scraper_prompt(url, site_id, persona_text) -> str
    build_architect_prompt(site, persona_text) -> str
    build_marketing_prompt(site, architecture, persona_text) -> str
    build_designer_prompt(site, recommendation, site_slug, persona_text,
                          gap_context=None) -> str
    build_builder_prompt(site, architecture, recommendation, site_slug,
                         persona_text, visual_direction=None,
                         gap_context=None) -> str
    build_seo_prompt(site, architecture, recommendation, site_slug,
                     migration_id, persona_text) -> str
    build_geo_plan_prompt(site, architecture, seo_strategy, site_slug,
                          migration_id, persona_text) -> str
    build_geo_build_prompt(site, architecture, seo_strategy, geo_strategy,
                           site_dir, site_slug, migration_id, persona_text) -> str
    build_github_issue_prompt(migration_id, url, platform, issue_body,
                              persona_text) -> str

The ``persona_text`` argument is the loaded charter markdown (the
caller is responsible for loading it from ``registry/personas/<name>.md``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from skills.agentic.prompt_budget import (
    compact_content_recommendation,
    compact_site_architecture,
    compact_site_understanding,
    compact_visual_direction,
)


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------


def build_scraper_prompt(url: str, site_id: str, persona_text: str) -> str:
    """Build the scraper_specialist prompt.

    The recon agent writes its findings to a directory under
    ``memory/site_understandings/<site_id>/`` during its loop. The Python
    glue only checks that ``site.json`` exists at the end.
    """
    out_dir = f"memory/site_understandings/{site_id}"
    return f"""{persona_text}

## Task
Recon: {url}
Site ID: {site_id}
Output directory: {out_dir}/

Follow the persona's instructions. Write files to that directory as you go.
At the end, confirm `site.json` exists."""


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


def build_architect_prompt(site, persona_text: str) -> str:
    """Build the architect_specialist prompt.

    Phase 0.6: uses a compact view of SiteUnderstanding. Full JSON is
    available on disk at ``memory/site_understandings/[id].json`` for the
    persona to re-read via its tools if it needs per-page component
    detail beyond the summary.
    """
    from models.site_schemas import SiteArchitecture

    schema_json = json.dumps(SiteArchitecture.model_json_schema(), indent=2)
    site_compact = compact_site_understanding(site)
    site_json = json.dumps(site_compact, indent=2, default=str)

    return f"""{persona_text}

## Task
Analyze the following SiteUnderstanding (compact view) and produce a SiteArchitecture blueprint.

## Input SiteUnderstanding (compact view)
{site_json}

_Full SiteUnderstanding JSON is available at: `memory/site_understandings/[site_id].json`. Re-read via your tools if you need per-page component detail beyond the summary above._

## Output Contract
Output ONLY valid JSON matching this schema — no markdown, no commentary,
no text outside the JSON object:
{schema_json}

Begin architecture analysis now."""


def _retry_architect_prompt() -> str:
    """Short, terse re-emit prompt used after a first extraction failure."""
    return (
        "Your previous response was not parseable JSON. "
        "Re-emit the SiteArchitecture as a single JSON object "
        "(no ``` fence, no prose, no comments). "
        'Example: {"source_url": "https://x.com", '
        '"target_stack": {"framework": "nextjs"}} '
        "Keep it under 1500 chars. Use snake_case for field names."
    )


def retry_architect_prompt() -> str:
    """Public re-emit prompt for the architect's retry path."""
    return _retry_architect_prompt()


# ---------------------------------------------------------------------------
# Marketing
# ---------------------------------------------------------------------------


def build_marketing_prompt(site, architecture, persona_text: str) -> str:
    """Build the marketing_specialist prompt."""
    from models.site_schemas import ContentRecommendation

    schema_json = json.dumps(ContentRecommendation.model_json_schema(), indent=2)
    site_compact = compact_site_understanding(site)
    arch_compact = compact_site_architecture(architecture)
    site_json = json.dumps(site_compact, indent=2, default=str)
    arch_json = json.dumps(arch_compact, indent=2, default=str)

    return f"""{persona_text}

## Task
Analyze the following SiteUnderstanding and SiteArchitecture (compact views).
Develop two content strategy variants (A and B), then autonomously choose the winning variant.
Produce a complete ContentRecommendation.

## Input SiteUnderstanding (compact view)
{site_json}

## Input SiteArchitecture (compact view)
{arch_json}

_Full upstream JSON is available at `memory/site_understandings/` and `memory/site_architectures/` — re-read via your tools if you need per-page detail._

## Output Contract
Output ONLY valid JSON matching this schema — no markdown, no commentary,
no text outside the JSON object:
{schema_json}

Begin content strategy analysis now."""


# ---------------------------------------------------------------------------
# UI Designer
# ---------------------------------------------------------------------------


def build_designer_prompt(
    site,
    recommendation,
    site_slug: str,
    persona_text: str,
    gap_context: Optional[str] = None,
) -> str:
    """Build the ui_designer prompt."""
    site_compact = compact_site_understanding(site)
    rec_compact = compact_content_recommendation(recommendation, keep_brand=True)

    site_json = json.dumps(site_compact, indent=2, default=str)
    rec_json = json.dumps(rec_compact, indent=2, default=str)

    gap_section = ""
    if gap_context:
        gap_section = f"""

## Prioritized Rework Instructions (from Quality Gate)
{gap_context}

Apply these changes first. Produce a new versioned VisualDirection (_vN.json) reflecting the requested adjustments.
"""

    return f"""{persona_text}

## Task
Produce a VisualDirection artifact that the Builder will use as the authoritative visual specification.
{gap_section}

## Input SiteUnderstanding (compact view)
{site_json}

## Input ContentRecommendation (compact view, with BrandSpec)
{rec_json}

## Output Contract
Return a single JSON object with these fields (all optional except primary_change + rationale + stitch_status):
- primary_change (string, required) — one-sentence headline of the visual evolution
- rationale (string, required) — why this evolution, traceable to BrandSpec tokens
- stitch_status (string, required) — "available" | "unavailable" | "partial"
- impacted_components (string[]) — component_ids affected
- impacted_pages (string[]) — route paths affected
- color_delta (object|null) — DELTA only, never repeat BrandSpec fields
- typography_delta (object|null) — DELTA only
- motion_delta (object|null) — DELTA only
- designer_notes (string[]) — short bullets for the human reviewer
- created_at (string, ISO 8601) — when this direction was produced

If Stitch MCP is unavailable, still emit a valid artifact using the fallback contract in the persona above. Never return `{{}}`.

Write the JSON to memory/visual_specs/{site_slug}/[timestamp].json AND a companion REVIEW.md.

Begin design now."""


# ---------------------------------------------------------------------------
# Builder (Phase 1.1: legacy monolithic builder — kept for in-flight migrations)
# ---------------------------------------------------------------------------


def build_builder_prompt(
    site,
    architecture,
    recommendation,
    site_slug: str,
    persona_text: str,
    visual_direction=None,
    gap_context: Optional[str] = None,
) -> str:
    """Build the legacy monolithic builder_specialist prompt."""
    from models.site_schemas import BuildManifest

    site_compact = compact_site_understanding(site)
    arch_compact = compact_site_architecture(architecture)
    rec_compact = compact_content_recommendation(recommendation, keep_brand=True)
    site_json = json.dumps(site_compact, indent=2, default=str)
    arch_json = json.dumps(arch_compact, indent=2, default=str)
    rec_json = json.dumps(rec_compact, indent=2, default=str)

    vd_section = ""
    if visual_direction:
        vd_compact = compact_visual_direction(visual_direction)
        vd_json = json.dumps(vd_compact, indent=2, default=str)
        vd_section = f"""

## Input VisualDirection (from UI Designer)
{vd_json}

## VisualDirection Usage
- visual_direction.primary_change = the overarching design evolution direction
- visual_direction.rationale = why the direction was chosen
- visual_direction.color_delta / typography_delta / motion_delta = specific overrides
- visual_direction.impacted_components / impacted_pages = which parts are affected
- visual_direction.stitch_status = "available" | "unavailable" | "partial"
- If stitch_status is "unavailable", the Builder must apply BrandSpec tokens exactly without introducing new visual choices.

Apply VisualDirection AFTER applying BrandSpec. VisualDirection overrides BrandSpec only where explicitly delta-ed.
If no VisualDirection is present, apply BrandSpec tokens exactly as the final authority.
"""
    else:
        vd_section = """

## VisualDirection
No VisualDirection artifact found. Apply BrandSpec tokens exactly as the final visual authority.
Log any deviation from BrandSpec tokens as a gap in the Gap Ledger.
"""

    gap_section = ""
    if gap_context:
        gap_section = f"""

## Prioritized Rework Instructions (from Quality Gate)
{gap_context}

Apply these changes first. Re-run `impeccable detect` as the final step and ensure the report is emitted.
"""

    return f"""{persona_text}

## Task
Build a complete, production-ready site implementation from the following artifacts.
{gap_section}

## Input SiteUnderstanding (compact view)
{site_json}

## Input SiteArchitecture (compact view)
{arch_json}

## Input ContentRecommendation (with chosen variant + brand_spec)
{rec_json}
{vd_section}
The chosen variant is already decided. Apply it fully. Apply the brand_spec as the design system contract.
Run the polish pass after initial generation. Log every polish change with reason + brand_spec_reference.
Run a structured self-critique after polish.

_Full upstream JSON is available at `memory/site_understandings/`, `memory/site_architectures/`, `memory/site_recommendations/`, and `memory/visual_specs/<slug>/` — re-read via your tools if you need per-page component detail._

## Output
Your final response must include:
1. A complete BuildManifest JSON (use the exact schema below)
2. All generated code files written to the output directory

## BuildManifest Schema
Use this exact schema for the BuildManifest:
{json.dumps(BuildManifest.model_json_schema(), indent=2)}

## Code Output
Write all generated files to the directory: sites/{site_slug}/
Key files to generate:
- sites/{site_slug}/app/page.tsx (or appropriate page file for the target framework)
- sites/{site_slug}/app/globals.css (with full BrandSpec tokens as CSS custom properties)
- sites/{site_slug}/tailwind.config.js (with BrandSpec color/typography tokens)
- sites/{site_slug}/components/ (one file per component from SiteArchitecture.components)
- sites/{site_slug}/package.json
- sites/{site_slug}/next.config.js (or appropriate config for target framework)
- sites/{site_slug}/README.md

Begin building now."""


# ---------------------------------------------------------------------------
# SEO + GEO (Phase E: discoverability specialists)
# ---------------------------------------------------------------------------


def build_seo_prompt(
    site,
    architecture,
    recommendation,
    site_slug: str,
    migration_id: str,
    persona_text: str,
) -> str:
    """Build the seo_specialist prompt (planning pass)."""
    from models.site_schemas import SeoStrategy

    schema_json = json.dumps(SeoStrategy.model_json_schema(), indent=2)

    site_compact = {
        "url": str(site.url),
        "site_name": site.site_name,
        "pages": [
            {
                "url": str(p.url),
                "title": p.title,
                "page_type": [str(pt) for pt in p.page_type],
                "headings": p.headings,
            }
            for p in site.pages
        ],
        "navigation_structure": [
            {"label": n.label, "url": str(n.url) if n.url else None}
            for n in (site.navigation_structure or [])
        ],
    }
    arch_compact = {
        "source_url": str(architecture.source_url),
        "target_stack": architecture.target_stack,
        "pages": [
            {"url": p.url, "route": p.route, "priority": p.priority}
            for p in architecture.pages
        ],
    }
    rec_compact = {
        "site_name": recommendation.site_name,
        "chosen_variant": recommendation.chosen_variant,
        "overall_content_strategy": recommendation.overall_content_strategy,
        "page_strategies": [
            {"route": ps.route, "intent": ps.intent if hasattr(ps, "intent") else ""}
            for ps in recommendation.page_strategies
        ],
    }

    return f"""{persona_text}

## Task
Produce a SeoStrategy for site_slug={site_slug!r} migration_id={migration_id!r}.

You are the seo_specialist in the Planning Room. Read the three upstream
artifacts below (compact views), then emit a single JSON object matching
the SeoStrategy schema. Do NOT emit prose, markdown fences, or commentary
outside the JSON.

## Input SiteUnderstanding (compact view)
{json.dumps(site_compact, indent=2, default=str)}

## Input SiteArchitecture (compact view)
{json.dumps(arch_compact, indent=2, default=str)}

## Input ContentRecommendation (compact view)
{json.dumps(rec_compact, indent=2, default=str)}

_Full upstream JSON is available at `memory/site_understandings/`,
`memory/site_architectures/`, and `memory/site_recommendations/` — re-read
via your tools if you need per-page detail._

## Output Contract
Output ONLY valid JSON matching this schema — no markdown, no commentary,
no text outside the JSON object. Use Pydantic v1 conventions: no `X | None`,
use `Optional[X] = None` and `model_dump()` style.

{schema_json}

Begin SEO strategy analysis now."""


def build_geo_plan_prompt(
    site,
    architecture,
    seo_strategy,
    site_slug: str,
    migration_id: str,
    persona_text: str,
) -> str:
    """Build the geo_specialist PLANNING prompt."""
    from models.site_schemas import GeoStrategy

    schema_json = json.dumps(GeoStrategy.model_json_schema(), indent=2)

    site_compact = {
        "url": str(site.url),
        "site_name": site.site_name,
        "pages": [
            {"url": str(p.url), "title": p.title, "page_type": [str(pt) for pt in p.page_type]}
            for p in site.pages
        ],
    }
    arch_compact = {
        "source_url": str(architecture.source_url),
        "target_stack": architecture.target_stack,
        "pages": [{"route": p.route, "priority": p.priority} for p in architecture.pages],
    }
    seo_compact = (
        {
            "target_routes": list(seo_strategy.target_routes),
            "canonical_base": seo_strategy.canonical_base,
        }
        if seo_strategy is not None
        else None
    )

    return f"""{persona_text}

## Task (PLANNING PASS — Strategy)
Produce a GeoStrategy for site_slug={site_slug!r} migration_id={migration_id!r}.

You are the geo_specialist running the PLANNING pass. Read the upstream
artifacts (compact views below), then emit a single JSON object matching
the GeoStrategy schema. Do NOT emit prose, markdown fences, or commentary
outside the JSON.

## Input SiteUnderstanding (compact view)
{json.dumps(site_compact, indent=2, default=str)}

## Input SiteArchitecture (compact view)
{json.dumps(arch_compact, indent=2, default=str)}

## Input SeoStrategy (compact view; may be null on resume)
{json.dumps(seo_compact, indent=2, default=str)}

_Full upstream JSON is at `memory/site_understandings/`,
`memory/site_architectures/`, and `memory/seo_strategies/`._

## Output Contract
Output ONLY valid JSON matching this schema — no markdown, no commentary,
no text outside the JSON object:

{schema_json}

Begin GEO strategy analysis now."""


def build_geo_build_prompt(
    site,
    architecture,
    seo_strategy,
    geo_strategy,
    site_dir: Path,
    site_slug: str,
    migration_id: str,
    persona_text: str,
) -> str:
    """Build the geo_specialist FORGE prompt."""
    from models.site_schemas import GeoBuildArtifacts

    schema_json = json.dumps(GeoBuildArtifacts.model_json_schema(), indent=2)

    site_compact = {
        "url": str(site.url),
        "site_name": site.site_name,
        "pages": [
            {"url": str(p.url), "title": p.title, "page_type": [str(pt) for pt in p.page_type]}
            for p in site.pages
        ],
    }
    geo_strategy_compact = {
        "target_first_class_routes": list(geo_strategy.target_first_class_routes),
        "schema_org_types_by_route": dict(geo_strategy.schema_org_types_by_route or {}),
        "llms_txt_outline": geo_strategy.llms_txt_outline,
        "organization_block": dict(geo_strategy.organization_block or {}),
        "author_block": dict(geo_strategy.author_block or {}),
        "facts_with_sources": list(geo_strategy.facts_with_sources or []),
    }
    seo_compact = (
        {"target_routes": list(seo_strategy.target_routes), "canonical_base": seo_strategy.canonical_base}
        if seo_strategy is not None
        else None
    )

    return f"""{persona_text}

## Task (FORGE PASS — Build)
Produce a GeoBuildArtifacts payload for site_slug={site_slug!r} migration_id={migration_id!r}.

You are the geo_specialist running the FORGE pass. The Planning pass has
already produced a GeoStrategy (compact view below). The built site is
at `{site_dir}`. Read whatever DOM context you need, then emit a single
JSON object matching the GeoBuildArtifacts schema. Do NOT emit prose,
markdown fences, or commentary outside the JSON.

The Python glue will write the files you describe (`llms_txt`,
`robots_txt_ai_stanza`, etc.) to disk after you return. You only produce
the JSON.

## CRITICAL: AI Crawler Allowlist

`ai_crawler_allowlist` MUST contain ALL 11 of these entries (the locked
allowlist, see docs/GEO_FOR_LLMS.md):

  GPTBot, ClaudeBot, Claude-User, Google-Extended, PerplexityBot,
  Applebot-Extended, anthropic-ai, CCBot, cohere-ai, Amazonbot,
  Bytespider.

build_quality_gate fails the build if any are missing.

## CRITICAL: JSON-LD blocks

Every route in `target_first_class_routes` MUST appear as a key in
`json_ld_blocks_by_route` with at least one valid JSON-LD dict. Each
dict must include `@context` (https://schema.org) and `@type`. For
`FAQPage`, `mainEntity` must contain `Question`/`Answer` pairs
mirroring the DOM.

## Input SiteUnderstanding (compact view)
{json.dumps(site_compact, indent=2, default=str)}

## Input SeoStrategy (compact view; may be null)
{json.dumps(seo_compact, indent=2, default=str)}

## Input GeoStrategy (compact view)
{json.dumps(geo_strategy_compact, indent=2, default=str)}

## Built Site
The built site is at `{site_dir}`. You can read its DOM via your file
tools.

## Output Contract
Output ONLY valid JSON matching this schema:

{schema_json}

Begin GEO file production now."""


# ---------------------------------------------------------------------------
# GitHub Strategy (deploy_specialist persona)
# ---------------------------------------------------------------------------


def build_github_issue_prompt(
    migration_id: str,
    url: str,
    platform: str,
    issue_body: str,
    persona_text: str,
) -> str:
    """Build the prompt for the GitHub-issue-creation dispatch."""
    return f"""You are the GitHub Strategy specialist for Elyra.

Create a GitHub issue in the Alira-os/elyra repository to track a failed migration.

**Migration ID:** {migration_id}
**Source URL:** {url}
**Platform:** {platform}

**Issue Body:**
{issue_body}

**Steps to perform using GitHub MCP tools:**
1. Create a new issue in Alira-os/elyra with the provided title and body
2. Use appropriate labels: "migration-failure", "automated"
3. Set the issue title to: "[Migration Failed] {migration_id} - {platform}"

**Output format (JSON only, no markdown):**
{{
  "success": true/false,
  "issue_url": "https://github.com/Alira-os/elyra/issues/XXX",
  "issue_number": 123,
  "message": "What was done or what error occurred"
}}

Return ONLY valid JSON. No markdown code blocks, no explanation outside the JSON."""


# ---------------------------------------------------------------------------
# LLM-side parse + repair helpers (used by callers for validation)
# ---------------------------------------------------------------------------


# Coerce known LLM drift patterns for SiteArchitecture payloads.
_ARCH_ALLOWED = None  # populated lazily because we want SiteArchitecture in scope


def _coerce_architect_payload(data):
    """Normalise the most common drift patterns in Kilo's SiteArchitecture output.

    Strips unknown top-level keys and coerces the literal "null" string
    to JSON null for ``image_strategy.cdn_domain`` and per-page optional
    fields like ``cms_content_type`` / ``template_id``.
    """
    from models.site_schemas import SiteArchitecture

    if not isinstance(data, dict):
        return data

    allowed = {k: v for k, v in data.items() if k in SiteArchitecture.model_fields}
    data = allowed

    if "image_strategy" in data and isinstance(data["image_strategy"], dict):
        cdn = data["image_strategy"].get("cdn_domain")
        if cdn == "null":
            data["image_strategy"]["cdn_domain"] = None

    if "pages" in data and isinstance(data["pages"], list):
        for page in data["pages"]:
            if not isinstance(page, dict):
                continue
            for opt_field in ("cms_content_type", "template_id"):
                if isinstance(page.get(opt_field), str) and page[opt_field] == "null":
                    page[opt_field] = None

    return data


def coerce_architect_payload(data):
    """Public wrapper for the architect-coercion helper."""
    return _coerce_architect_payload(data)


# ---------------------------------------------------------------------------
# Lenient VisualDirection salvage (the designer's last-resort fallback)
# ---------------------------------------------------------------------------


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _collect_last_text(stdout: str) -> Optional[str]:
    """Collect the last 'text' event payload from a Kilo NDJSON stream."""
    last_text = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "text":
            t = event.get("part", {}).get("text", "")
            if isinstance(t, str) and t:
                last_text = t
    return last_text


def collect_last_text(stdout: str) -> Optional[str]:
    """Public wrapper for the NDJSON last-text collector."""
    return _collect_last_text(stdout)


def _lenient_parse_visual_direction(raw_text: str) -> Optional[dict]:
    """Best-effort extraction of VisualDirection fields from arbitrary text.

    Mirrors the legacy ``designer_agent.lenient_parse_visual_direction``
    implementation. Returns a dict ready for ``VisualDirection(**dict)``
    or ``None`` if nothing useful can be recovered.
    """
    from skills.agentic.json_extract import extract_json

    if not raw_text:
        return None

    try:
        return extract_json(raw_text)
    except Exception:
        pass

    for match in _FENCE_RE.finditer(raw_text):
        candidate = (match.group(1) or "").strip()
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    out: dict = {}
    patterns = {
        "primary_change": re.compile(
            r'"primary_change"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL
        ),
        "rationale": re.compile(
            r'"rationale"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL
        ),
        "stitch_status": re.compile(
            r'"stitch_status"\s*:\s*"((?:[^"\\]|\\.)*)"'
        ),
        "stitch_project_id": re.compile(
            r'"stitch_project_id"\s*:\s*"((?:[^"\\]|\\.)*)"'
        ),
        "stitch_project_url": re.compile(
            r'"stitch_project_url"\s*:\s*"((?:[^"\\]|\\.)*)"'
        ),
    }
    for field_name, pat in patterns.items():
        m = pat.search(raw_text)
        if m:
            out[field_name] = m.group(1)

    if out.get("primary_change") or out.get("rationale"):
        if "stitch_status" not in out:
            out["stitch_status"] = "unavailable"
        return out

    return None


def lenient_parse_visual_direction(raw_text: str) -> Optional[dict]:
    """Public wrapper for the lenient VisualDirection parser."""
    return _lenient_parse_visual_direction(raw_text)


__all__ = [
    # Persona prompt builders
    "build_scraper_prompt",
    "build_architect_prompt",
    "retry_architect_prompt",
    "build_marketing_prompt",
    "build_designer_prompt",
    "build_builder_prompt",
    "build_seo_prompt",
    "build_geo_plan_prompt",
    "build_geo_build_prompt",
    "build_github_issue_prompt",
    # Validation / repair helpers
    "coerce_architect_payload",
    "collect_last_text",
    "lenient_parse_visual_direction",
]