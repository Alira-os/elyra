"""
architect.py — Phase 2 Architect Specialist CLI

Usage:
    python architect.py <site_id>       Run architect on a saved SiteUnderstanding
    python architect.py --latest        Run on most recent SiteUnderstanding
    python architect.py --list         List available SiteUnderstandings

Output goes to memory/site_architectures/<id>.json

Architecture:
- Python (thin glue): loads SiteUnderstanding, calls architect_agent, validates output
- Kilo CLI: loads persona, drives LLM reasoning over scraped data
"""

import sys
import json

from skills.agentic.architect_agent import architect, list_site_understandings


def main(site_id: str):
    result = architect(site_id)

    if result is None:
        print("Architecture failed.")
        sys.exit(1)

    print(f"\n[SITEARCHITECTURE]")
    print("-" * 60)
    print(json.dumps(result.model_dump(mode="json"), indent=2))

    return result


def cli():
    args = sys.argv[1:]
    site_id = None

    for arg in args:
        if arg in ("-h", "--help"):
            print("Usage: python architect.py <site_id> [--latest] [--list]")
            print("  <site_id>   Timestamp ID of a SiteUnderstanding (e.g., 20260520_142439)")
            print("  --latest    Run on the most recent SiteUnderstanding")
            print("  --list      List all available SiteUnderstandings")
            return
        elif arg == "--latest":
            site_id = "--latest"
        elif arg == "--list":
            files = list_site_understandings()
            if not files:
                print("No SiteUnderstanding files found in memory/site_understandings/")
            else:
                print("Available SiteUnderstandings:")
                for f in files:
                    print(f"  {f.stem}")
            return
        elif not arg.startswith("--"):
            site_id = arg

    if not site_id:
        print("Error: site_id required (or use --latest or --list)")
        print("Usage: python architect.py <site_id> [--latest] [--list]")
        sys.exit(1)

    main(site_id)


if __name__ == "__main__":
    cli()