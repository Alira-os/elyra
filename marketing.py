"""
marketing.py — Phase 1 root CLI for the marketing persona.

Phase 1: no thin-glue ``skills/agentic/marketing_agent.py``. The CLI
calls the configured ``ExecutionBackend`` directly with
``(marketing_specialist persona, prompt, ContentRecommendation)`` and
saves the artifact via ``memory.artifacts``.

Usage:
    python marketing.py <site_id> [<arch_id>]
    python marketing.py --latest
    python marketing.py --list
"""

import sys
import json
from pathlib import Path

from registry.prompts import build_marketing_prompt
from memory.artifacts import (
    SITE_UNDERSTANDINGS_DIR, SITE_ARCHITECTURES_DIR,
    load_site_architecture, load_site_understanding,
)
from tools.execution import get_backend
from models.site_schemas import ContentRecommendation


PERSONA_LONG = "marketing_specialist"
PERSONA_PATH = Path(f"registry/personas/{PERSONA_LONG}.md")


def _read_persona() -> str:
    return PERSONA_PATH.read_text(encoding="utf-8") if PERSONA_PATH.exists() else ""


def list_site_understandings():
    if not SITE_UNDERSTANDINGS_DIR.exists():
        return []
    files = sorted(SITE_UNDERSTANDINGS_DIR.glob("*.json"), reverse=True)
    dirs = sorted(
        [d for d in SITE_UNDERSTANDINGS_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    return files + [d / "site.json" for d in dirs if (d / "site.json").exists()]


def list_architectures():
    if not SITE_ARCHITECTURES_DIR.exists():
        return []
    return sorted(SITE_ARCHITECTURES_DIR.glob("*.json"), reverse=True)


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


def run_marketing(site_id: str, arch_id: str):
    site = load_site_understanding(site_id)
    arch = load_site_architecture(arch_id)
    if site is None or arch is None:
        print("Marketing analysis failed (missing upstream artifacts).")
        return None

    prompt = build_marketing_prompt(site, arch, _read_persona())
    rec = get_backend().invoke(
        persona=PERSONA_PATH,
        prompt=prompt,
        output_model=ContentRecommendation,
    )
    if rec is None:
        print("Marketing analysis failed.")
        return None

    print(f"\n[CONTENTRECOMMENDATION]")
    print("-" * 60)
    print(json.dumps(rec.model_dump(mode="json"), indent=2))
    return rec


def main(site_id: str, arch_id: str):
    result = run_marketing(site_id, arch_id)
    if result is None:
        sys.exit(1)
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