"""
Elyra — AI-powered site migration, refinement, and optimization.

Thin CLI entrypoint. The greeting is the only logic; everything else is
delegated to :class:`conductor.orchestrator.MigrationManager`.

Usage (interactive):
    python -m elyra

Usage (one-shot):
    python -m elyra <url> [migrate|edit|refine|optimize]

Usage (installed console script):
    elyra <url> [migrate|edit|refine|optimize]

Environment variables:
    ELYRA_BACKEND=kilo|mock   Selects the execution backend. Default: kilo.

Per ``AGENTS.md``, this module is the single new root-level CLI. It is
intentionally thin — no orchestration logic lives here. The Manager remains
the single source of truth for routing decisions.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Tuple

# Ensure repo root is on sys.path when invoked as ``python -m elyra`` from
# a checkout (so ``conductor``, ``tools``, ``registry``, ``models`` etc.
# resolve correctly). This is a no-op when the package is installed.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from conductor.orchestrator import MigrationManager  # noqa: E402
from tools.execution import get_backend  # noqa: E402


DYNAMIC_GREETING = (
    "Hello! I'm Elyra — your AI site engineer.\n"
    "What would you like to work on today?\n"
    "  - migrate   reconstruct a site on a modern stack\n"
    "  - edit      refine an existing site\n"
    "  - refine    improve visual/UX/content quality\n"
    "  - optimize  boost SEO, GEO, performance, accessibility\n\n"
    "URL: "
)

HELP_TEXT = (
    "Usage:\n"
    "    python -m elyra <url> [migrate|edit|refine|optimize]\n"
    "    python -m elyra                       # interactive greeting\n"
    "    python -m elyra --help\n"
    "\n"
    "Tasks:\n"
    "    migrate   reconstruct a site on a modern stack\n"
    "    edit      refine an existing site\n"
    "    refine    improve visual/UX/content quality\n"
    "    optimize  boost SEO, GEO, performance, accessibility\n"
    "\n"
    "Environment:\n"
    "    ELYRA_BACKEND  kilo (default) | mock\n"
)

TASK_CHOICES = ("migrate", "edit", "refine", "optimize")


def parse_args(argv: list[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(url, task)`` — either may be ``None`` if not supplied.

    Handles ``--help`` / ``-h`` by printing :data:`HELP_TEXT` and exiting 0.
    """
    # Skip argv[0] (program name).
    args = list(argv[1:])

    if args and args[0] in ("--help", "-h"):
        print(HELP_TEXT)
        sys.exit(0)

    url = args[0] if len(args) > 0 else None
    task = args[1] if len(args) > 1 else None

    if task is not None and task not in TASK_CHOICES:
        print(f"Unknown task '{task}'. Choose from: {', '.join(TASK_CHOICES)}")
        sys.exit(2)

    return url, task


def prompt_for_missing(url: Optional[str], task: Optional[str]) -> Tuple[str, str]:
    """Interactive prompt for any missing fields. Prints the greeting first
    if the task wasn't supplied on the command line.
    """
    if not task:
        print(DYNAMIC_GREETING, end="")
    url = url or input("URL: ").strip()
    task = task or input("Task (migrate/edit/refine/optimize): ").strip().lower()
    if task not in TASK_CHOICES:
        print(f"Unknown task '{task}'. Choose from: {', '.join(TASK_CHOICES)}")
        sys.exit(2)
    return url, task


def build_context(url: str, task: str) -> dict:
    """Compose the ``task_context`` dict that :meth:`MigrationManager.run`
    expects from CLI arguments.

    The Manager re-derives a lot of this from the URL itself; we only set
    the fields the CLI genuinely owns (task type, migration id, site slug
    derived from the URL path).
    """
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    slug = (path_parts[-1] if path_parts else parsed.netloc or "unnamed").lower()

    return {
        "url": url,
        "platform": "generic",  # Manager / Router re-detects via the URL.
        "task_type": task,
        "site_name": slug,
        "migration_id": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
    }


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point. Returns a process exit code (0 = success)."""
    if argv is None:
        argv = sys.argv
    args_url, args_task = parse_args(argv)

    if not args_url or not args_task:
        args_url, args_task = prompt_for_missing(args_url, args_task)

    print(f"\n[Elyra] {args_task} -> {args_url}\n")

    backend = get_backend()
    manager = MigrationManager(backend=backend)
    ctx = build_context(args_url, args_task)
    result = manager.run(ctx)

    # Summary — kept terse and stable so downstream tooling can grep it.
    print(f"\n[Elyra] phase_reached : {result.get('phase_reached')}")
    print(f"[Elyra] site_slug     : {result.get('site_slug')}")
    print(f"[Elyra] success       : {result.get('success')}")
    return 0 if result.get("success") else 1


__all__ = [
    "DYNAMIC_GREETING",
    "HELP_TEXT",
    "TASK_CHOICES",
    "build_context",
    "main",
    "parse_args",
    "prompt_for_missing",
]
