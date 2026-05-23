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
    """Build the prompt that Kilo CLI will execute. When gap_context is provided, inject it as prioritized rework instructions."""
    persona = PERSONA_PATH.read_text() if PERSONA_PATH.exists() else ""

    site_json = site.model_dump_json(indent=2)
    rec_json = recommendation.model_dump_json(indent=2)

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

## Input SiteUnderstanding
{site_json}

## Input ContentRecommendation (with BrandSpec)
{rec_json}

## Output
Your final response must include:
1. A complete VisualDirection JSON
2. Design reasoning traceable to BrandSpec tokens

## VisualDirection Schema
Use this exact schema for the VisualDirection:
{json.dumps(VisualDirection.model_json_schema(), indent=2)}

## BrandSpec for this Site
{recommendation.brand_spec.model_dump_json(indent=2) if recommendation.brand_spec else '{}'}

## Guidance
- Derive all decisions from BrandSpec tokens + Stitch output (if available)
- Every color must trace to a BrandSpec token (no hardcoded hex)
- Every motion class must match the motion_philosophy value
- For each page route, specify grid_system, spacing_philosophy, section_order
- Map all component interactions to motion classes matching the motion_philosophy
- Store output in: memory/visual_specs/{site_slug}/[timestamp].json

Begin design now."""


def extract_json_from_output(stdout: str) -> tuple[Optional[str], Optional[str]]:
    """Extract JSON object from Kilo CLI --format json output.

    Kilo outputs NDJSON events. Find the last text event and extract JSON from it.
    Returns (json_str, last_text) for debugging.
    """
    stdout = stdout.strip()

    try:
        json.loads(stdout)
        return stdout, None
    except json.JSONDecodeError:
        pass

    last_text = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                last_text = event["part"].get("text", "")
        except json.JSONDecodeError:
            continue

    if last_text:
        last_text = last_text.strip()
        try:
            json.loads(last_text)
            return last_text, last_text
        except json.JSONDecodeError:
            pass

        first_brace = last_text.find("{")
        last_brace = last_text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace >= first_brace:
            json_str = last_text[first_brace : last_brace + 1]
            try:
                json.loads(json_str)
                return json_str, last_text
            except json.JSONDecodeError:
                pass

    first_brace = stdout.find("{")
    last_brace = stdout.rfind("}")
    if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
        return None, None

    json_str = stdout[first_brace : last_brace + 1]
    try:
        json.loads(json_str)
        return json_str, None
    except json.JSONDecodeError:
        return None, None


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

    try:
        import platform
        if platform.system() == "Windows":
            node_exe = (
                "C:\\Program Files\\nodejs\\node.exe"
                if Path("C:\\Program Files\\nodejs\\node.exe").exists()
                else "node"
            )
            kilo_bin_fallback = Path(
                "C:\\Users\\micha\\AppData\\Roaming\\npm\\node_modules\\@kilocode\\cli\\bin\\kilo"
            )
            kilo_bin = kilo_bin_fallback

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(prompt)
                prompt_file = f.name

            try:
                result = subprocess.run(
                    [node_exe, str(kilo_bin), "run", "--format", "json", "--auto", "--", f"@{prompt_file}"],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=600,
                )
            finally:
                try:
                    os.unlink(prompt_file)
                except Exception:
                    pass
        else:
            result = subprocess.run(
                ["kilo", "run", "--format", "json", "--auto", "--", prompt],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
    except subprocess.TimeoutExpired:
        print("[ERROR] Kilo CLI timed out after 10 minutes")
        log_gap(
            migration_id=site_id,
            gap_type="gate_failure",
            source_persona="ui_designer",
            description="Kilo CLI timed out after 10 minutes during design phase",
            suggested_fix="Increase timeout or simplify design scope",
            severity="medium",
        )
        return None
    except FileNotFoundError:
        print("[ERROR] 'kilo' command not found. Is Kilo CLI installed and in PATH?")
        log_gap(
            migration_id=site_id,
            gap_type="gate_failure",
            source_persona="ui_designer",
            description="'kilo' command not found in PATH",
            suggested_fix="Ensure Kilo CLI is installed and in system PATH",
            severity="high",
        )
        return None

    if result.returncode != 0:
        print(f"[ERROR] Kilo CLI exited with code {result.returncode}")
        print(f"[STDERR] {result.stderr[:500] if result.stderr else ''}")
        log_gap(
            migration_id=site_id,
            gap_type="gate_failure",
            source_persona="ui_designer",
            description=f"Kilo CLI exited with code {result.returncode}: {result.stderr[:200] if result.stderr else 'no stderr'}",
            suggested_fix="Check Kilo CLI configuration and prompt syntax",
            severity="high",
        )
        return None

    stdout = result.stdout or ""

    print(f"[KILO] Output received ({len(stdout)} chars)")

    json_str, last_text = extract_json_from_output(stdout)
    if not json_str:
        print("[ERROR] Could not extract JSON from Kilo output")
        lines = result.stdout.splitlines()
        print(f"[KILO] Got {len(lines)} NDJSON events")
        if last_text:
            print(f"[TEXT] Last text event: {last_text[:500]}")
        log_gap(
            migration_id=site_id,
            gap_type="gate_failure",
            source_persona="ui_designer",
            description="Could not extract VisualDirection JSON from Kilo output",
            suggested_fix="Check Kilo output format and prompt instructions",
            severity="medium",
        )
        return None

    stitch_status = "available"
    try:
        result = subprocess.run(
            ["npx", "stitch", "status"],
            capture_output=True,
            timeout=10,
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
    if visual_direction:
        filepath = save_visual_direction(visual_direction, site_slug)
        print(f"  [OK] VisualDirection created")
        print(f"  [OUTPUT] {filepath}")
        print(f"  [STITCH] {visual_direction.stitch_status}")
        print(f"  [PRIMARY CHANGE] {visual_direction.primary_change}")
    else:
        print("[ERROR] JSON parsed but failed schema validation")
        log_gap(
            migration_id=site_id,
            gap_type="gate_failure",
            source_persona="ui_designer",
            description="VisualDirection JSON parsed but failed Pydantic schema validation",
            suggested_fix="Check that Kilo produces valid VisualDirection JSON per schema",
            severity="medium",
        )

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