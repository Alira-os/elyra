"""
architect.py — Phase 1 root CLI for the architect persona.

Phase 1: no thin-glue ``skills/agentic/architect_agent.py``. The CLI
calls the configured ``ExecutionBackend`` directly with
``(architect_specialist persona, prompt, SiteArchitecture)`` and saves
the artifact via ``memory.artifacts``.

Usage:
    python architect.py <site_id>       Run architect on a saved SiteUnderstanding
    python architect.py --latest        Run on most recent SiteUnderstanding
    python architect.py --list          List available SiteUnderstandings
"""

import sys
import json
from pathlib import Path

from registry.prompts import build_architect_prompt
from memory.artifacts import (
    SITE_UNDERSTANDINGS_DIR, load_site_understanding,
)
from tools.execution import get_backend
from models.site_schemas import SiteArchitecture


PERSONA_LONG = "architect_specialist"
PERSONA_PATH = Path(f"registry/personas/{PERSONA_LONG}.md")


def _read_persona() -> str:
    return PERSONA_PATH.read_text(encoding="utf-8") if PERSONA_PATH.exists() else ""


def list_site_understandings():
    """List saved SiteUnderstanding IDs (used by --list)."""
    if not SITE_UNDERSTANDINGS_DIR.exists():
        return []
    # Include both legacy single-file layout and new recon-directory layout.
    files = sorted(SITE_UNDERSTANDINGS_DIR.glob("*.json"), reverse=True)
    dirs = sorted(
        [d for d in SITE_UNDERSTANDINGS_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    return files + [d / "site.json" for d in dirs if (d / "site.json").exists()]


def run_architect(site_id: str):
    site = load_site_understanding(site_id)
    if site is None:
        print(f"Could not load SiteUnderstanding for: {site_id}")
        return None

    prompt = build_architect_prompt(site, _read_persona())
    arch = get_backend().invoke(
        persona=PERSONA_PATH,
        prompt=prompt,
        output_model=SiteArchitecture,
    )
    if arch is None:
        print("Architecture failed.")
        return None

    print(f"\n[SITEARCHITECTURE]")
    print("-" * 60)
    print(json.dumps(arch.model_dump(mode="json"), indent=2))
    return arch


def main(site_id: str):
    result = run_architect(site_id)
    if result is None:
        sys.exit(1)
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
            files = list_site_understandings()
            if not files:
                print("No SiteUnderstanding files found in memory/site_understandings/")
                return
            site_id = files[0].stem
            print(f"[ARCHITECT] Using latest: {files[0].name}")
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