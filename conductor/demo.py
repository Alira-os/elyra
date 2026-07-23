#!/usr/bin/env python3
"""
Elyra Migration Demo (Phase A — Manager-based)

Runs the MigrationManager on a hardcoded test URL to verify end-to-end
functionality.

Usage:
    python conductor/demo.py [url]

Example:
    python conductor/demo.py https://example.wixsite.com

The legacy `Conductor` class was removed in Phase A; the demo now
goes through MigrationManager, which is the live Room-based pipeline.
"""

import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conductor.orchestrator import MigrationManager


def run_demo(url: str = "https://example.wixsite.com"):
    print("=" * 60)
    print("ELYRA MANAGER DEMO")
    print("=" * 60)
    print(f"\nTarget URL: {url}\n")

    manager = MigrationManager()

    task_context = {
        "url": url,
        "platform": "wix",
        "task_type": "portfolio",
        "stack_preference": "modernize",
        "must_haves": ["home", "about", "portfolio", "contact"],
    }

    print("Starting migration...\n")
    result = manager.run(task_context)

    print(f"\n--- Migration Result ---")
    print(f"Success: {result.get('success')}")
    print(f"Phase Reached: {result.get('phase_reached')}")
    print(f"Site slug: {result.get('site_slug')}")
    gaps = result.get("gaps", [])
    print(f"Gaps logged: {len(gaps)}")

    return result


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.wixsite.com"
    run_demo(url)
