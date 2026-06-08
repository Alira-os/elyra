"""
scraper_agent.py — Phase 1 Agentic Scraper (Kilo CLI as execution engine)

Architecture:
- Python: thin glue — builds prompt, calls kilo run, parses JSON
- Kilo CLI: handles all agentic logic (persona + MCP tools + LLM reasoning + tool execution)
- No LangGraph, no LangChain, no custom agent loops

Kilo CLI handles:
  - Loading the persona (embedded in prompt)
  - Playwright + Fetch MCP tools (from kilocode/.mcp.json)
  - ReAct loop: think → tool → observe → repeat
  - Returns text/JSON output

Usage:
    result = scrape("https://example.com")
"""

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory.gap_ledger import log_gap
from skills.agentic.json_extract import extract_json, JSONExtractionError
from tools.kilo import invoke_kilo_safe
from skills.agentic.kilo_callbacks import make_timeout_callback

from models.site_schemas import SiteUnderstanding, PlatformType


PERSONA_PATH = Path("registry/personas/scraper_specialist.md")
MEMORY_DIR = Path("memory/site_understandings")

# Scraper is pre-flight: it can be retried indefinitely until a SiteUnderstanding
# is produced. We don't track a stable migration_id here, so the callback uses
# an empty string (the gap will still land in the global ledger).
_SCRAPER_MIGRATION_ID = lambda: ""  # noqa: E731
_on_scraper_timeout = make_timeout_callback(
    persona="scraper_specialist",
    migration_id_fn=_SCRAPER_MIGRATION_ID,
    default_timeout_s=300,
)


def build_scraper_prompt(url: str) -> str:
    """Build the prompt that Kilo CLI will execute."""
    persona = PERSONA_PATH.read_text() if PERSONA_PATH.exists() else ""

    schema_json = json.dumps(SiteUnderstanding.model_json_schema(), indent=2)

    return f"""{persona}

## Task
Scrape and analyze: {url}

Use the available Playwright MCP and Fetch MCP tools to explore this site thoroughly.
Build a complete SiteUnderstanding: platform detection, all pages discovered,
full navigation structure, per-page structure with components/text/content,
global assets, contact info.

## Output Contract
Output ONLY valid JSON matching this schema — no markdown, no commentary,
no text outside the JSON object:
{schema_json}

Begin exploration now."""


def extract_json_from_output(stdout: str) -> tuple[Optional[str], Optional[str]]:
    """Deprecated shim kept for backward compatibility.

    The Phase 0 shared extractor in skills/agentic/json_extract.py is now
    the single source of truth. New code should call extract_json() and
    catch JSONExtractionError.
    """
    try:
        obj = extract_json(stdout)
        return json.dumps(obj), None
    except JSONExtractionError:
        return None, None


def parse_and_validate(raw_json: str) -> Optional[SiteUnderstanding]:
    """Parse and validate JSON against SiteUnderstanding schema.

    Handles null values in required string fields by either removing invalid
    assets/images or falling back to a minimal valid SiteUnderstanding.
    """
    try:
        data = json.loads(raw_json)

        if "contact_info" in data and isinstance(data["contact_info"], dict):
            data["contact_info"] = {
                k: v for k, v in data["contact_info"].items() if v is not None
            }

        for page in data.get("pages", []):
            if "images" in page and isinstance(page["images"], list):
                page["images"] = [img for img in page["images"] if img and img.get("src")]

            # Clean up null values in components and their child structures
            if "components" in page and isinstance(page["components"], list):
                for comp in page["components"]:
                    if "assets" in comp and isinstance(comp["assets"], list):
                        comp["assets"] = [
                            a for a in comp["assets"]
                            if a and a.get("src") is not None
                        ]

        return SiteUnderstanding(**data)
    except Exception as e:
        print(f"[WARN] Validation error: {e}")
        try:
            data = json.loads(raw_json)
            if "contact_info" in data and isinstance(data["contact_info"], dict):
                data["contact_info"] = {
                    k: v for k, v in data["contact_info"].items() if v is not None
                }
            for page in data.get("pages", []):
                if "images" in page and isinstance(page["images"], list):
                    page["images"] = [img for img in page["images"] if img and img.get("src")]
                if "components" in page and isinstance(page["components"], list):
                    for comp in page["components"]:
                        if "assets" in comp and isinstance(comp["assets"], list):
                            comp["assets"] = [
                                a for a in comp["assets"]
                                if a and a.get("src") is not None
                            ]
            allowed = {k: v for k, v in data.items() if k in SiteUnderstanding.model_fields}
            return SiteUnderstanding(**allowed)
        except Exception:
            return None


def load_site_understanding(site_id: str) -> Optional[SiteUnderstanding]:
    """Load a saved SiteUnderstanding from memory/site_understandings/.

    Companion to scrape(). Both are used by the Phase 1.1 Forge Room
    personas which read their upstream artifacts from the blackboard.
    """
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


def scrape(url: str) -> Optional[SiteUnderstanding]:
    """
    Main entry point: build prompt -> call kilo run -> parse JSON.

    Kilo CLI handles all agentic logic internally:
    - Loads the persona (embedded in prompt)
    - Binds Playwright + Fetch MCP tools (from kilocode/.mcp.json)
    - Runs ReAct loop: think -> tool -> observe -> repeat
    - Returns text/JSON output
    """
    prompt = build_scraper_prompt(url)

    print(f"\n[SCAPE] Scraping {url} via Kilo CLI")
    print("=" * 60)

    # Phase 0.5: route through invoke_kilo_safe so prompt-size + timeout
    # guard-rails apply uniformly to all personas.
    result = invoke_kilo_safe(
        prompt=prompt,
        context={"url": url},
        working_dir=".",
        persona="scraper_specialist",
        timeout=300,
        on_timeout=_on_scraper_timeout,
    )

    if not result.success:
        print(f"[ERROR] Kilo invocation failed: {result.errors}")
        if any("not found" in e.lower() for e in result.errors):
            print("[ERROR] 'kilo' command not found. Is Kilo CLI installed and in PATH?")
        return None

    # invoke_kilo_safe returns a ToolResult with `summary` holding the raw Kilo
    # text/NDJSON output. We extract the JSON from that.
    stdout = result.summary or ""

    print(f"[KILO] Output received ({len(stdout)} chars)")

    # Track last_text for debugging parity with the old behavior.
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
            migration_id="",
            gap_type="gate_failure",
            source_persona="scraper_specialist",
            target_persona="scraper_specialist",
            description=f"Could not extract SiteUnderstanding JSON from Kilo output: {e.reason}",
            suggested_fix="Check Kilo output format and prompt instructions",
            severity="high",
        )
        # Return None rather than a silent minimal SiteUnderstanding: the
        # manager will treat this as a scraper failure and route back here.
        return None

    validated = parse_and_validate(json.dumps(data))
    if validated:
        print(f"  [OK] Scraping complete")
        print(f"  [PAGES] {len(validated.pages)} pages discovered")
        print(f"  [PLATFORM] {validated.platform.value} ({validated.platform_confidence:.0%})")
        return validated

    # JSON parsed but failed schema validation. This is a separate failure
    # class from extraction failure; log it as such and still return None.
    print("[WARN] JSON parsed but failed schema validation")
    log_gap(
        migration_id="",
        gap_type="gate_failure",
        source_persona="scraper_specialist",
        target_persona="scraper_specialist",
        description="SiteUnderstanding JSON parsed but failed Pydantic schema validation",
        suggested_fix="Check that Kilo produces valid SiteUnderstanding JSON per schema",
        severity="high",
    )
    return None


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    result = scrape(url)
    if result:
        print(result.model_dump_json(indent=2))
    else:
        print("Scraping failed.")
        sys.exit(1)