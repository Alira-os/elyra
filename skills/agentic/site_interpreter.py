"""
site_interpreter — Phase 1 Agentic Scraper (Kilo Code)

Thin glue that wires:
- scraper_specialist persona (markdown charter)
- Raw MCP artifacts (Playwright + Fetch)
- Kilo Code LLM reasoning
- Pydantic validation
- JSON output / memory persistence

Python is ONLY glue. All intelligence lives in the LLM guided by the persona.
No imperative parsing, no DOM manipulation — only MCP orchestration + validation.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

from models.site_schemas import SiteUnderstanding, PageStructure


PERSONA_PATH = "registry/personas/scraper_specialist.md"
OUTPUT_DIR = Path("memory/site_understandings")


def load_persona() -> str:
    """Load the scraper specialist persona charter."""
    with open(PERSONA_PATH, "r", encoding="utf-8") as f:
        return f.read()


def extract_json(text: str) -> Optional[str]:
    """
    Extract first complete JSON object from text.
    Uses brace counting to find matching { ... } pair.
    """
    start = text.find('{')
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None


def build_interpreter_prompt(raw_artifacts: Dict[str, Any], url: str) -> str:
    """
    Build the prompt sent to Kilo Code LLM.

    Structure:
    - Persona charter (scraper_specialist.md)
    - Raw MCP artifacts (Playwright snapshot, Fetch content)
    - Schema instruction (must return valid SiteUnderstanding JSON)
    - URL being scraped
    """
    persona = load_persona()

    pages_summary = []
    for i, page in enumerate(raw_artifacts.get("pages", [])):
        snapshot_text = page.get("snapshot", {}).get("snapshot", "")
        nav_result = page.get("navigation_result", {})
        fetch_result = page.get("fetch_result", {})

        pages_summary.append({
            "index": i + 1,
            "url": page.get("url"),
            "nav_success": nav_result.get("success", False),
            "snapshot_preview": snapshot_text[:1000] if snapshot_text else "",
            "fetch_status": fetch_result.get("success", False) if fetch_result else False
        })

    artifacts_json = json.dumps({
        "url": raw_artifacts.get("url"),
        "total_pages": len(raw_artifacts.get("pages", [])),
        "pages": pages_summary
    }, indent=2, default=str)

    full_artifacts = json.dumps(raw_artifacts, indent=2, default=str)

    return f"""{persona}

---

## Target URL
{url}

---

## MCP Artifacts Collected
{artifacts_json}

---

## Full Raw Artifacts (for detailed analysis)
```json
{full_artifacts}
```

---

## Your Task
Given the above artifacts and your analysis of the target URL, produce a complete SiteUnderstanding.

Output ONLY valid JSON — no commentary, no markdown code blocks, no explanatory text.
The JSON must exactly match the SiteUnderstanding schema.
```json
{{
  "url": "...",
  "platform": "wix|squarespace|wordpress|shopify|generic|unknown",
  "platform_confidence": 0.0-1.0,
  "site_name": "...",
  "total_pages_discovered": N,
  "pages": [ /* array of PageStructure objects */ ],
  "global_assets": {{ ... }},
  "contact_info": {{ ... }},
  "navigation_structure": [ ... ],
  "estimated_fidelity": 0.0-1.0,
  "warnings": [ ... ],
  "recommendations": [ ... ],
  "reasoning_trace": [ ... ]
}}
```
"""


def invoke_kilo_llm(prompt: str, timeout: int = 180) -> Optional[str]:
    """
    Invoke Kilo Code LLM with the interpreter prompt.

    Uses tools/kilo.py invoke_kilo pattern.
    Returns raw JSON string from Kilo response, or None on failure.
    """
    try:
        from tools.kilo import invoke_kilo

        result = invoke_kilo(
            prompt=prompt,
            context={"mode": "site_interpreter", "task": "scrape_and_analyze"},
            working_dir=".",
            timeout=timeout
        )

        if result.success and result.summary:
            text = result.summary
            json_str = extract_json(text)
            if json_str:
                return json_str
            return text if text else None
        elif result.errors:
            print(f"Kilo errors: {result.errors}")
        return None
    except Exception as e:
        print(f"Kilo invocation failed: {e}")
        return None


def parse_and_validate(raw_json: str) -> Optional[SiteUnderstanding]:
    """
    Parse raw JSON string into SiteUnderstanding Pydantic model.
    Returns None if validation fails, with recovery attempt.
    """
    try:
        data = json.loads(raw_json)
        return SiteUnderstanding(**data)
    except Exception as e:
        print(f"Validation failed: {e}")
        try:
            data = json.loads(raw_json)
            allowed = {k: v for k, v in data.items() if k in SiteUnderstanding.model_fields}
            return SiteUnderstanding(**allowed)
        except Exception:
            return None


def save_site_understanding(site_understanding: SiteUnderstanding, output_id: Optional[str] = None) -> Path:
    """
    Save SiteUnderstanding to JSON file in memory directory.
    Returns the path to the saved file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not output_id:
        output_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = f"{output_id}.json"
    filepath = OUTPUT_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(site_understanding.model_dump_json(indent=2))

    return filepath


def load_site_understanding(filepath: Path) -> Optional[SiteUnderstanding]:
    """Load a saved SiteUnderstanding from JSON file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SiteUnderstanding(**data)
    except Exception:
        return None


def interpret_site(raw_artifacts: Dict[str, Any], url: str, save: bool = True) -> SiteUnderstanding:
    """
    Main site_interpreter entry point.

    Flow:
    1. Build interpreter prompt (persona + artifacts + schema)
    2. Invoke Kilo LLM (single-shot, with fallback)
    3. Parse + validate response
    4. Optionally save to memory

    Python is thin glue here — no parsing, no reasoning.
    """
    prompt = build_interpreter_prompt(raw_artifacts, url)

    raw_response = invoke_kilo_llm(prompt)

    if raw_response:
        site = parse_and_validate(raw_response)
        if site:
            if save:
                output_path = save_site_understanding(site)
                print(f"  💾 Saved to: {output_path}")
            return site

    fallback_pages = [
        PageStructure(
            url=url,
            title="Home (stub)",
            page_type=["home"],
            notes=["Stub mode - Kilo LLM not available or returned invalid output"]
        )
    ]

    fallback = SiteUnderstanding(
        url=url,
        platform="generic",
        platform_confidence=0.5,
        site_name="Stub Site",
        total_pages_discovered=len(raw_artifacts.get("pages", [])),
        pages=fallback_pages,
        estimated_fidelity=0.3,
        warnings=["Stub mode - Kilo LLM not wired or returned invalid output"]
    )

    if save:
        output_path = save_site_understanding(fallback)
        print(f"  💾 Fallback saved to: {output_path}")

    return fallback


if __name__ == "__main__":
    sample_artifacts = {
        "url": "https://example.com",
        "pages": [
            {
                "url": "https://example.com",
                "navigation_result": {"success": True},
                "snapshot": {"success": True, "snapshot": "..."},
                "fetch_result": {"success": True}
            }
        ]
    }
    result = interpret_site(sample_artifacts, "https://example.com")
    print(result.model_dump_json(indent=2))