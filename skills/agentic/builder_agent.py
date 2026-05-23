"""
builder_agent.py — Phase 3/4 Agentic Builder (Kilo CLI as execution engine)

Architecture:
- Python: thin glue — loads SiteUnderstanding + SiteArchitecture + ContentRecommendation,
           builds prompt, calls kilo run, parses JSON + writes code files
- Kilo CLI: handles all agentic logic (persona + LLM reasoning + code generation)
- No LangGraph, no LangChain, no custom agent loops

Kilo CLI handles:
  - Loading the persona (embedded in prompt)
  - LLM reasoning over all three input artifacts + brand_spec
  - Generating production-grade code files
  - Producing BuildManifest JSON

Usage:
    from skills.agentic.builder_agent import build
    result = build("20260520_132936", "20260520_132936", "20260520_142439")
"""

import subprocess
import json
import sys
import tempfile
import os
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory.gap_ledger import log_gap

from models.site_schemas import (
    SiteUnderstanding,
    SiteArchitecture,
    ContentRecommendation,
    BuildManifest,
    PolishChange,
    SelfCritique,
    VisualDirection,
)


MEMORY_DIR = Path("memory/site_understandings")
ARCHITECTURE_DIR = Path("memory/site_architectures")
RECOMMENDATION_DIR = Path("memory/site_recommendations")
VISUAL_SPEC_DIR = Path("memory/visual_specs")
OUTPUT_DIR = Path("memory/site_builds")
SITES_DIR = Path("sites")
PERSONA_PATH = Path("registry/personas/builder_specialist.md")


def get_site_slug(site_name: str) -> str:
    """Derive a kebab-case site slug from a site name."""
    import re
    slug = site_name.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    slug = slug.strip('-')
    return slug or "unnamed-site"


def build_builder_prompt(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
    recommendation: ContentRecommendation,
    site_slug: str,
    visual_direction: Optional[VisualDirection] = None,
) -> str:
    """Build the prompt that Kilo CLI will execute."""
    persona = PERSONA_PATH.read_text() if PERSONA_PATH.exists() else ""

    site_json = site.model_dump_json(indent=2)
    arch_json = architecture.model_dump_json(indent=2)
    rec_json = recommendation.model_dump_json(indent=2)

    vd_section = ""
    if visual_direction:
        vd_json = visual_direction.model_dump_json(indent=2)
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

    return f"""{persona}

## Task
Build a complete, production-ready site implementation from the following artifacts.
{gap_section}

## Input SiteUnderstanding
{site_json}

## Input SiteArchitecture
{arch_json}

## Input ContentRecommendation (with chosen variant + brand_spec)
{rec_json}
{vd_section}
The chosen variant is already decided. Apply it fully. Apply the brand_spec as the design system contract.
Run the polish pass after initial generation. Log every polish change with reason + brand_spec_reference.
Run a structured self-critique after polish.

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


def parse_build_manifest(raw_json: str) -> Optional[BuildManifest]:
    """Parse and validate JSON against BuildManifest schema."""
    try:
        data = json.loads(raw_json)
        return BuildManifest(**data)
    except Exception as e:
        print(f"[WARN] Validation error: {e}")
        try:
            data = json.loads(raw_json)
            allowed = {k: v for k, v in data.items() if k in BuildManifest.model_fields}
            return BuildManifest(**allowed)
        except Exception:
            return None


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


def load_site_architecture(arch_id: str) -> Optional[SiteArchitecture]:
    """Load a saved SiteArchitecture from memory directory."""
    if not arch_id:
        return None
    arch_path = ARCHITECTURE_DIR / f"{arch_id}.json"
    if not arch_path.exists():
        arch_path = Path(arch_id)
    try:
        with open(arch_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SiteArchitecture(**data)
    except Exception as e:
        print(f"[ERROR] Failed to load SiteArchitecture: {e}")
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
    """Load the latest VisualDirection from memory/visual_specs/[site_slug]/."""
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
                print(f"  [VISUAL] Loaded VisualDirection from {json_file.name}")
                print(f"  [VISUAL] stitch_status: {vd.stitch_status}")
                print(f"  [VISUAL] primary_change: {vd.primary_change[:80]}...")
                return vd
        except Exception as e:
            print(f"[WARN] Failed to load VisualDirection {json_file}: {e}")
            continue
    return None


def save_build_manifest(manifest: BuildManifest, output_id: str) -> Path:
    """Save BuildManifest to JSON file in memory directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{output_id}.json"
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(manifest.model_dump_json(indent=2))
    return filepath


def list_recommendations() -> list[Path]:
    """List all saved ContentRecommendation files."""
    if not RECOMMENDATION_DIR.exists():
        return []
    return sorted(RECOMMENDATION_DIR.glob("*.json"), reverse=True)


def list_architectures() -> list[Path]:
    """List all saved SiteArchitecture files."""
    if not ARCHITECTURE_DIR.exists():
        return []
    return sorted(ARCHITECTURE_DIR.glob("*.json"), reverse=True)


def list_site_understandings() -> list[Path]:
    """List all saved SiteUnderstanding files."""
    if not MEMORY_DIR.exists():
        return []
    return sorted(MEMORY_DIR.glob("*.json"), reverse=True)


def build(site_id: str, arch_id: str, rec_id: str, gap_context: Optional[str] = None) -> Optional[BuildManifest]:
    """
    Main entry point: load all three artifacts -> build prompt -> call kilo run ->
    parse manifest + write code files.

    When gap_context is supplied (from MigrationManager route_back), the
    prompt includes prioritized rework instructions. Builder always runs
    `impeccable detect` as its final step and emits the report.

    Args:
        site_id: timestamp ID of the SiteUnderstanding
        arch_id: timestamp ID of the SiteArchitecture
        rec_id: timestamp ID of the ContentRecommendation
        gap_context: optional crisp 2-4 bullet summary of quality-gate gaps

    Returns:
        BuildManifest or None on failure
    """
    site = load_site_understanding(site_id)
    if not site:
        print(f"[ERROR] Could not load SiteUnderstanding for: {site_id}")
        return None

    architecture = load_site_architecture(arch_id)
    if not architecture:
        print(f"[ERROR] Could not load SiteArchitecture for: {arch_id}")
        return None

    recommendation = load_content_recommendation(rec_id)
    if not recommendation:
        print(f"[ERROR] Could not load ContentRecommendation for: {rec_id}")
        return None

    site_name = recommendation.site_name or site.name or "unnamed"
    site_slug = get_site_slug(site_name)

    visual_direction = load_visual_direction(site_slug)
    if not visual_direction:
        print(f"  [VISUAL] No VisualDirection found — using BrandSpec as final authority")
        log_gap(
            migration_id=site_id,
            gap_type="missing_data",
            source_persona="ui_designer",
            description=f"No VisualDirection found for site '{site_slug}' — Builder applying BrandSpec only",
            suggested_fix="Run designer_agent.py to produce VisualDirection before builder",
            severity="medium",
        )

    prompt = build_builder_prompt(site, architecture, recommendation, site_slug, visual_direction, gap_context=gap_context)

    print(f"\n[BUILDER] Building {site.url} via Kilo CLI")
    print("=" * 60)
    print(f"[INPUT] Site: {site_id}, Architecture: {arch_id}, Recommendation: {rec_id}")
    print(f"[OUTPUT] sites/{site_slug}/")
    if recommendation.brand_spec:
        print(f"[BRAND] Motion: {recommendation.brand_spec.motion_philosophy}")
        print(f"[BRAND] Primary: {recommendation.brand_spec.primary_color}")
    print(f"[VARIANT] Chosen: {recommendation.chosen_variant}")

    try:
        import platform
        if platform.system() == "Windows":
            node_exe = (
                "C:\\Program Files\\nodejs\\node.exe"
                if Path("C:\\Program Files\\nodejs\\node.exe").exists()
                else "node"
            )
            kilo_bin_local = (
                Path(__file__).resolve().parents[2]
                / "node_modules"
                / "@kilocode"
                / "cli"
                / "bin"
                / "kilo"
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
            source_persona="builder",
            description="Kilo CLI timed out after 10 minutes",
            suggested_fix="Increase timeout or simplify build scope",
            severity="high",
        )
        return None
    except FileNotFoundError:
        print("[ERROR] 'kilo' command not found. Is Kilo CLI installed and in PATH?")
        log_gap(
            migration_id=site_id,
            gap_type="gate_failure",
            source_persona="builder",
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
            source_persona="builder",
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
            source_persona="builder",
            description="Could not extract BuildManifest JSON from Kilo output",
            suggested_fix="Check Kilo output format and prompt instructions",
            severity="high",
        )
        for i, line in enumerate(lines):
            try:
                event = json.loads(line.strip())
                if event.get("type") == "text":
                    text = event.get("part", {}).get("text", "")
                    print(f"  [TEXT_EVENT {i}] len={len(text)} start={text[:100]}")
            except:
                pass
        return None

    manifest = parse_build_manifest(json_str)
    if manifest:
        manifest.output_dir = f"sites/{site_slug}/"
        print(f"  [OK] Build complete")
        print(f"  [OUTPUT] sites/{site_slug}/")
        print(f"  [QUALITY] Score: {manifest.overall_quality_score:.0f}/100")
        print(f"  [POLISH] {len(manifest.ui_polish_changes)} changes logged")
        if manifest.self_critique:
            print(f"  [CRITIQUE] Severity: {manifest.self_critique.severity}")
            if manifest.self_critique.severity == "high":
                for issue in manifest.self_critique.brand_token_violations:
                    log_gap(
                        migration_id=site_id,
                        gap_type="visual_mismatch",
                        source_persona="builder",
                        description=f"Brand token violation: {issue}",
                        suggested_fix=manifest.self_critique.recommended_action,
                        severity="high",
                    )
        save_build_manifest(manifest, site_id)
    else:
        print("[ERROR] JSON parsed but failed schema validation")
        log_gap(
            migration_id=site_id,
            gap_type="gate_failure",
            source_persona="builder",
            description="BuildManifest JSON parsed but failed Pydantic schema validation",
            suggested_fix="Check that Kilo produces valid BuildManifest JSON per schema",
            severity="high",
        )

    return manifest


if __name__ == "__main__":
    import sys
    site_id = sys.argv[1] if len(sys.argv) > 1 else "--latest"
    arch_id = sys.argv[2] if len(sys.argv) > 2 else site_id
    rec_id = sys.argv[3] if len(sys.argv) > 3 else site_id

    if site_id == "--latest":
        sites = list_site_understandings()
        archs = list_architectures()
        recs = list_recommendations()
        if sites:
            site_id = sites[0].stem
            arch_id = archs[0].stem if archs else site_id
            rec_id = recs[0].stem if recs else site_id
            print(f"[LATEST] Using site: {site_id}, arch: {arch_id}, rec: {rec_id}")

    result = build(site_id, arch_id, rec_id)
    if result:
        print(result.model_dump_json(indent=2))
    else:
        print("Build failed.")
        sys.exit(1)