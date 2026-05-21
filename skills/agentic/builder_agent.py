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
import tempfile
import os
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from models.site_schemas import (
    SiteUnderstanding,
    SiteArchitecture,
    ContentRecommendation,
    BuildManifest,
    PolishChange,
    SelfCritique,
)


MEMORY_DIR = Path("memory/site_understandings")
ARCHITECTURE_DIR = Path("memory/site_architectures")
RECOMMENDATION_DIR = Path("memory/site_recommendations")
OUTPUT_DIR = Path("memory/site_builds")
PERSONA_PATH = Path("registry/personas/builder_specialist.md")


def build_builder_prompt(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
    recommendation: ContentRecommendation,
) -> str:
    """Build the prompt that Kilo CLI will execute."""
    persona = PERSONA_PATH.read_text() if PERSONA_PATH.exists() else ""

    site_json = site.model_dump_json(indent=2)
    arch_json = architecture.model_dump_json(indent=2)
    rec_json = recommendation.model_dump_json(indent=2)

    return f"""{persona}

## Task
Build a complete, production-ready site implementation from the following three artifacts.

## Input SiteUnderstanding
{site_json}

## Input SiteArchitecture
{arch_json}

## Input ContentRecommendation (with chosen variant + brand_spec)
{rec_json}

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
Write all generated files to the directory: output/
Key files to generate:
- app/page.tsx (or appropriate page file for the target framework)
- app/globals.css (with full BrandSpec tokens as CSS custom properties)
- tailwind.config.js (with BrandSpec color/typography tokens)
- components/ (one file per component from SiteArchitecture.components)
- package.json
- next.config.js (or appropriate config for target framework)
- README.md

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


def build(site_id: str, arch_id: str, rec_id: str) -> Optional[BuildManifest]:
    """
    Main entry point: load all three artifacts -> build prompt -> call kilo run ->
    parse manifest + write code files.

    Args:
        site_id: timestamp ID of the SiteUnderstanding
        arch_id: timestamp ID of the SiteArchitecture
        rec_id: timestamp ID of the ContentRecommendation

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

    prompt = build_builder_prompt(site, architecture, recommendation)

    print(f"\n[BUILDER] Building {site.url} via Kilo CLI")
    print("=" * 60)
    print(f"[INPUT] Site: {site_id}, Architecture: {arch_id}, Recommendation: {rec_id}")
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
        return None
    except FileNotFoundError:
        print("[ERROR] 'kilo' command not found. Is Kilo CLI installed and in PATH?")
        return None

    if result.returncode != 0:
        print(f"[ERROR] Kilo CLI exited with code {result.returncode}")
        print(f"[STDERR] {result.stderr[:500] if result.stderr else ''}")
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
        # Debug: show all text events
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
        print(f"  [OK] Build complete")
        print(f"  [QUALITY] Score: {manifest.overall_quality_score:.0f}/100")
        print(f"  [POLISH] {len(manifest.ui_polish_changes)} changes logged")
        if manifest.self_critique:
            print(f"  [CRITIQUE] Severity: {manifest.self_critique.severity}")
        save_build_manifest(manifest, site_id)
    else:
        print("[ERROR] JSON parsed but failed schema validation")

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