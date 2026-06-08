"""
conductor.orchestrator package entry point.

Usage:
    python -m conductor.orchestrator <url>
    python -m conductor.orchestrator <url> <platform>
"""

import sys
from urllib.parse import urlparse
from datetime import datetime, timezone

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.wixsite.com"
    platform = sys.argv[2] if len(sys.argv) > 2 else "wix"

    from conductor.orchestrator import MigrationManager
    from conductor.routing import Router

    # Detect platform from URL
    router = Router()
    detection = router.detect_platform_from_url(url)
    platform = detection.get("platform", "generic")
    platform_confidence = detection.get("confidence", 0.5)

    # Extract site_name from URL path
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    site_name = path_parts[-1] if path_parts else "unnamed"

    task_context = {
        "url": url,
        "platform": platform,
        "platform_confidence": platform_confidence,
        "site_name": site_name,
        "migration_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "task_type": "portfolio",
    }

    print(f"[ELYRA MANAGER] Starting migration for {url}")
    print(f"[CONFIG] Platform: {platform} (confidence: {platform_confidence:.0%})")
    print(f"[CONFIG] Site name: {site_name}")
    print(f"[CONFIG] Migration ID: {task_context['migration_id']}")

    manager = MigrationManager()
    result = manager.run(task_context)

    print(f"\n[MANAGER] Result: {result['phase_reached']}")
    print(f"[MANAGER] Site slug: {result['site_slug']}")
    print(f"[MANAGER] Success: {result['success']}")
    trace = result.get("trace", [])
    print(f"[MANAGER] Trace events: {[t.get('event') for t in trace]}")
    print(f"[MANAGER] Gaps logged: {len(result.get('gaps', []))}")

if __name__ == "__main__":
    main()