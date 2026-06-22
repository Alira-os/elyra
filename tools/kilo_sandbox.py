"""
Per-migration Kilo data sandbox.

Kilo's CLI resolves its SQLite DB and log directory via the XDG Base Directory
spec — specifically ``XDG_DATA_HOME``. Pointing that env var at a per-migration
directory keeps Elyra-spawned Kilo sessions out of the user's normal
``~/.local/share/kilo/kilo.db`` (and therefore out of their TUI session list),
while leaving the rest of the user's Kilo state untouched.

Empirical contract (verified against kilo.exe v0.x on Windows 11, see
``.kilo/plans/isolate-kilo-sessions-from-elyra-workspace.md`` for the test log):

  - ``XDG_DATA_HOME`` redirects **both data and log** paths on Windows.
  - It does NOT touch ``config`` — MCP servers, permissions, providers, etc.
    continue to read from ``%USERPROFILE%\\.config\\kilo`` as normal.
  - Kilo appends ``\\kilo`` to the data home, so to land the sandbox at
    ``<LOCALAPPDATA>\\kilo-elyra\\<session_id>\\kilo\\kilo.db`` we set
    ``XDG_DATA_HOME=<LOCALAPPDATA>\\kilo-elyra\\<session_id>\\kilo``.
  - ``auth.json`` lives at the root of the data dir (not under ``kilo/``), so
    the sandbox must copy it from the real data dir or Kilo will refuse model
    calls. ``auth.json`` is ~1.1 KB and rarely rotates, so we cache the copy.
  - Other XDG vars (``XDG_CONFIG_HOME``, ``XDG_CACHE_HOME``, ``XDG_STATE_HOME``)
    must NOT be set — the first would break MCP server discovery, and the
    latter two are unnecessary noise.

Containerization (Docker / WSL2) was considered and rejected — see the plan.
"""

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional


SANDBOX_BASE_NAME = "kilo-elyra"
NO_SANDBOX_ENV_VAR = "ELYRA_KILO_NO_SANDBOX"
DEFAULT_MAX_AGE_DAYS = 7


def _real_data_dir() -> Path:
    """Return the user's real Kilo data dir (where kilo.db and auth.json live).

    Verified against ``kilo debug paths`` on Windows 11 (kilo.exe v0.x):

      - With ``XDG_DATA_HOME`` unset: ``data: %USERPROFILE%\\.local\\share\\kilo``
        (kilo uses the XDG default ``$HOME/.local/share`` even on Windows).
      - With ``XDG_DATA_HOME=<x>`` set: ``data: <x>\\kilo`` — kilo appends
        ``\\kilo`` to the data home.

    So this helper computes the **actual** on-disk data dir, which is what
    contains ``kilo.db`` and ``auth.json``.
    """
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "kilo"
    # XDG default is $HOME/.local/share on all platforms; kilo honours that
    # even on Windows (it does NOT fall back to %LOCALAPPDATA% for data).
    return Path.home() / ".local" / "share" / "kilo"


def _real_auth_file() -> Path:
    return _real_data_dir() / "auth.json"


def sandbox_root_for(session_id: str) -> Path:
    """Compute (but do not create) the sandbox root for a given session id.

    Layout::

        <LOCALAPPDATA>\\kilo-elyra\\<session_id>\\kilo\\kilo.db
        <LOCALAPPDATA>\\kilo-elyra\\<session_id>\\kilo\\auth.json
    """
    local_app = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local_app) / SANDBOX_BASE_NAME / session_id


def _ensure_auth_copied(sandbox_root: Path) -> None:
    """Copy ``auth.json`` from the real data dir into the sandbox if needed.

    Idempotent: only copies when the sandbox copy is missing OR the source is
    newer than the destination (rare, but handles the case where the user
    rotated their Kilo credentials mid-run).
    """
    sandbox_auth = sandbox_root / "auth.json"
    real_auth = _real_auth_file()

    if not real_auth.exists():
        # No real auth file — nothing to copy. Kilo will surface a
        # "not authenticated" error when the persona tries to call a model,
        # which is the correct behaviour.
        return

    needs_copy = True
    if sandbox_auth.exists():
        try:
            if sandbox_auth.stat().st_mtime >= real_auth.stat().st_mtime:
                needs_copy = False
        except OSError:
            needs_copy = True

    if needs_copy:
        try:
            sandbox_auth.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(real_auth, sandbox_auth)
        except OSError as e:
            # Best-effort — never raise from here. The Kilo subprocess will
            # surface the real error if it actually needs auth.
            print(f"[SANDBOX] WARN could not copy auth.json into sandbox: {e}")


def make_sandbox_env(session_id: str) -> tuple[dict[str, str], Optional[Path]]:
    """Build a subprocess env that redirects Kilo's data dir into a sandbox.

    Args:
        session_id: A stable identifier for the migration. All persona calls
            within a single Elyra run should pass the same id so they share
            one sandbox dir.

    Returns:
        ``(env, sandbox_root)`` where ``env`` is a copy of the parent env with
        ``XDG_DATA_HOME`` overridden, and ``sandbox_root`` is the directory the
        env points at (or ``None`` if sandboxing is disabled — see below).

    Escape hatch: if ``ELYRA_KILO_NO_SANDBOX=1`` is set in the parent env,
    returns ``(os.environ.copy(), None)`` and the caller should skip the
    ``env=`` argument to ``subprocess.run``. This reproduces today's behaviour
    (sessions land in the user's normal DB) and is useful for reproducing
    user-reported bugs against the real Kilo state.
    """
    if os.environ.get(NO_SANDBOX_ENV_VAR) == "1":
        return os.environ.copy(), None

    root = sandbox_root_for(session_id)
    kilo_subdir = root / "kilo"
    kilo_subdir.mkdir(parents=True, exist_ok=True)

    # Auth lives at the root of the data dir (one level up from where kilo.db
    # lands), matching the production layout.
    _ensure_auth_copied(root)

    env = os.environ.copy()
    # No trailing backslash — Kilo appends "\\kilo" itself (verified). Use
    # str() to coerce Path → str; do NOT add a separator.
    env["XDG_DATA_HOME"] = str(root)
    return env, root


def prune_sandboxes(max_age_days: int = DEFAULT_MAX_AGE_DAYS, base: Optional[Path] = None) -> int:
    """Remove sandbox dirs older than ``max_age_days``.

    Walks ``<LOCALAPPDATA>\\kilo-elyra\\`` and removes immediate children whose
    ``st_mtime`` is older than the threshold. Returns the count removed.

    Best-effort: never raises. A failure removing one dir is logged and
    skipped so a partial prune does not abort the caller's cleanup logic.
    """
    if base is None:
        local_app = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        base = Path(local_app) / SANDBOX_BASE_NAME

    if not base.exists():
        return 0

    cutoff = time.time() - (max_age_days * 86400)
    removed = 0
    try:
        children = list(base.iterdir())
    except OSError as e:
        print(f"[SANDBOX] WARN could not list {base}: {e}")
        return 0

    for child in children:
        try:
            if not child.is_dir():
                continue
            if child.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(child, ignore_errors=True)
            if child.exists():
                # shutil.rmtree with ignore_errors=True may have left some
                # read-only files. Best-effort — if it's still there we move
                # on rather than blocking the whole prune pass.
                print(f"[SANDBOX] WARN could not fully remove {child}")
                continue
            removed += 1
        except Exception as e:
            print(f"[SANDBOX] WARN skipping {child}: {e}")

    return removed


if __name__ == "__main__":
    # CLI for ad-hoc pruning: ``python -m tools.kilo_sandbox --prune [days]``
    import argparse
    parser = argparse.ArgumentParser(description="Kilo sandbox helpers")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("prune", help="Remove stale kilo-elyra sandbox dirs")
    p.add_argument("days", nargs="?", type=int, default=DEFAULT_MAX_AGE_DAYS,
                   help=f"Max age in days (default {DEFAULT_MAX_AGE_DAYS})")
    args = parser.parse_args()
    if args.cmd == "prune":
        removed = prune_sandboxes(max_age_days=args.days)
        print(f"[SANDBOX] Pruned {removed} stale sandbox dir(s) older than {args.days}d")
    else:
        parser.print_help()
