"""
marketing.py — Phase 3 Marketing Specialist CLI

Usage:
    python marketing.py <site_id> [<arch_id>]  Run marketing on a SiteUnderstanding + SiteArchitecture
    python marketing.py --latest                Run on most recent for both
    python marketing.py --list                  List available SiteUnderstandings and Architectures

Output goes to memory/site_recommendations/<id>.json

Architecture:
- Python (thin glue): loads SiteUnderstanding + SiteArchitecture, calls marketing_agent, validates output
- Kilo CLI: loads persona, drives LLM reasoning over content data
"""

import sys
import json

from skills.agentic.marketing_agent import (
    market,
    list_architectures,
)
from skills.agentic.architect_agent import list_site_understandings


def get_latest_ids():
    sites = list_site_understandings()
    archs = list_architectures()
    if not sites:
        print("[ERROR] No SiteUnderstanding files found")
        sys.exit(1)
    site_id = sites[0].stem
    arch_id = archs[0].stem if archs else site_id
    print(f"[LATEST] Using site: {site_id}, architecture: {arch_id}")
    return site_id, arch_id


def main(site_id: str, arch_id: str):
    result = market(site_id, arch_id)

    if result is None:
        print("Marketing analysis failed.")
        sys.exit(1)

    print(f"\n[CONTENTRECOMMENDATION]")
    print("-" * 60)
    print(json.dumps(result.model_dump(mode="json"), indent=2))

    return result


def cli():
    args = sys.argv[1:]
    site_id = None
    arch_id = None

    for arg in args:
        if arg in ("-h", "--help"):
            print("Usage: python marketing.py <site_id> [<arch_id>] [--latest] [--list]")
            print("  <site_id>   Timestamp ID of a SiteUnderstanding (e.g., 20260520_142439)")
            print("  <arch_id>   Timestamp ID of a SiteArchitecture (defaults to <site_id>)")
            print("  --latest    Run on the most recent SiteUnderstanding + SiteArchitecture")
            print("  --list      List all available SiteUnderstandings and Architectures")
            return
        elif arg == "--latest":
            site_id, arch_id = get_latest_ids()
        elif arg == "--list":
            sites = list_site_understandings()
            archs = list_architectures()
            print("Available SiteUnderstandings:")
            for f in sites:
                print(f"  {f.stem}")
            print("\nAvailable SiteArchitectures:")
            if archs:
                for f in archs:
                    print(f"  {f.stem}")
            else:
                print("  (none yet — run architect.py first)")
            return
        elif not arg.startswith("--"):
            site_id = arg

    if not site_id:
        print("Error: site_id required (or use --latest or --list)")
        print("Usage: python marketing.py <site_id> [<arch_id>] [--latest] [--list]")
        sys.exit(1)

    if arch_id is None:
        arch_id = site_id

    main(site_id, arch_id)


if __name__ == "__main__":
    cli()