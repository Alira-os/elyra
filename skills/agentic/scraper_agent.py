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


def build_scraper_prompt(url: str, retry_mode: bool = False) -> str:
    """Build the prompt that Kilo CLI will execute.

    Args:
        url: Target URL.
        retry_mode: If True, produce a tightened prompt used only when the
            first invocation failed to produce parseable JSON. Skips the
            full schema dump and short-circuits exploration so Kilo emits
            a JSON-only response.
    """
    persona = PERSONA_PATH.read_text() if PERSONA_PATH.exists() else ""

    if retry_mode:
        # Tightened retry: no schema dump, no exploration, just "emit JSON
        # exactly matching the schema you already received in the previous
        # turn." The orchestrator passes the prior prompt as context, so
        # Kilo retains the schema.
        return f"""{persona}

## Task (RETRY — previous attempt did not return parseable JSON)
Re-emit the SiteUnderstanding for: {url}

Your previous response could not be parsed as JSON. This time:

1. Do NOT call any tools — you already have all the information you need.
2. Output a single ```json fenced code block containing one valid JSON
   object that matches the SiteUnderstanding schema you were given.
3. NO prose, NO commentary, NO markdown headings, NO `text` events before
   the fence. The first and only text event MUST be the fenced JSON.
4. If you truly have no information, emit `{{}}` inside the fence.

Begin now."""

    schema_json = json.dumps(SiteUnderstanding.model_json_schema(), indent=2)
    # Phase 1.2: persona markdown's "Output Contract" section already
    # shows the SiteUnderstanding schema as an example JSON object.
    # Dumping `model_json_schema()` inline added 12.6K of duplicate
    # information (57% of the 22K prompt) without changing the LLM's
    # output. Drop it; the persona's own schema doc is enough.
    _ = schema_json  # retained for debugging; not embedded.

    return f"""{persona}

## Task
Scrape and analyze: {url}

Use the available Playwright MCP and Fetch MCP tools to explore this site thoroughly.
Build a complete SiteUnderstanding: platform detection, all pages discovered,
full navigation structure, per-page structure with components/text/content,
global assets, contact info.

## Output Contract
Output ONLY valid JSON matching the SiteUnderstanding schema documented in
the "Output Contract" section of your persona charter above. No markdown
fences, no commentary, no text outside the JSON object.

The persona's Output Contract section shows the schema as an example JSON
object. Match that shape exactly.

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
    # Phase 1.2: known-good component types per the SiteUnderstanding
    # schema. LLM scraper outputs occasionally introduce ad-hoc types
    # (e.g. "header", "sidebar", "search_bar"). Coerce anything not in
    # this set to "unknown" so the artifact survives lenient parse.
    from models.site_schemas import ComponentType, PageType
    _valid_component_types = {t.value for t in ComponentType}
    _valid_page_types = {t.value for t in PageType}

    def _coerce_page_types(pages):
        for page in pages:
            if "page_type" in page and isinstance(page["page_type"], list):
                page["page_type"] = [
                    t if t in _valid_page_types else "other"
                    for t in page["page_type"]
                    if isinstance(t, str)
                ]

    def _coerce_nav_urls(nav):
        if isinstance(nav, list):
            for node in nav:
                if isinstance(node, dict):
                    url = node.get("page_url")
                    if isinstance(url, str) and not url.startswith(("http://", "https://")):
                        node["page_url"] = None

    def _coerce_components(pages):
        for page in pages:
            if "components" in page and isinstance(page["components"], list):
                for comp in page["components"]:
                    if isinstance(comp, dict) and comp.get("type") not in _valid_component_types:
                        comp["type"] = "unknown"
                    if isinstance(comp, dict) and "assets" in comp and isinstance(comp["assets"], list):
                        comp["assets"] = [
                            a for a in comp["assets"]
                            if a and a.get("src") is not None
                        ]

    def _clean(data):
        if "contact_info" in data and isinstance(data["contact_info"], dict):
            ci = {}
            for k, v in data["contact_info"].items():
                if v is None:
                    continue
                if k == "geo" and isinstance(v, dict):
                    lat = v.get("lat")
                    lng = v.get("lng")
                    if lat is not None and lng is not None:
                        v = f"{lat},{lng}"
                    else:
                        v = json.dumps(v)
                ci[k] = v
            data["contact_info"] = ci
        for page in data.get("pages", []):
            if "images" in page and isinstance(page["images"], list):
                page["images"] = [img for img in page["images"] if img and img.get("src")]
            _coerce_page_types([page])
            _coerce_components([page])
        _coerce_nav_urls(data.get("navigation_structure"))

    try:
        data = json.loads(raw_json)
        _clean(data)
        return SiteUnderstanding(**data)
    except Exception as e:
        print(f"[WARN] Validation error: {e}")
        try:
            data = json.loads(raw_json)
            _clean(data)
            allowed = {k: v for k, v in data.items() if k in SiteUnderstanding.model_fields}
            return SiteUnderstanding(**allowed)
        except Exception as e2:
            print(f"[WARN] Lenient parse also failed: {e2}")
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


def _try_extract_from_tool_result(result) -> tuple[Optional[dict], Optional[str]]:
    """Try to extract a JSON dict from a ToolResult, returning (data, last_text).

    The returned `last_text` is the body of the last NDJSON `text` event
    (or None) — useful for debug logging on failure.

    Strategy:
      1. Standard extractor over the raw stdout (handles ToolResult wrapper,
         fenced blocks, embedded JSON).
      2. If that fails, re-extract from the last `text` event body alone —
         rescues the case where ToolResult.summary was truncated to the
         first 2000 chars but the actual JSON lives in the final text event.
      3. If still failing and we saw NDJSON events, re-extract from the
         concatenation of all text bodies.

    Returns (None, last_text) when nothing parseable is found. Importantly,
    if extract_json returns a *Kilo NDJSON event* (e.g. {"type": "text",
    "part": {...}}) rather than a real artifact, we reject it and fall
    through to the next strategy — the bare event isn't a SiteUnderstanding.
    """
    stdout = result.summary or ""

    # Walk NDJSON events to capture the last text body.
    last_text: Optional[str] = None
    text_bodies: list[str] = []
    saw_event = False
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        saw_event = True
        if event.get("type") == "text":
            part = event.get("part") or {}
            if isinstance(part, dict):
                t = part.get("text")
                if isinstance(t, str) and t:
                    last_text = t
                    text_bodies.append(t)

    def _is_ndjson_event(d: dict) -> bool:
        """A Kilo NDJSON event wrapper, not a real artifact."""
        return (
            isinstance(d.get("type"), str)
            and d.get("type") in ("text", "tool_use", "step_finish", "init")
            and isinstance(d.get("part"), dict)
        )

    # Strategy 1: standard extractor over the raw stdout.
    try:
        d = extract_json(stdout)
        if not _is_ndjson_event(d):
            return d, last_text
    except JSONExtractionError:
        pass

    # Strategy 2: re-extract from the last text event body alone.
    if last_text and last_text != stdout:
        try:
            d = extract_json(last_text)
            if not _is_ndjson_event(d):
                return d, last_text
        except JSONExtractionError:
            pass

    # Strategy 3: extract from the concatenation of all text bodies.
    if saw_event and text_bodies:
        joined = "\n".join(text_bodies)
        try:
            d = extract_json(joined)
            if not _is_ndjson_event(d):
                return d, last_text
        except JSONExtractionError:
            pass

    return None, last_text


def scrape(url: str) -> Optional[SiteUnderstanding]:
    """
    Main entry point: build prompt -> call kilo run -> parse JSON.

    Kilo CLI handles all agentic logic internally:
    - Loads the persona (embedded in prompt)
    - Binds Playwright + Fetch MCP tools (from kilocode/.mcp.json)
    - Runs ReAct loop: think -> tool -> observe -> repeat
    - Returns text/JSON output

    Reliability behavior:
      - Extracts JSON from the full NDJSON event stream, not just the
        2000-char `summary` cap (which has hidden the JSON artifact in
        past runs).
      - On extraction failure, issues a single tightened-prompt retry
        that asks Kilo to re-emit the JSON without further tool calls.
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
        timeout=900,  # Phase 1.2: real Playwright agent loops need 2-5+ min
        on_timeout=_on_scraper_timeout,
    )

    if not result.success:
        print(f"[ERROR] Kilo invocation failed: {result.errors}")
        if any("not found" in e.lower() for e in result.errors):
            print("[ERROR] 'kilo' command not found. Is Kilo CLI installed and in PATH?")
        return None

    print(f"[KILO] Output received ({(result.summary or '').__len__()} chars)")

    # Try extraction on the first response. If that fails, fall through to
    # a tightened-prompt retry.
    data, _last_text = _try_extract_from_tool_result(result)
    if data is None:
        print("[RETRY] Initial output not parseable; retrying with JSON-only prompt")
        retry_result = invoke_kilo_safe(
            prompt=build_scraper_prompt(url, retry_mode=True),
            context={"url": url, "previous_prompt_chars": len(prompt)},
            working_dir=".",
            persona="scraper_specialist",
            timeout=300,  # retry is JSON-only, no tool calls → fast
            on_timeout=_on_scraper_timeout,
        )
        if retry_result.success:
            data, _last_text = _try_extract_from_tool_result(retry_result)

    if data is None:
        print(f"[ERROR] Could not extract JSON from Kilo output after retry")
        log_gap(
            migration_id="",
            gap_type="gate_failure",
            source_persona="scraper_specialist",
            target_persona="scraper_specialist",
            description="Could not extract SiteUnderstanding JSON from Kilo output (after retry)",
            suggested_fix="Check Kilo output format and prompt instructions",
            severity="high",
        )
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
