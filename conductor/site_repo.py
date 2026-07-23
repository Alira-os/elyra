"""conductor/site_repo.py — Phase D.

Per-site git repo initialization. Called by the orchestrator
immediately after the Handoff Ceremony (before the Forge persona
loop) so each new site is its own git repo on a forge/<migration_id>
branch. This keeps each migration's working tree isolated from the
elyra repo and makes per-site history trivial.

Public surface is intentionally tiny: `ensure_site_repo`. Everything
else (trace events, gap logging, persona dispatch) lives in the
orchestrator. The helper returns a small dict so callers can emit
their own trace events without an import cycle.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def _run_git(args: List[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a git command in `cwd`. Caller handles CalledProcessError."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _git_exists(repo_dir: Path) -> bool:
    return (repo_dir / ".git").exists()


def _has_commits(repo_dir: Path) -> bool:
    try:
        r = _run_git(["rev-parse", "--verify", "HEAD"], repo_dir)
        return r.returncode == 0
    except Exception:
        return False


def _current_branch(repo_dir: Path) -> Optional[str]:
    try:
        r = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_dir)
        branch = (r.stdout or "").strip()
        return branch or None
    except Exception:
        return None


def _init_main(repo_dir: Path) -> None:
    """`git init -b main` with fallback for older git (< 2.28)."""
    try:
        _run_git(["init", "-b", "main"], repo_dir)
    except subprocess.CalledProcessError:
        _run_git(["init"], repo_dir)
        try:
            _run_git(["symbolic-ref", "HEAD", "refs/heads/main"], repo_dir)
        except subprocess.CalledProcessError:
            pass


def _write_site_readme(
    site_dir: Path,
    site_slug: str,
    migration_id: str,
    branch: str,
    extras: Optional[Dict[str, Any]] = None,
) -> None:
    extras = extras or {}
    source_url = extras.get("source_url", "")
    target_stack = extras.get("target_stack", "unknown")
    stitch_project_url = extras.get("stitch_project_url", "")

    readme = f"""# {site_slug} migration

- migration_id: `{migration_id}`
- source_url: {source_url or "(not set)"}
- target_stack: {target_stack}
- forge_branch: `{branch}`
- stitch_project_url: {stitch_project_url or "(pending — set by frontend_architect after first build)"}

This repository was created by Elyra's Forge Room. Each migration runs
on its own `forge/<migration_id>` branch so multiple migrations can
proceed in parallel without stepping on each other.
"""
    (site_dir / "SITE_README.md").write_text(readme, encoding="utf-8")


def ensure_site_repo(
    site_dir: Path,
    site_slug: str,
    migration_id: str,
    site_readme_extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ensure `site_dir` is a git repo on `forge/<migration_id>`.

    Idempotent: re-running with the same migration_id is a no-op (the
    branch already exists, the README is overwritten in place). Re-running
    with a different migration_id switches branches (or creates the
    new one). Never deletes existing work.

    Returns: {"site_dir": str, "branch": str, "init_steps": [str, ...]}
    Raises: subprocess.CalledProcessError if any git command fails —
    the orchestrator catches and logs a medium-severity gap.
    """
    site_dir = Path(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)

    init_steps: List[str] = []

    if not _git_exists(site_dir):
        _init_main(site_dir)
        init_steps.append("git_init")

    if not _has_commits(site_dir):
        # Allow-empty so we have an initial commit even before any
        # files exist.
        try:
            _run_git(["-c", "user.email=elyra@local", "-c", "user.name=Elyra", "commit", "--allow-empty", "-m", f"init: {site_slug}"], site_dir)
            init_steps.append("initial_commit")
        except subprocess.CalledProcessError:
            # If user.name/email aren't configured globally either, fall back
            # to writing the README first then committing for real.
            _write_site_readme(site_dir, site_slug, migration_id, f"forge/{migration_id}", site_readme_extras)
            _run_git(["add", "SITE_README.md"], site_dir)
            _run_git(["-c", "user.email=elyra@local", "-c", "user.name=Elyra", "commit", "-m", f"init: {site_slug}"], site_dir)
            init_steps.append("initial_commit_with_readme")

    branch = f"forge/{migration_id}"
    # `-B` ensures re-running with the same migration_id is a fast-forward
    # no-op rather than failing because the branch already exists.
    _run_git(["checkout", "-B", branch], site_dir)
    init_steps.append("checkout_branch")

    # Always rewrite the README so it reflects the current migration
    # extras (source URL, target_stack, stitch_project_url).
    _write_site_readme(site_dir, site_slug, migration_id, branch, site_readme_extras)
    try:
        _run_git(["add", "SITE_README.md"], site_dir)
        # Only commit if there's actually a diff (re-runs are no-ops).
        diff = _run_git(["diff", "--cached", "--quiet"], site_dir)
        if diff.returncode != 0:
            _run_git(["-c", "user.email=elyra@local", "-c", "user.name=Elyra", "commit", "-m", f"site_readme: {site_slug}"], site_dir)
            init_steps.append("site_readme_commit")
    except subprocess.CalledProcessError:
        # Don't fail the whole init just because the README commit
        # couldn't happen — the branch and dir are already set up.
        pass

    return {
        "site_dir": str(site_dir),
        "branch": branch,
        "init_steps": init_steps,
    }