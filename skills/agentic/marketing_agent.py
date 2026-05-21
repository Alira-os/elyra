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
from pathlib import Path
from typing import Optional

from models.site_schemas import (
    SiteUnderstanding,
    SiteArchitecture,
    ContentRecommendation,
)


MEMORY_DIR = Path("memory/site_understandings")
ARCHITECTURE_DIR = Path("memory/site_architectures")
OUTPUT_DIR = Path("memory/site_recommendations")
PERSONA_PATH = Path("registry/personas/marketing_specialist.md")


def build_marketing_prompt(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
) -> str:
    """Build the prompt that Kilo CLI will execute."""
    persona = PERSONA_PATH.read_text() if PERSONA_PATH.exists() else ""

    schema_json = json.dumps(ContentRecommendation.model_json_schema(), indent=2)
    site_json = site.model_dump_json(indent=2)
    arch_json = architecture.model_dump_json(indent=2)

    return f"""{persona}

## Task
Analyze the following SiteUnderstanding and SiteArchitecture.
Develop two content strategy variants (A and B), then autonomously choose the winning variant.
Produce a complete ContentRecommendation.

## Input SiteUnderstanding
{site_json}

## Input SiteArchitecture
{arch_json}

## Output Contract
Output ONLY valid JSON matching this schema — no markdown, no commentary,
no text outside the JSON object:
{schema_json}

Begin content strategy analysis now."""


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
                    timeout=300,
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
                timeout=300,
            )
    except subprocess.TimeoutExpired:
        print("[ERROR] Kilo CLI timed out after 5 minutes")
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
        return None

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