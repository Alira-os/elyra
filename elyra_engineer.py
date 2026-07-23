"""
elyra_engineer.py — Phase-A thin debug CLI for the Elyra Engineer persona.

Mirrors the shape of architect.py: a 50-line wrapper that delegates to the
real implementation in skills/agentic/elyra_engineer.py.

Usage:
    python elyra_engineer.py <migration_id>
    python elyra_engineer.py --latest
    python elyra_engineer.py --list
"""

import sys
import json

from skills.agentic.elyra_engineer import analyze, list_migration_ids


def main(migration_id: str) -> int:
    report = analyze(migration_id)
    if report is None:
        print("Analysis failed.")
        return 1
    print("\n[ELYRA_ENGINEER_REPORT]")
    print("-" * 60)
    print(json.dumps(report, indent=2)[:2000])
    return 0


def cli() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return

    if args[0] == "--list":
        ids = list_migration_ids()
        if not ids:
            print("No migration IDs found in gap ledger.")
        else:
            print("Available migration IDs:")
            for mid in ids:
                print(f"  {mid}")
        return

    if args[0] == "--latest":
        ids = list_migration_ids()
        if not ids:
            print("No migration IDs available.")
            sys.exit(1)
        sys.exit(main(ids[-1]))

    sys.exit(main(args[0]))


if __name__ == "__main__":
    cli()
