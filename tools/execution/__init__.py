"""
ExecutionBackend — pluggable subprocess LLM invocation + structured output.

This is the Phase 0 abstraction layer described in ``PLAN.md``. It defines:

  - :class:`ExecutionBackend` — a ``Protocol`` that any backend (Kilo, Mock,
    future Codex/Claude Code/Copilot) must conform to.
  - :func:`get_backend` — a cached factory that picks the configured backend
    from the ``ELYRA_BACKEND`` env var or ``kilo.json``, defaulting to
    ``KiloBackend``.
  - Re-exports of ``ToolResult`` and ``KiloBackend`` for callers that want
    ``from tools.execution import ToolResult`` style imports.

Per ``AGENTS.md``, an "agent" is now defined by the triple
``(persona.md charter) + (Pydantic output model) + (backend.invoke(...))``.
There are no thin ``*_agent.py`` files in Phase 1; the Manager (and direct
CLI entrypoints) call ``backend.invoke`` directly. This module is the seam
that makes that possible.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Type, runtime_checkable

from pydantic import BaseModel

# Re-export from the concrete backends so callers can do
# `from tools.execution import ToolResult, KiloBackend`.
from tools.execution.backend_kilo import (  # noqa: E402, F401
    BackendInvokeError,
    KiloBackend,
    ToolResult,
    invoke_kilo,
    invoke_kilo_safe,
    invoke_kilo_simple,
    resolve_persona,
)


@runtime_checkable
class ExecutionBackend(Protocol):
    """Pluggable LLM execution backend.

    The contract: given a persona (charter or path), a task prompt, and a
    Pydantic output model, return a validated instance of that model.

    Implementations may invoke a subprocess LLM (:class:`KiloBackend`), make
    an HTTP call to a hosted API (future Codex/Claude Code/Copilot
    backends), or return canned test fixtures (:class:`MockBackend`).
    """

    def invoke(
        self,
        persona: "str | Path",
        prompt: str,
        output_model: "Type[BaseModel]",
    ) -> BaseModel:
        """Invoke the backend with a persona, task prompt, and output schema.

        Args:
            persona: Either a string persona charter (already-loaded text)
                or a Path to a ``.md`` file in ``registry/personas/``. If a
                Path, the backend reads it and prepends its content to the
                prompt before invoking the LLM.
            prompt: The task instruction given to the LLM.
            output_model: The Pydantic class the backend should validate
                its output against.

        Returns:
            A validated instance of ``output_model``.

        Raises:
            Exception: Backend-specific failure (subprocess crash, missing
                JSON, schema mismatch, etc.). Implementations should raise
                an exception that carries enough context for the caller to
                log a useful gap; :class:`BackendInvokeError` from
                ``backend_kilo`` is the canonical shape.
        """
        ...


# ---------------------------------------------------------------------------
# get_backend — cached factory driven by env var / kilo.json.
# ---------------------------------------------------------------------------

_BACKEND_CACHE: Dict[str, ExecutionBackend] = {}

# Known backend names — extend when adding new implementations.
_KNOWN_BACKENDS = ("kilo", "mock")

# The env var that overrides everything else.
ENV_VAR = "ELYRA_BACKEND"


def get_backend(name: Optional[str] = None) -> ExecutionBackend:
    """Return the configured execution backend (cached singleton).

    Resolution order for the backend ``name``:

      1. ``name`` argument (highest priority — bypasses cache key by name).
      2. ``ELYRA_BACKEND`` environment variable (e.g. ``"kilo"``, ``"mock"``).
      3. ``kilo.json`` at the project root — field ``backend`` (or
         ``execution_backend``).
      4. Default: ``"kilo"`` → :class:`KiloBackend`.

    The returned backend is cached per ``name``. Calling
    ``get_backend("mock")`` twice returns the same instance. Pass ``name``
    to override the resolved default.

    Supported ``name`` values:

      - ``"kilo"`` → :class:`KiloBackend` (real subprocess LLM)
      - ``"mock"`` → ``MockBackend`` (in-memory, deterministic — see
        ``backend_mock.py``)
    """
    if name is None:
        name = _resolve_backend_name()

    name = (name or "").strip().lower()
    if not name:
        name = "kilo"

    if name in _BACKEND_CACHE:
        return _BACKEND_CACHE[name]

    backend = _instantiate_backend(name)
    _BACKEND_CACHE[name] = backend
    return backend


def reset_backend_cache() -> None:
    """Forget cached backend instances.

    Useful for tests that need to re-read ``kilo.json`` or re-evaluate
    ``ELYRA_BACKEND`` mid-run. Production callers should not need this.
    """
    _BACKEND_CACHE.clear()


# ---------------------------------------------------------------------------
# Resolution helpers — kept module-private so callers go through get_backend.
# ---------------------------------------------------------------------------


def _resolve_backend_name() -> str:
    """Read the backend name from env / kilo.json, falling back to ``"kilo"``."""
    env_name = os.environ.get(ENV_VAR)
    if env_name:
        return env_name

    kilo_json_path = _find_kilo_json()
    if kilo_json_path is not None:
        try:
            data = json.loads(kilo_json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict):
            # Accept either "backend" or "execution_backend" as the key.
            for key in ("backend", "execution_backend"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value

    return "kilo"


def _find_kilo_json() -> Optional[Path]:
    """Locate the ``kilo.json`` config file.

    Search order (most-specific first):

      1. ``<project_root>/kilo.json`` (the conventional location per PLAN.md).
      2. ``<project_root>/.kilo/kilo.json`` (the user-level Kilo config).

    Returns the first match, or ``None`` if neither exists.
    """
    # tools/execution/__init__.py → parents[2] is the project root.
    here = Path(__file__).resolve()
    project_root = here.parents[2]

    for candidate in (project_root / "kilo.json", project_root / ".kilo" / "kilo.json"):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _instantiate_backend(name: str) -> ExecutionBackend:
    """Instantiate a backend by name. Lazy imports to keep this module
    import-light and to avoid loading backends the user didn't ask for.
    """
    if name == "kilo":
        # KiloBackend is already imported at the top of this module.
        return KiloBackend()
    if name == "mock":
        from tools.execution.backend_mock import MockBackend
        return MockBackend()
    raise ValueError(
        f"Unknown execution backend '{name}'. Known backends: "
        f"{', '.join(repr(n) for n in _KNOWN_BACKENDS)}. "
        f"Set the {ENV_VAR} env var or the 'backend' field in kilo.json."
    )


__all__ = [
    "ExecutionBackend",
    "get_backend",
    "reset_backend_cache",
    "ToolResult",
    "KiloBackend",
    "BackendInvokeError",
    "resolve_persona",
    "ENV_VAR",
]


# Re-export MockBackend at the package level so callers (and tests) can
# import ``from tools.execution import MockBackend`` without reaching
# into the backend_mock submodule directly. The actual class lives in
# backend_mock.py; this is a thin re-export.
def __getattr__(name):  # pragma: no cover - exercised via tests
    if name == "MockBackend":
        from tools.execution.backend_mock import MockBackend as _MockBackend
        return _MockBackend
    raise AttributeError(f"module 'tools.execution' has no attribute {name!r}")
