"""
architect_agent.py — Phase 2 Agentic Architect (Kilo CLI as execution engine)

Architecture:
- Python: thin glue — loads SiteUnderstanding, builds prompt, calls kilo run, parses JSON
- Kilo CLI: handles all agentic logic (persona + MCP tools + LLM reasoning)
- No LangGraph, no LangChain, no custom agent loops

Kilo CLI handles:
  - Loading the persona (embedded in prompt)
  - LLM reasoning over SiteUnderstanding data
  - Returns text/JSON output

Usage:
    from skills.agentic.architect_agent import architect
    result = architect("20260520_142439")
"""

import subprocess
import json
import tempfile
import os
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory.gap_ledger import log_gap
from skills.agentic.json_extract import extract_json, JSONExtractionError
from skills.agentic.kilo_callbacks import make_timeout_callback
from skills.agentic.prompt_budget import compact_site_understanding
from tools.kilo import invoke_kilo_safe

from models.site_schemas import SiteUnderstanding, SiteArchitecture


MEMORY_DIR = Path("memory/site_understandings")
OUTPUT_DIR = Path("memory/site_architectures")
PERSONA_PATH = Path("registry/personas/architect_specialist.md")


def build_architect_prompt(site: SiteUnderstanding) -> str:
    """Build the prompt that Kilo CLI will execute.

    Phase 0.6: uses compact view of SiteUnderstanding. Full JSON is
    available at memory/site_understandings/[id].json for the persona
    to re-read if it needs per-page detail.
    """
    persona = PERSONA_PATH.read_text() if PERSONA_PATH.exists() else ""

    schema_json = json.dumps(SiteArchitecture.model_json_schema(), indent=2)
    site_compact = compact_site_understanding(site)
    site_json = json.dumps(
        site_compact if isinstance(site_compact, dict) else site_compact,
        indent=2,
        default=str,
    )

    return f"""{persona}

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


def _coerce_architect_payload(data: Any) -> Any:
    """Normalise the most common drift patterns in Kilo's SiteArchitecture output.

    - Strip unknown top-level keys (the persona markdown describes fields
      like `routing_strategy`, `tier1_triggers`, `platform` that are
      not in the Pydantic schema).
    - Coerce literal "null" strings → JSON None for `image_strategy.cdn_domain`
      and a few other optional string fields where the LLM likes to
      emit "null" verbatim.

    Defensive no-op for non-dict input.
    """
    if not isinstance(data, dict):
        return data

    # Strip unknown top-level keys
    allowed = {k: v for k, v in data.items() if k in SiteArchitecture.model_fields}
    data = allowed

    # Coerce literal "null" string in image_strategy.cdn_domain
    if "image_strategy" in data and isinstance(data["image_strategy"], dict):
        cdn = data["image_strategy"].get("cdn_domain")
        if cdn == "null":
            data["image_strategy"]["cdn_domain"] = None

    # Coerce literal "null" string in per-page optional fields. Kilo
    # sometimes emits "null" (the string) when it means null (the
    # value) for Optional fields like cms_content_type / template_id.
    if "pages" in data and isinstance(data["pages"], list):
        for page in data["pages"]:
            if not isinstance(page, dict):
                continue
            for opt_field in ("cms_content_type", "template_id"):
                if isinstance(page.get(opt_field), str) and page[opt_field] == "null":
                    page[opt_field] = None

    return data


def _retry_prompt_for_reemit() -> str:
    """Short, terse re-emit prompt used after a first extraction failure.

    The Kilo output was either truncated or prose. We ask for a clean
    JSON-only re-emit. No markdown fences, no prose, no schema dump —
    we already have the JSON shape in the original prompt; we just need
    the model to produce it again, smaller.
    """
    return (
        "Your previous response was not parseable JSON. "
        "Re-emit the SiteArchitecture as a single JSON object "
        "(no ``` fence, no prose, no comments). "
        "Example: {\"source_url\": \"https://x.com\", "
        "\"target_stack\": {\"framework\": \"nextjs\"}} "
        "Keep it under 1500 chars. Use snake_case for field names."
    )


def parse_and_validate(
    raw_json: str,
    fallback_source_url: Optional[str] = None,
) -> Optional[SiteArchitecture]:
    """Parse and validate JSON against SiteArchitecture schema.

    Two-stage:
      1. Strict pass: coerce drift patterns, fill missing source_url
         from the fallback if provided, attempt validation.
      2. Lenient pass: drop any remaining unknown fields, retry.

    Returns None only if both passes fail.
    """
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    # Pass 1: strict, with coercion
    coerced = _coerce_architect_payload(data)
    if fallback_source_url and not coerced.get("source_url"):
        coerced["source_url"] = fallback_source_url
    try:
        return SiteArchitecture(**coerced)
    except Exception as e:
        first_error = str(e)
    else:
        # Will not reach here due to return above, but keeps the linter happy
        return None

    # Pass 2: lenient — strip everything not in the schema
    allowed = {k: v for k, v in data.items() if k in SiteArchitecture.model_fields}
    if fallback_source_url and not allowed.get("source_url"):
        allowed["source_url"] = fallback_source_url
    try:
        return SiteArchitecture(**allowed)
    except Exception as e:
        print(f"[WARN] Both validation passes failed: {first_error} / {e}")
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
    """Load a saved SiteArchitecture from memory directory.

    Companion to load_site_understanding. Both are now used by the
    Phase 1.1 Forge Room personas (data_engineer, backend_architect,
    frontend_architect, integration_coordinator, deploy_specialist)
    which read their upstream artifacts from the blackboard rather
    than receiving them as kwargs.
    """
    if not arch_id:
        return None
    arch_path = OUTPUT_DIR / f"{arch_id}.json"
    if not arch_path.exists():
        arch_path = Path(arch_id)
    try:
        with open(arch_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SiteArchitecture(**data)
    except Exception as e:
        print(f"[ERROR] Failed to load SiteArchitecture: {e}")
        return None


def save_site_architecture(architecture: SiteArchitecture, output_id: Optional[str] = None) -> Path:
    """Save SiteArchitecture to JSON file in memory directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not output_id:
        from datetime import datetime
        output_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = f"{output_id}.json"
    filepath = OUTPUT_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(architecture.model_dump_json(indent=2))

    return filepath


def list_site_understandings() -> list[Path]:
    """List all saved SiteUnderstanding files."""
    if not MEMORY_DIR.exists():
        return []
    return sorted(MEMORY_DIR.glob("*.json"), reverse=True)


def architect(site_id: str) -> Optional[SiteArchitecture]:
    """
    Main entry point: load SiteUnderstanding -> build prompt -> call kilo run -> parse JSON.

    Args:
        site_id: timestamp ID of the SiteUnderstanding (e.g., "20260520_142439")
                 or full path to a .json file
                 or "--latest" for most recent

    Returns:
        SiteArchitecture or None on failure
    """
    if site_id == "--latest":
        files = list_site_understandings()
        if not files:
            print("[ERROR] No SiteUnderstanding files found in memory/")
            return None
        site_id = files[0].stem
        print(f"[ARCHITECT] Using latest: {files[0].name}")

    site = load_site_understanding(site_id)
    if not site:
        print(f"[ERROR] Could not load SiteUnderstanding for: {site_id}")
        return None

    prompt = build_architect_prompt(site)

    print(f"\n[ARCHITECT] Analyzing {site.url} via Kilo CLI")
    print("=" * 60)

    # Phase 0.5: route through invoke_kilo_safe so prompt-size + timeout
    # guard-rails apply uniformly.
    result = invoke_kilo_safe(
        prompt=prompt,
        context={"site_id": site_id, "url": site.url},
        working_dir=".",
        persona="architect_specialist",
        timeout=300,
        on_timeout=make_timeout_callback(
            persona="architect_specialist",
            migration_id_fn=lambda: site_id,
            default_timeout_s=300,
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
        print(f"[WARN] Could not extract JSON from Kilo output (first attempt): {e.reason}")
        lines = stdout.splitlines()
        print(f"[KILO] Got {len(lines)} NDJSON events")
        if last_text:
            print(f"[TEXT] Last text event: {last_text[:500]}")

        # Phase 0.6.2 reliability: retry with a terse re-emit prompt.
        # Common cause is truncation to 2K chars; the retry asks for
        # a small (<1500 char) JSON-only re-emit.
        print(f"[ARCHITECT] Retrying with terse re-emit prompt...")
        retry_prompt = _retry_prompt_for_reemit()
        retry_result = invoke_kilo_safe(
            prompt=retry_prompt,
            context={"site_id": site_id, "url": site.url, "mode": "reemit"},
            working_dir=".",
            persona="architect_specialist",
            timeout=120,
            on_timeout=make_timeout_callback(
                persona="architect_specialist",
                migration_id_fn=lambda: site_id,
                default_timeout_s=120,
            ),
        )
        if not retry_result.success:
            print(f"[ERROR] Kilo retry invocation failed: {retry_result.errors}")
            log_gap(
                migration_id=site_id,
                gap_type="gate_failure",
                source_persona="architect_specialist",
                target_persona="architect_specialist",
                description=(
                    f"Could not extract SiteArchitecture JSON from Kilo output (after retry): {e.reason}"
                ),
                suggested_fix="Check Kilo output format and prompt instructions",
                severity="high",
            )
            return None
        stdout = retry_result.summary or ""
        try:
            data = extract_json(stdout)
        except JSONExtractionError as e2:
            print(f"[ERROR] Could not extract JSON from Kilo output (after retry): {e2.reason}")
            log_gap(
                migration_id=site_id,
                gap_type="gate_failure",
                source_persona="architect_specialist",
                target_persona="architect_specialist",
                description=(
                    f"Could not extract SiteArchitecture JSON from Kilo output (after retry): {e2.reason}"
                ),
                suggested_fix="Check Kilo output format and prompt instructions",
                severity="high",
            )
            return None

    json_str = json.dumps(data)

    # Pass fallback_source_url so the lenient validator can fill the
    # only-required top-level field when Kilo forgot it. site.url
    # is a Pydantic HttpUrl — cast to plain str to satisfy the
    # SiteArchitecture.source_url: str field.
    fallback_url = str(site.url) if site.url else None
    validated = parse_and_validate(json_str, fallback_source_url=fallback_url)
    if validated:
        print(f"  [OK] Architecture complete")
        print(f"  [STACK] {validated.target_stack.get('framework', 'unknown')} + {validated.target_stack.get('styling', 'unknown')}")
        print(f"  [PAGES] {len(validated.pages)} pages mapped")
        print(f"  [COMPONENTS] {len(validated.components)} components specified")
        validated.source_understanding_id = site_id
        save_site_architecture(validated, site_id)
    else:
        print("[ERROR] JSON parsed but failed schema validation")
        log_gap(
            migration_id=site_id,
            gap_type="gate_failure",
            source_persona="architect_specialist",
            target_persona="architect_specialist",
            description="SiteArchitecture JSON parsed but failed Pydantic schema validation",
            suggested_fix="Check that Kilo produces valid SiteArchitecture JSON per schema",
            severity="high",
        )

    return validated


if __name__ == "__main__":
    import sys
    site_id = sys.argv[1] if len(sys.argv) > 1 else "--latest"
    result = architect(site_id)
    if result:
        print(result.model_dump_json(indent=2))
    else:
        print("Architecture failed.")
        sys.exit(1)