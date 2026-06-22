#!/usr/bin/env python
"""
Elyra Orchestrator Entry Point

Run a full migration:
    python run_orchestrator.py <url> [platform]

Example:
    python run_orchestrator.py https://merimeesolutions.wixstudio.com/my-site-2
    python run_orchestrator.py https://example.wixsite.com wix

Ad-hoc sandbox cleanup (no migration):
    python run_orchestrator.py --prune-sandboxes [max_age_days]
"""

import argparse
import sys
import time
from urllib.parse import urlparse
from datetime import datetime, timezone


def _handle_prune_only(args) -> int:
    """CLI path: prune stale kilo-elyra sandbox dirs and exit."""
    from tools.kilo_sandbox import prune_sandboxes
    removed = prune_sandboxes(max_age_days=args.prune_sandboxes)
    print(f"[SANDBOX] Pruned {removed} stale sandbox dir(s) older than {args.prune_sandboxes}d")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Elyra orchestrator entry point")
    parser.add_argument("url", nargs="?", default=None,
                        help="URL of the site to migrate (default: example.wixsite.com)")
    parser.add_argument("platform", nargs="?", default=None,
                        help="Optional platform override (wix, squarespace, webflow, generic)")
    parser.add_argument("--prune-sandboxes", nargs="?", type=int, const=7, default=None,
                        help="Prune stale kilo-elyra sandbox dirs older than N days (default 7) "
                             "and exit without running a migration.")
    args = parser.parse_args()

    if args.prune_sandboxes is not None and args.url is None:
        return _handle_prune_only(args)

    url = args.url or "https://example.wixsite.com"
    platform = args.platform

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
        # personas for a fresh site slug. Disabled when an artifact
        # for the current URL already exists, so the rest of the
        # pipeline (architect/marketing/designer/forge) can proceed
        # without re-running an already-successful scraper.
        "force_preflight": False,
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

    # Best-effort prune of stale kilo-elyra sandboxes. Wrapped in
    # try/except so a cleanup failure can never break the migration.
    try:
        from tools.kilo_sandbox import prune_sandboxes
        removed = prune_sandboxes(max_age_days=7)
        if removed:
            print(f"[SANDBOX] Pruned {removed} stale kilo-elyra sandbox(es)")
    except Exception as e:
        print(f"[SANDBOX] Cleanup skipped: {e}")

    return 0 if result["success"] else 1

if __name__ == "__main__":
    sys.exit(main())