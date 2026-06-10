#!/usr/bin/env python
"""
Elyra Orchestrator Entry Point

Run a full migration:
    python run_orchestrator.py <url> [platform]

Example:
    python run_orchestrator.py https://merimeesolutions.wixstudio.com/my-site-2
    python run_orchestrator.py https://example.wixsite.com wix
"""

import sys
import time
from urllib.parse import urlparse
from datetime import datetime, timezone

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.wixsite.com"
    platform = sys.argv[2] if len(sys.argv) > 2 else None

    from conductor.orchestrator import MigrationManager
    from conductor.routing import Router

    # Detect platform from URL if not provided
    router = Router()
    detection = router.detect_platform_from_url(url)
    detected_platform = detection.get("platform", "generic")
    platform_confidence = detection.get("confidence", 0.5)
    platform = platform or detected_platform

    # Extract site_name from URL path
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    site_name = path_parts[-1] if path_parts else "unnamed"

    # Phase 0.8: detect whether this URL has been migrated before. The
    # orchestrator's skip-checks are per-migration (timestamp IDs in
    # flat dirs), so a brand-new URL will find the LATEST artifact
    # which is for some other site. We set `force_preflight=True` to
    # re-run all planning personas from scratch for any new URL.
    from pathlib import Path
    visual_dir = Path("memory/visual_specs") / site_name
    is_fresh_site = not (visual_dir.exists() and any(visual_dir.glob("*.json")))

    task_context = {
        "url": url,
        "platform": platform,
        "platform_confidence": platform_confidence,
        "site_name": site_name,
        "migration_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "task_type": "portfolio",
        # Phase 0.8: force the pre-flight to re-run all planning
        # personas for a fresh site slug (or any time the runner is
        # invoked). This is the safe default — the persona prompt
        # is cheap, and re-running ensures all artifacts are coherent
        # for the new URL.
        "force_preflight": True,
    }

    print(f"[ELYRA] Starting migration for {url}")
    print(f"[CONFIG] Platform: {platform} (confidence: {platform_confidence:.0%})")
    print(f"[CONFIG] Site name: {site_name}")
    print(f"[CONFIG] Migration ID: {task_context['migration_id']}")
    print(f"[CONFIG] Started at: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)

    t0 = time.time()
    manager = MigrationManager()
    result = manager.run(task_context)
    elapsed = time.time() - t0

    print("=" * 60)
    print(f"\n[RESULT] Phase: {result['phase_reached']}")
    print(f"[RESULT] Site slug: {result['site_slug']}")
    print(f"[RESULT] Success: {result['success']}")
    print(f"[RESULT] Elapsed: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    trace = result.get("trace", [])
    print(f"[TRACE] Events ({len(trace)}): {[t.get('event') for t in trace]}")

    gaps = result.get("gaps", [])
    print(f"[GAPS] Logged: {len(gaps)}")

    return 0 if result["success"] else 1

if __name__ == "__main__":
    sys.exit(main())