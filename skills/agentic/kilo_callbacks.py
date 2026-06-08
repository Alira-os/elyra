"""
kilo_callbacks.py — Shared callback builders for invoke_kilo_safe().

Centralizes the persona → on_timeout wiring so the 6 persona modules
don't each have to define the same lambda. Also keeps the
"source_persona" / "target_persona" / "severity" naming consistent.

Phase 0 rationale: in the last E2E run, timeouts landed in the gap
ledger as bare "Kilo CLI timed out after 120s" with no link to which
persona was running or how big the prompt was. With these helpers, every
timeout gap now carries (persona, prompt_size, elapsed_s).
"""

from __future__ import annotations

from typing import Optional


def make_timeout_callback(
    persona: str,
    migration_id_fn,
    default_timeout_s: int,
    severity: str = "high",
):
    """Build an on_timeout callback for invoke_kilo_safe().

    Args:
        persona: the calling persona's name (e.g. "ui_designer", "builder").
        migration_id_fn: callable that returns the current migration_id.
            We accept a callable because the migration_id isn't known at
            module import time — it's threaded through the call chain.
        default_timeout_s: the timeout value the persona was given. Used in
            the gap description so the entry tells you which budget was hit.
        severity: gap severity (default "high" — a timeout is a real failure).

    Returns:
        Callable(elapsed_s, prompt_size_chars, persona) -> None
        that logs a structured gap with target_persona=<persona>.
    """
    def _on_timeout(elapsed_s: float, prompt_size: int, _persona: str) -> None:
        try:
            from memory.gap_ledger import log_gap
            log_gap(
                migration_id=migration_id_fn() or "",
                gap_type="gate_failure",
                source_persona=persona,
                target_persona=persona,
                description=(
                    f"Kilo CLI timed out after {elapsed_s:.1f}s "
                    f"(budget {default_timeout_s}s, prompt={prompt_size} chars) "
                    f"during {persona} phase"
                ),
                suggested_fix=(
                    "Reduce prompt size; split persona into sub-steps; "
                    "or raise the budget for this persona if the work is real."
                ),
                severity=severity,
            )
        except Exception:
            # Never let gap-logging break a persona.
            pass
    return _on_timeout
