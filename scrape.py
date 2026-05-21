"""
scrape.py — Phase 1 Agentic Scraper CLI

Usage:
    python scrape.py <url>
    python scrape.py <url> --no-save

Output goes to memory/site_understandings/<id>.json

Architecture:
- Python (thin glue): builds prompt, calls kilo run, validates output
- Kilo CLI: loads persona, executes MCP tools, drives LLM reasoning
"""

import sys
import json

from skills.agentic.scraper_agent import scrape
from skills.agentic.site_interpreter import save_site_understanding


def main(url: str, no_save: bool = False):
    result = scrape(url)

    if result is None:
        print("Scraping failed.")
        sys.exit(1)

    print(f"\n[SITEUNDERSTANDING]")
    print("-" * 60)
    print(json.dumps(result.model_dump(mode="json"), indent=2))

    if not no_save:
        output_path = save_site_understanding(result)
        print(f"\n[SAVED] {output_path}")

    return result


def cli():
    args = sys.argv[1:]
    url = None
    no_save = False

    for i, arg in enumerate(args):
        if arg in ("-h", "--help"):
            print("Usage: python scrape.py <url> [--no-save]")
            return
        elif arg == "--no-save":
            no_save = True
        elif not arg.startswith("--"):
            url = arg

    if not url:
        print("Error: URL required")
        print("Usage: python scrape.py <url> [--no-save]")
        sys.exit(1)

    main(url, no_save)


if __name__ == "__main__":
    cli()