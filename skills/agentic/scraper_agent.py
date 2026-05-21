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

import subprocess
import json
from pathlib import Path
from typing import Optional

from models.site_schemas import SiteUnderstanding


PERSONA_PATH = Path("registry/personas/scraper_specialist.md")


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


def parse_and_validate(raw_json: str) -> Optional[SiteUnderstanding]:
    """Parse and validate JSON against SiteUnderstanding schema."""
    try:
        data = json.loads(raw_json)

        if "contact_info" in data and isinstance(data["contact_info"], dict):
            data["contact_info"] = {
                k: v for k, v in data["contact_info"].items() if v is not None
            }

        for page in data.get("pages", []):
            if "images" in page and isinstance(page["images"], list):
                page["images"] = [img for img in page["images"] if img.get("src")]

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
                    page["images"] = [img for img in page["images"] if img.get("src")]
            allowed = {k: v for k, v in data.items() if k in SiteUnderstanding.model_fields}
            return SiteUnderstanding(**allowed)
        except Exception:
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

    try:
        import platform
        if platform.system() == "Windows":
            node_exe = (
                "C:\\Program Files\\nodejs\\node.exe"
                if Path("C:\\Program Files\\nodejs\\node.exe").exists()
                else "node"
            )
            kilo_bin = (
                Path(__file__).resolve().parents[2]
                / "node_modules"
                / "@kilocode"
                / "cli"
                / "bin"
                / "kilo"
            )
            if not kilo_bin.exists():
                kilo_bin = Path(
                    "C:\\Users\\micha\\AppData\\Roaming\\npm\\node_modules\\@kilocode\\cli\\bin\\kilo"
                )
            result = subprocess.run(
                [node_exe, str(kilo_bin), "run", "--format", "json", "--auto", "--", prompt],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
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
        print(f"  [OK] Scraping complete")
        print(f"  [PAGES] {len(validated.pages)} pages discovered")
        print(f"  [PLATFORM] {validated.platform.value} ({validated.platform_confidence:.0%})")
    else:
        print("[ERROR] JSON parsed but failed schema validation")

    return validated


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    result = scrape(url)
    if result:
        print(result.model_dump_json(indent=2))
    else:
        print("Scraping failed.")
        sys.exit(1)