"""
scrape.py — Phase 1 root CLI for the scraper persona.

Phase 1: no thin-glue ``skills/agentic/scraper_agent.py``. The CLI calls
the configured ``ExecutionBackend`` directly with
``(scraper_specialist persona, prompt, SiteUnderstanding)`` and writes
the recon output to ``memory/site_understandings/<site_id>/``.

Usage:
    python scrape.py <url>

Architecture:
- Python: build the prompt via ``registry.prompts.build_scraper_prompt``,
  invoke ``backend.invoke(...)``, then load the recon directory as a
  ``SiteUnderstanding`` and print it.
- Backend: persona (markdown) + tools (Playwright + Fetch MCP for the
  real Kilo backend; deterministic dummy for ``MockBackend``).
"""

import sys
from datetime import datetime
from pathlib import Path

from registry.prompts import build_scraper_prompt
from memory.artifacts import (
    SITE_UNDERSTANDINGS_DIR, load_site_understanding,
)
from tools.execution import get_backend, BackendInvokeError
from models.site_schemas import SiteUnderstanding, SiteSummary


PERSONA_LONG = "scraper_specialist"
PERSONA_PATH = Path(f"registry/personas/{PERSONA_LONG}.md")


def _read_persona() -> str:
    return PERSONA_PATH.read_text(encoding="utf-8") if PERSONA_PATH.exists() else ""


def main(url: str) -> str | None:
    site_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    SITE_UNDERSTANDINGS_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = SITE_UNDERSTANDINGS_DIR / site_id
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt = build_scraper_prompt(url, site_id, _read_persona())
    # The scraper is side-effect driven — the agent writes files to
    # ``out_dir`` during its loop. We don't trust the backend's return
    # value for the actual artifact; we re-load from disk.
    try:
        get_backend().invoke(
            persona=PERSONA_PATH,
            prompt=prompt,
            output_model=SiteUnderstanding,
        )
    except BackendInvokeError:
        pass  # scraper frequently fails structured validation; we still try disk.

    site = load_site_understanding(site_id)
    if site is None:
        print("Scraping failed.")
        return None

    summary_path = out_dir / "site.json"
    summary = SiteSummary.model_validate_json(
        summary_path.read_text(encoding="utf-8")
    ) if summary_path.exists() else None
    print(f"\n[SITEUNDERSTANDING]")
    print("-" * 60)
    print(summary.model_dump_json(indent=2) if summary is not None else site.model_dump_json(indent=2))
    print(f"\n[SAVED] memory/site_understandings/{site_id}/")
    return site_id


def cli():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: python scrape.py <url>")
        return
    url = args[0]
    main(url)


if __name__ == "__main__":
    cli()