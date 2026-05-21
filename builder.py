"""
builder.py — Phase 3/4 Builder Specialist CLI

Usage:
    python builder.py <site_id> [<arch_id> [<rec_id>]]
    python builder.py --latest       Run on most recent artifacts
    python builder.py --list         List available artifacts

Architecture:
- Python (thin glue): loads three artifacts, calls builder_agent, validates output
- Kilo CLI: loads persona, drives LLM reasoning + code generation
"""

import sys
import json

from skills.agentic.builder_agent import (
    build,
    list_site_understandings,
    list_architectures,
    list_recommendations,
)


def main(site_id: str, arch_id: str, rec_id: str):
    result = build(site_id, arch_id, rec_id)

    if result is None:
        print("Build failed.")
        sys.exit(1)

    print(f"\n[BUILDMANIFEST]")
    print("-" * 60)
    print(json.dumps(result.model_dump(mode="json"), indent=2))

    return result


def cli():
    args = sys.argv[1:]
    site_id = None
    arch_id = None
    rec_id = None

    for arg in args:
        if arg in ("-h", "--help"):
            print("Usage: python builder.py <site_id> [<arch_id> [<rec_id>]] [--latest] [--list]")
            print("  <site_id>   Timestamp ID of SiteUnderstanding")
            print("  <arch_id>   Timestamp ID of SiteArchitecture (defaults to <site_id>)")
            print("  <rec_id>    Timestamp ID of ContentRecommendation (defaults to <site_id>)")
            print("  --latest    Run on most recent artifacts")
            print("  --list      List all available artifacts")
            return
        elif arg == "--latest":
            sites = list_site_understandings()
            archs = list_architectures()
            recs = list_recommendations()
            if not sites:
                print("[ERROR] No artifacts found")
                sys.exit(1)
            site_id = sites[0].stem
            arch_id = archs[0].stem if archs else site_id
            rec_id = recs[0].stem if recs else site_id
            print(f"[LATEST] site: {site_id}, arch: {arch_id}, rec: {rec_id}")
        elif arg == "--list":
            sites = list_site_understandings()
            archs = list_architectures()
            recs = list_recommendations()
            print("Available SiteUnderstandings:")
            for f in sites:
                print(f"  {f.stem}")
            print("\nAvailable SiteArchitectures:")
            for f in archs:
                print(f"  {f.stem}")
            print("\nAvailable ContentRecommendations:")
            for f in recs:
                print(f"  {f.stem}")
            return
        elif not arg.startswith("--"):
            site_id = arg

    if not site_id:
        print("Error: site_id required (or use --latest or --list)")
        print("Usage: python builder.py <site_id> [<arch_id> [<rec_id>]] [--latest] [--list]")
        sys.exit(1)

    if arch_id is None:
        arch_id = site_id
    if rec_id is None:
        rec_id = site_id

    main(site_id, arch_id, rec_id)


if __name__ == "__main__":
    cli()