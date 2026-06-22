"""
designer_agent.py — UI Designer Agent (Kilo CLI as execution engine)

Architecture:
- Python: thin glue — loads SiteUnderstanding + ContentRecommendation,
          builds prompt, calls kilo run, parses VisualDirection JSON
- Kilo CLI: handles all agentic logic (persona + LLM reasoning)
- No LangGraph, no LangChain, no custom agent loops

Kilo CLI handles:
  - Loading the persona (embedded in prompt)
  - LLM reasoning over SiteUnderstanding + BrandSpec + Stitch output
  - Producing VisualDirection JSON

Usage:
    from skills.agentic.designer_agent import design
    result = design("20260520_132936", "20260520_142439")
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory.gap_ledger import log_gap
from skills.agentic.json_extract import extract_json, JSONExtractionError
from skills.agentic.kilo_callbacks import make_timeout_callback
from skills.agentic.prompt_budget import (
    compact_site_understanding,
    compact_content_recommendation,
    approx_chars,
)
from tools.kilo import invoke_kilo_safe

from models.site_schemas import (
    SiteUnderstanding,
    ContentRecommendation,
    VisualDirection,
    BrandSpec,
)


MEMORY_DIR = Path("memory/site_understandings")
RECOMMENDATION_DIR = Path("memory/site_recommendations")
VISUAL_SPEC_DIR = Path("memory/visual_specs")
PERSONA_PATH = Path("registry/personas/ui_designer.md")


def get_site_slug(site_name: str) -> str:
    """Derive a kebab-case site slug from a site name."""
    slug = site_name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    slug = slug.strip("-")
    return slug or "unnamed-site"


def build_designer_prompt(
    site: SiteUnderstanding,
    recommendation: ContentRecommendation,
    site_slug: str,
    gap_context: Optional[str] = None,
) -> str:
    """Build the prompt that Kilo CLI will execute.

    Phase 0.7: drops the inlined Pydantic JSON schema (Kilo can infer
    VisualDirection fields from the explicit field list below) and the
    "Re-read from disk" pointer text, which together were ~3KB of pure
    noise. The compact site+rec views are still JSON-serialized as
    concrete examples Kilo can copy from. Full artifacts remain on disk
    at memory/site_understandings/<id>.json and
    memory/site_recommendations/<id>.json — the persona can re-read them
    if it needs per-page detail beyond the summary.

    The persona markdown has been trimmed to its contractual essentials
    (no CSS examples — Kilo already knows CSS).
    """
    persona = PERSONA_PATH.read_text() if PERSONA_PATH.exists() else ""

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

    return f"""{persona}

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


def extract_json_from_output(stdout: str) -> tuple[Optional[str], Optional[str]]:
    """Extract JSON object from Kilo CLI --format json output.

    Returns (json_str, last_text) for debugging. Raises JSONExtractionError
    via the underlying extract_json() when no valid object can be found.
    Kept as a thin shim for backward compatibility with existing callers.
    """
    last_text = None
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
        obj = extract_json(stdout)
        return json.dumps(obj), last_text
    except JSONExtractionError:
        return None, last_text


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


def lenient_parse_visual_direction(raw_text: str) -> Optional[dict]:
    """Best-effort extraction of VisualDirection fields from arbitrary Kilo text.

    Used as a *last* fallback when Kilo's structured output is unparseable
    (e.g. truncated mid-JSON, fenced but missing a brace, or plain prose
    describing the design rather than emitting it). We scan the text for
    VisualDirection-shaped fields and return whatever we can find.

    Returns a dict ready to feed into VisualDirection(**dict), or None if
    nothing useful can be recovered.
    """
    if not raw_text:
        return None

    # Strategy 1: try extract_json on the whole text (may have been
    # already attempted; cheap to retry).
    try:
        return extract_json(raw_text)
    except JSONExtractionError:
        pass

    # Strategy 2: try a fenced ```json block (Kilo often wraps JSON).
    fence_re = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    for match in fence_re.finditer(raw_text):
        candidate = (match.group(1) or "").strip()
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    # Strategy 3: field-by-field salvage. Search the prose for keys
    # that look like VisualDirection fields. This is deliberately
    # conservative — we only recover fields whose values we can isolate.
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
    }
    for field_name, pat in patterns.items():
        m = pat.search(raw_text)
        if m:
            out[field_name] = m.group(1)

    # If we got at least primary_change OR rationale, return what we
    # have — parse_visual_direction() will fill the rest from the
    # BrandSpec-fidelity fallback.
    if out.get("primary_change") or out.get("rationale"):
        if "stitch_status" not in out:
            out["stitch_status"] = "unavailable"
        return out

    return None


def parse_visual_direction(
    raw_json: str,
    stitch_status: str = "available",
    brand_spec: Optional["BrandSpec"] = None,
) -> Optional[VisualDirection]:
    """Parse and validate JSON against VisualDirection schema.

    Always returns a minimal valid VisualDirection — even on partial or missing fields.
    stitch_status is used to set the fallback rationale when Kilo emits nothing useful.
    Duplication warnings (delta fields that repeat BrandSpec) are logged to Gap Ledger.
    """
    try:
        data = json.loads(raw_json)
        allowed = {k: v for k, v in data.items() if k in VisualDirection.model_fields}
        vd = VisualDirection(**allowed)
        dup_warnings = vd.validate_delta_no_duplication(brand_spec)
        for warning in dup_warnings:
            print(f"[WARN] VisualDirection delta duplication: {warning}")
            log_gap(
                migration_id="",
                gap_type="visual_mismatch",
                source_persona="ui_designer",
                description=f"VisualDirection delta duplication detected: {warning}",
                suggested_fix="Remove duplicate delta fields — apply BrandSpec value directly",
                severity="medium",
            )
        if vd.primary_change and vd.rationale:
            return vd
        if stitch_status == "unavailable":
            vd.primary_change = vd.primary_change or "No visual evolution — BrandSpec fidelity only"
            vd.rationale = vd.rationale or "Stitch MCP unavailable; preserving source brand tokens exactly"
            vd.stitch_status = "unavailable"
            return vd
        return vd
    except Exception as e:
        print(f"[WARN] Validation error: {e}")

    fallback_change = "No visual evolution — BrandSpec fidelity only"
    fallback_rationale = "Stitch MCP unavailable; preserving source brand tokens exactly"
    if stitch_status == "available":
        fallback_change = "Minimal delta — confirm BrandSpec fidelity in build"
        fallback_rationale = "Kilo output partial; Builder should validate against BrandSpec tokens"

    return VisualDirection(
        primary_change=fallback_change,
        rationale=fallback_rationale,
        stitch_status=stitch_status,
        created_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def load_site_understanding(site_id: str) -> Optional[SiteUnderstanding]:
    """Load a saved SiteUnderstanding from memory directory."""
    if not site_id:
        return None
    site_path = MEMORY_DIR / f"{site_id}.json"
    if not site_path.exists():
        site_path = Path(site_id)
    try:
        with open(site_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SiteUnderstanding(**data)
    except Exception as e:
        print(f"[ERROR] Failed to load SiteUnderstanding: {e}")
        return None


def load_content_recommendation(rec_id: str) -> Optional[ContentRecommendation]:
    """Load a saved ContentRecommendation from memory directory."""
    if not rec_id:
        return None
    rec_path = RECOMMENDATION_DIR / f"{rec_id}.json"
    if not rec_path.exists():
        rec_path = Path(rec_id)
    try:
        with open(rec_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ContentRecommendation(**data)
    except Exception as e:
        print(f"[ERROR] Failed to load ContentRecommendation: {e}")
        return None


def load_visual_direction(site_slug: str) -> Optional[VisualDirection]:
    """Load the latest VisualDirection for a given site_slug.

    Used by the Phase 1.1 frontend_architect persona which reads its
    upstream artifacts from the blackboard. Returns the most recent
    VisualDirection JSON under memory/visual_specs/<site_slug>/.
    """
    spec_dir = VISUAL_SPEC_DIR / site_slug
    if not spec_dir.exists():
        return None
    json_files = sorted(spec_dir.glob("*.json"), reverse=True)
    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            vd = VisualDirection(**data)
            if vd.primary_change or vd.rationale:
                return vd
        except Exception:
            continue
    return None


def save_visual_direction(
    visual_direction: VisualDirection,
    site_slug: str,
    version: Optional[str] = None,
) -> Path:
    """Save VisualDirection to memory/visual_specs directory."""
    version = version or datetime.now().strftime("%Y%m%d_%H%M%S")
    VISUAL_SPEC_DIR.mkdir(parents=True, exist_ok=True)
    site_dir = VISUAL_SPEC_DIR / site_slug
    site_dir.mkdir(parents=True, exist_ok=True)
    filepath = site_dir / f"{version}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(visual_direction.model_dump_json(indent=2))

    designer_notes_text = "\n".join(f"- {n}" for n in visual_direction.designer_notes) if visual_direction.designer_notes else "None"
    review_path = site_dir / "REVIEW.md"
    review_content = f"""# Visual Direction Review — {site_slug}

## Primary Change
{visual_direction.primary_change}

## Rationale
{visual_direction.rationale}

## Stitch Status
{visual_direction.stitch_status}

## Impacted Components
{", ".join(visual_direction.impacted_components) if visual_direction.impacted_components else "None specified"}

## Impacted Pages
{", ".join(visual_direction.impacted_pages) if visual_direction.impacted_pages else "None specified"}

## Color Delta
{visual_direction.color_delta or "{}"}

## Typography Delta
{visual_direction.typography_delta or "{}"}

## Motion Delta
{visual_direction.motion_delta or "{}"}

## Designer Notes
{designer_notes_text}

## Open Questions
_Edit this section to capture areas where human taste matters most_

---
*This file is editable. The Manager monitors timestamp changes on this file and treats edits as signals for re-design or build adjustment.*
"""
    with open(review_path, "w", encoding="utf-8") as f:
        f.write(review_content)

    return filepath


def design(site_id: str, rec_id: str, gap_context: Optional[str] = None) -> Optional[VisualDirection]:
    """
    Main entry point: load artifacts -> build prompt -> call kilo run ->
    parse VisualDirection JSON.

    When gap_context is supplied (from MigrationManager route_back), it is
    injected as prioritized rework instructions and the output artifact is
    automatically versioned by the Manager.

    Args:
        site_id: timestamp ID of the SiteUnderstanding
        rec_id: timestamp ID of the ContentRecommendation
        gap_context: optional crisp 2-4 bullet summary of quality-gate gaps

    Returns:
        VisualDirection or None on failure
    """
    site = load_site_understanding(site_id)
    if not site:
        print(f"[ERROR] Could not load SiteUnderstanding for: {site_id}")
        return None

    recommendation = load_content_recommendation(rec_id)
    if not recommendation:
        print(f"[ERROR] Could not load ContentRecommendation for: {rec_id}")
        return None

    site_name = recommendation.site_name or site.name or "unnamed"
    site_slug = get_site_slug(site_name)

    prompt = build_designer_prompt(site, recommendation, site_slug, gap_context=gap_context)

    print(f"\n[DESIGNER] Designing {site.url} via Kilo CLI")
    print("=" * 60)
    print(f"[INPUT] Site: {site_id}, Recommendation: {rec_id}")
    if recommendation.brand_spec:
        print(f"[BRAND] Motion: {recommendation.brand_spec.motion_philosophy}")
        print(f"[BRAND] Primary: {recommendation.brand_spec.primary_color}")

    # Phase 0.7: 120s → 300s. The designer is the largest in-chain
    # persona prompt and the most likely to need a real LLM round-trip;
    # 4 of the 35 logged gaps were timeouts at 120s.
    _DESIGNER_TIMEOUT = 600  # Phase 1.2: lifted from 300 — Stitch integration + iterations
    _DESIGNER_MAX_RETRIES = 2  # retries ON TOP of the initial attempt

    stdout = ""
    last_text = None
    invoke_failed = False
    last_errors: list[str] = []
    json_str: Optional[str] = None

    for attempt in range(_DESIGNER_MAX_RETRIES + 1):
        result = invoke_kilo_safe(
            prompt=prompt,
            context={"site_id": site_id, "rec_id": rec_id, "url": site.url},
            working_dir=".",
            persona="ui_designer",
            timeout=_DESIGNER_TIMEOUT,
            on_timeout=make_timeout_callback(
                persona="ui_designer",
                migration_id_fn=lambda: site_id,
                default_timeout_s=_DESIGNER_TIMEOUT,
            ),
        )

        if not result.success:
            print(f"[ERROR] Kilo invocation failed (attempt {attempt + 1}): {result.errors}")
            last_errors = result.errors
            invoke_failed = True
            break  # don't retry infra-level failures

        stdout = result.summary or ""
        last_text = _collect_last_text(stdout)
        print(f"[KILO] Output received (attempt {attempt + 1}, {len(stdout)} chars)")

        # Happy path: parse and we're done.
        try:
            data = extract_json(stdout)
            json_str = json.dumps(data)
            break
        except JSONExtractionError as e:
            print(
                f"[WARN] JSON extraction failed (attempt {attempt + 1}): {e.reason}"
            )
            if last_text:
                print(f"[TEXT] Last text event (first 500): {last_text[:500]}")
            if attempt < _DESIGNER_MAX_RETRIES:
                print(f"[RETRY] Re-invoking Kilo ({attempt + 2}/{_DESIGNER_MAX_RETRIES + 1})")
                continue
            # Out of retries. Fall through to lenient_parse below.
            json_str = None
            break

    # Handle infra-level failure.
    if invoke_failed:
        if any("not found" in e.lower() for e in last_errors):
            log_gap(
                migration_id=site_id,
                gap_type="gate_failure",
                source_persona="ui_designer",
                target_persona="ui_designer",
                description="'kilo' command not found in PATH",
                suggested_fix="Ensure Kilo CLI is installed and in system PATH",
                severity="high",
            )
        return None

    # Lenient fallback: when all retries fail, try to salvage any
    # partial VisualDirection fields from the raw Kilo output. This
    # converts a "could not extract JSON" hard failure into a degraded
    # VisualDirection that still has primary_change / rationale set.
    if json_str is None:
        salvage_source = last_text or stdout
        salvaged = lenient_parse_visual_direction(salvage_source)
        if salvaged:
            print(
                f"[LENIENT] Recovered {len(salvaged)} VisualDirection fields "
                f"from Kilo output (primary_change set: {bool(salvaged.get('primary_change'))})"
            )
            json_str = json.dumps(salvaged)
            log_gap(
                migration_id=site_id,
                gap_type="degraded_artifact",
                source_persona="ui_designer",
                target_persona="ui_designer",
                description=(
                    f"Designer output required lenient_parse; recovered "
                    f"{list(salvaged.keys())} from unparseable Kilo response"
                ),
                suggested_fix=(
                    "Inspect Kilo output — likely truncated or wrapped in "
                    "markdown that broke the JSON fence"
                ),
                severity="medium",
            )
        else:
            print(f"[ERROR] Could not extract JSON from Kilo output (any attempt)")
            lines = stdout.splitlines()
            print(f"[KILO] Got {len(lines)} NDJSON events")
            # Phase 0: silent fallback to "{}" is REMOVED. We log a HIGH-severity
            # gap with target_persona=ui_designer so the manager routes back here
            # (instead of producing a useless VisualDirection downstream).
            log_gap(
                migration_id=site_id,
                gap_type="gate_failure",
                source_persona="ui_designer",
                target_persona="ui_designer",
                description="Could not extract VisualDirection JSON from Kilo output",
                suggested_fix="Check Kilo output format and prompt instructions",
                severity="high",
            )
            return None

    stitch_status = "available"
    try:
        result = subprocess.run(
            ["npx", "stitch", "status"],
            capture_output=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        if result.returncode != 0 or "not authenticated" in result.stderr.lower():
            stitch_status = "unavailable"
    except Exception:
        stitch_status = "unavailable"

    visual_direction = parse_visual_direction(
        json_str,
        stitch_status=stitch_status,
        brand_spec=recommendation.brand_spec if recommendation else None,
    )
    filepath = save_visual_direction(visual_direction, site_slug)
    print(f"  [OK] VisualDirection created")
    print(f"  [OUTPUT] {filepath}")
    print(f"  [STITCH] {visual_direction.stitch_status}")
    print(f"  [PRIMARY CHANGE] {visual_direction.primary_change or '(fallback)'}")
    return visual_direction


if __name__ == "__main__":
    import sys

    site_id = sys.argv[1] if len(sys.argv) > 1 else "--latest"
    rec_id = sys.argv[2] if len(sys.argv) > 2 else site_id

    if site_id == "--latest":
        from skills.agentic.builder_agent import (
            list_site_understandings,
            list_recommendations,
        )
        sites = list_site_understandings()
        recs = list_recommendations()
        if sites:
            site_id = sites[0].stem
            rec_id = recs[0].stem if recs else site_id
            print(f"[LATEST] Using site: {site_id}, rec: {rec_id}")

    result = design(site_id, rec_id)
    if result:
        print(result.model_dump_json(indent=2))
    else:
        print("Design failed.")
        sys.exit(1)