"""
marketing_agent.py — Phase 3 Agentic Marketing Specialist (Kilo CLI as execution engine)

Architecture:
- Python: thin glue — loads SiteUnderstanding + SiteArchitecture, builds prompt, calls kilo run, parses JSON
- Kilo CLI: handles all agentic logic (persona + LLM reasoning)
- No LangGraph, no LangChain, no custom agent loops

Kilo CLI handles:
  - Loading the persona (embedded in prompt)
  - LLM reasoning over SiteUnderstanding + SiteArchitecture data
  - Returns text/JSON output

Usage:
    from skills.agentic.marketing_agent import market
    result = market("20260520_142439", "20260520_143100")
"""

import subprocess
import json
import tempfile
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory.gap_ledger import log_gap
from skills.agentic.json_extract import extract_json, JSONExtractionError
from skills.agentic.kilo_callbacks import make_timeout_callback
from skills.agentic.prompt_budget import compact_site_understanding, compact_site_architecture
from tools.kilo import invoke_kilo_safe

from models.site_schemas import (
    SiteUnderstanding,
    SiteArchitecture,
    ContentRecommendation,
)


MEMORY_DIR = Path("memory/site_understandings")
ARCHITECTURE_DIR = Path("memory/site_architectures")
RECOMMENDATION_DIR = Path("memory/site_recommendations")
OUTPUT_DIR = Path("memory/site_recommendations")
PERSONA_PATH = Path("registry/personas/marketing_specialist.md")


def build_marketing_prompt(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
) -> str:
    """Build the prompt that Kilo CLI will execute.

    Phase 0.6: uses compact views of both SiteUnderstanding and
    SiteArchitecture. Full JSON is available at memory/<dir>/[id].json.
    """
    persona = PERSONA_PATH.read_text() if PERSONA_PATH.exists() else ""

    schema_json = json.dumps(ContentRecommendation.model_json_schema(), indent=2)
    site_compact = compact_site_understanding(site)
    arch_compact = compact_site_architecture(architecture)
    site_json = json.dumps(site_compact, indent=2, default=str)
    arch_json = json.dumps(arch_compact, indent=2, default=str)

    return f"""{persona}

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


def extract_json_from_output(stdout: str) -> tuple[Optional[str], Optional[str]]:
    """Extract JSON object from Kilo CLI --format json output.

    Returns (json_str, last_text) for debugging. Returns (None, last_text)
    on extraction failure — callers MUST treat None as a hard error.
    Thin shim over the shared extractor.
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


def parse_and_validate(raw_json: str) -> Optional[ContentRecommendation]:
    """Parse and validate JSON against ContentRecommendation schema."""
    try:
        data = json.loads(raw_json)
        return ContentRecommendation(**data)
    except Exception as e:
        print(f"[WARN] Validation error: {e}")
        try:
            data = json.loads(raw_json)
            allowed = {k: v for k, v in data.items() if k in ContentRecommendation.model_fields}
            return ContentRecommendation(**allowed)
        except Exception:
            return None


def load_site_understanding(site_id: str) -> Optional[SiteUnderstanding]:
    """Load a saved SiteUnderstanding from memory directory."""
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


def save_content_recommendation(
    recommendation: ContentRecommendation,
    output_id: Optional[str] = None,
) -> Path:
    """Save ContentRecommendation to JSON file in memory directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not output_id:
        from datetime import datetime
        output_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = f"{output_id}.json"
    filepath = OUTPUT_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(recommendation.model_dump_json(indent=2))

    return filepath


def list_recommendations() -> list[Path]:
    """List all saved ContentRecommendation files."""
    if not OUTPUT_DIR.exists():
        return []
    return sorted(OUTPUT_DIR.glob("*.json"), reverse=True)


def list_architectures() -> list[Path]:
    """List all saved SiteArchitecture files."""
    if not ARCHITECTURE_DIR.exists():
        return []
    return sorted(ARCHITECTURE_DIR.glob("*.json"), reverse=True)


def load_content_recommendation(rec_id: str) -> Optional[ContentRecommendation]:
    """Load a saved ContentRecommendation from memory/site_recommendations/.

    Companion to market(). Both are used by the Phase 1.1 Forge Room
    personas which read their upstream artifacts from the blackboard.
    """
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


def market(site_id: str, arch_id: str) -> Optional[ContentRecommendation]:
    """
    Main entry point: load SiteUnderstanding + SiteArchitecture -> build prompt ->
    call kilo run -> parse JSON.

    Args:
        site_id: timestamp ID of the SiteUnderstanding
        arch_id: timestamp ID of the SiteArchitecture (or same as site_id to reuse)

    Returns:
        ContentRecommendation or None on failure
    """
    site = load_site_understanding(site_id)
    if not site:
        print(f"[ERROR] Could not load SiteUnderstanding for: {site_id}")
        return None

    architecture = load_site_architecture(arch_id)
    if not architecture:
        print(f"[ERROR] Could not load SiteArchitecture for: {arch_id}")
        return None

    prompt = build_marketing_prompt(site, architecture)

    print(f"\n[MARKETING] Analyzing content for {site.url} via Kilo CLI")
    print("=" * 60)

    # Phase 0.5: route through invoke_kilo_safe so prompt-size + timeout
    # guard-rails apply uniformly.
    result = invoke_kilo_safe(
        prompt=prompt,
        context={"site_id": site_id, "arch_id": arch_id, "url": site.url},
        working_dir=".",
        persona="marketing_specialist",
        timeout=600,  # Phase 1.2: lifted from 300 — content strategy + variants takes longer
        on_timeout=make_timeout_callback(
            persona="marketing_specialist",
            migration_id_fn=lambda: site_id,
            default_timeout_s=600,
        ),
    )

    if not result.success:
        print(f"[ERROR] Kilo invocation failed: {result.errors}")
        return None

    stdout = result.summary or ""
    print(f"[KILO] Output received ({len(stdout)} chars)")

    # Track last_text for debug parity.
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
        data = extract_json(stdout)
    except JSONExtractionError as e:
        print(f"[ERROR] Could not extract JSON from Kilo output: {e.reason}")
        lines = stdout.splitlines()
        print(f"[KILO] Got {len(lines)} NDJSON events")
        if last_text:
            print(f"[TEXT] Last text event: {last_text[:500]}")
        log_gap(
            migration_id=site_id,
            gap_type="gate_failure",
            source_persona="marketing_specialist",
            target_persona="marketing_specialist",
            description=f"Could not extract ContentRecommendation JSON from Kilo output: {e.reason}",
            suggested_fix="Check Kilo output format and prompt instructions",
            severity="high",
        )
        return None

    json_str = json.dumps(data)

    validated = parse_and_validate(json_str)
    if validated:
        print(f"  [OK] Content strategy complete")
        print(f"  [STRATEGY] {validated.overall_content_strategy}")
        print(f"  [VARIANTS] {len(validated.variants)} developed")
        print(f"  [CHOSEN] Variant {validated.chosen_variant} — {validated.final_rationale[:60]}...")
        validated.source_understanding_id = site_id
        validated.source_architecture_id = arch_id
        save_content_recommendation(validated, site_id)
    else:
        print("[ERROR] JSON parsed but failed schema validation")
        log_gap(
            migration_id=site_id,
            gap_type="gate_failure",
            source_persona="marketing_specialist",
            target_persona="marketing_specialist",
            description="ContentRecommendation JSON parsed but failed Pydantic schema validation",
            suggested_fix="Check that Kilo produces valid ContentRecommendation JSON per schema",
            severity="high",
        )

    return validated


if __name__ == "__main__":
    import sys
    site_id = sys.argv[1] if len(sys.argv) > 1 else "--latest"
    arch_id = sys.argv[2] if len(sys.argv) > 2 else site_id
    result = market(site_id, arch_id)
    if result:
        print(result.model_dump_json(indent=2))
    else:
        print("Marketing analysis failed.")
        sys.exit(1)