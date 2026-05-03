#!/usr/bin/env python3
"""
Elyra Phase 0 MVP Demo Script

Runs the Conductor on a hardcoded test URL to verify end-to-end functionality.

Usage:
    python conductor/demo.py [url]

Example:
    python conductor/demo.py https://example.wixsite.com
"""

import sys
import json
from conductor.orchestrator import Conductor
from conductor.trace import Trace


def run_demo(url: str = "https://example.wixsite.com"):
    print("=" * 60)
    print("ELYRA PHASE 0 MVP DEMO")
    print("=" * 60)
    print(f"\nTarget URL: {url}\n")

    conductor = Conductor()

    task_context = {
        "url": url,
        "platform": "wix",
        "task_type": "portfolio",
        "stack_preference": "modernize",
        "must_haves": ["home", "about", "portfolio", "contact"]
    }

    print("Starting migration...\n")
    result = conductor.run(task_context)

    print(result.trace.summary())

    print("\n--- Migration Result ---")
    print(f"Success: {result.success}")
    print(f"Phase Reached: {result.phase_reached}")
    print(f"Stack Chosen: {result.stack_chosen}")
    print(f"Routing: {' -> '.join(result.routing_sequence)}")
    if result.deploy_url:
        print(f"Staging URL: {result.deploy_url}")
    print(f"Errors: {len(result.errors)}")

    if result.errors:
        print("\nErrors:")
        for err in result.errors:
            print(f"  - [{err.get('step', 'unknown')}] {err.get('error', 'Unknown error')}")

    return result


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.wixsite.com"
    run_demo(url)