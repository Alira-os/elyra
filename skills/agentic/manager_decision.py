"""
manager_decision.py — Validate and repair ManagerDecision from LLM output.

Phase 0.7: The LLM-driven manager persona occasionally returns malformed
decisions (prose instead of JSON, missing `action`, or a JSON object that
fails Pydantic validation). The legacy code path had 175 lines of
hand-rolled brace-counting + filter-to-allowed-fields logic that still
ended in "Missing action in manager decision" aborts.

This module replaces all of that with a clean three-step pipeline:

  1. extract_json() — find the JSON object in the LLM output (handles
     fenced blocks, ToolResult wrappers, NDJSON events, prose-embedded
     JSON, etc.). Defined in skills/agentic/json_extract.py.
  2. Pydantic validation — instantiate ManagerDecision (defined in
     models/site_schemas.py). The Literal enum on `action` catches
     typos. Optional fields default cleanly.
  3. Repair — on failure, return a deterministic ManagerDecision
     (NOT a re-prompt loop). Re-prompting the LLM to fix its own output
     is unreliable; deterministic fall-through to a clear abort is
     always better than a hung manager.

The helper is site-agnostic by design: it works for any migration the
manager persona drives, regardless of source platform. There's no
per-site tuning — the validator is a pure function of (text → decision).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from models.site_schemas import ManagerDecision
from skills.agentic.json_extract import extract_json, JSONExtractionError

logger = logging.getLogger(__name__)


def _abort_decision(reason: str, raw_preview: str = "") -> ManagerDecision:
    """Build a deterministic abort decision with a precise reason."""
    full_reason = reason
    if raw_preview:
        # Truncate so the gap ledger stays readable.
        snippet = raw_preview[:200].replace("\n", " ").strip()
        full_reason = f"{reason} | raw: {snippet!r}"
    return ManagerDecision(
        action="abort",
        reason=full_reason,
    )


# Phase B: action normalizer. The LLM occasionally emits actions with
# leading/trailing whitespace or unusual capitalization (e.g. "Invoke
# persona" or "ROUTE_BACK"). Before the existing repair map lookup,
# normalize to a canonical form so these harmless slips don't abort the
# manager loop. The repair map itself is unchanged; this just makes the
# lookup more forgiving.
_VALID_ACTIONS = frozenset({
    "invoke_persona", "route_back", "complete",
    "github_issue_created", "abort",
})

_REPAIR_MAP = {
    "create_github_issue": "github_issue_created",
    "github_issue": "github_issue_created",
    "retry": "invoke_persona",
    "loop": "invoke_persona",
    "continue": "complete",
    "done": "complete",
    "finish": "complete",
    "stop": "abort",
    "fail": "abort",
}


def _normalize_action(raw: str) -> str:
    """Normalize a manager-decision `action` string to a canonical form.

    Pipeline:
      1. Strip whitespace.
      2. Lower-case.
      3. If the result is a valid action, return it.
      4. Else if the value is multi-word (e.g. "Invoke persona"),
         try to map the first token through the repair map. The
         most common LLM slip is "Invoke persona" → "invoke_persona"
         and "Create GitHub issue" → "github_issue_created".
      5. Else consult the repair map for single-word synonyms.
      6. Else return the normalized string unchanged so Pydantic
         validation produces a precise abort.
    """
    if not isinstance(raw, str):
        return raw
    n = raw.strip().lower()
    if n in _VALID_ACTIONS:
        return n
    # Multi-word: "Invoke persona" / "Create GitHub issue" / "Route back".
    # The LLM sometimes emits the action as natural language rather
    # than snake_case. Map the first word (and "github" + "issue"
    # combo) into the canonical enum value.
    if " " in n:
        first = n.split()[0]
        if first in _REPAIR_MAP:
            return _REPAIR_MAP[first]
        # "create github issue" / "open github issue" / "file github issue"
        if first in {"create", "open", "file", "new", "make"} and "github" in n:
            return "github_issue_created"
        # "send back" / "route back" / "go back" → "route_back"
        if first in {"send", "route", "go", "bounce"} and "back" in n:
            return "route_back"
        # "run persona" / "invoke persona" / "call persona" → "invoke_persona"
        if first in {"run", "invoke", "call", "use", "try", "do", "re", "reinvoke"}:
            return "invoke_persona"
    if n in _REPAIR_MAP:
        return _REPAIR_MAP[n]
    return n


def validate_and_repair_manager_decision(
    raw_text: Any,
    *,
    on_parse_error: Optional[str] = None,
) -> ManagerDecision:
    """Turn raw LLM output (or any object) into a validated ManagerDecision.

    Args:
        raw_text: anything the LLM (or its ToolResult wrapper) produced.
            Can be a string, a dict, a ToolResult-like object with a
            `.summary` attribute, or None.
        on_parse_error: optional reason prefix for the gap that's logged
            when validation fails. None = no logging (caller logs).

    Returns:
        A validated ManagerDecision. Never raises. On any failure mode
        (couldn't extract JSON, JSON didn't validate, action was bogus),
        returns a deterministic ManagerDecision(action="abort", reason=...).
    """
    # Step 0: normalize input.
    if raw_text is None:
        return _abort_decision("manager persona returned None")

    # If we already have a ManagerDecision, return as-is.
    if isinstance(raw_text, ManagerDecision):
        return raw_text

    if isinstance(raw_text, dict):
        # The caller (or the manager prompt) already produced a dict.
        # Skip extraction and validate directly.
        data = raw_text
    else:
        # String or ToolResult-like. Coerce to text.
        if isinstance(raw_text, str):
            text = raw_text
        else:
            # ToolResult-like: pull .summary if available, else .to_json().
            summary = getattr(raw_text, "summary", None)
            if isinstance(summary, str) and summary:
                text = summary
            elif hasattr(raw_text, "to_json"):
                try:
                    text = raw_text.to_json()
                except Exception:
                    text = str(raw_text)
            else:
                text = str(raw_text)

        if not text or not text.strip():
            return _abort_decision("manager persona returned empty text", raw_preview="")

        # Step 1: extract the JSON object from the text.
        try:
            data = extract_json(text)
        except JSONExtractionError as e:
            return _abort_decision(
                f"manager persona returned text with no valid JSON: {e.reason}",
                raw_preview=e.preview,
            )

        if not isinstance(data, dict):
            return _abort_decision(
                f"manager persona extracted value is not a dict: {type(data).__name__}",
                raw_preview=str(data)[:200],
            )

        if not isinstance(data, dict):
            return _abort_decision(
                f"manager persona extracted value is not a dict: {type(data).__name__}",
                raw_preview=str(data)[:200],
            )

    # Step 2: Pydantic validation. The Literal enum on `action` enforces
    # the closed set; everything else gets coerced or stripped.
    try:
        return ManagerDecision.model_validate(data)
    except Exception as e:
        # Validation failed. Try one targeted repair: if the dict has
        # an `action` that's not in the Literal enum, normalize it
        # (Phase B: strip whitespace + lower-case) and consult the
        # repair map for common LLM slips:
        #   "create_github_issue" → "github_issue_created"
        #   "retry", "loop" → "invoke_persona" (default)
        #   "Invoke persona"     → "invoke_persona" (Phase B)
        #   "ROUTE_BACK"         → "route_back"     (Phase B)
        action = data.get("action")
        if isinstance(action, str):
            normalized = _normalize_action(action)
            if normalized and normalized != action and normalized in {
                "invoke_persona", "route_back", "complete",
                "github_issue_created", "abort",
            }:
                repaired = dict(data)
                repaired["action"] = normalized
                try:
                    return ManagerDecision.model_validate(repaired)
                except Exception:
                    pass  # fall through to abort
        return _abort_decision(
            f"manager decision failed Pydantic validation: {e}",
            raw_preview=str(data)[:200],
        )
