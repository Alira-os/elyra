"""
json_extract.py — Shared, deterministic JSON extraction for Kilo CLI output.

Replaces 4+ copy-pasted extract_json_from_output() implementations that all
shared the same bug: when extraction failed, callers silently fell through to
a "{}" string and produced useless artifacts. That bug accounted for 17/25
(68%) of all gaps in the last E2E run.

Design:
  - Single public function: extract_json(text) -> dict
  - Strict: never returns a fake/empty object. Raises JSONExtractionError
    with the full raw text and a precise reason on failure.
  - Handles every observed Kilo output shape:
      1. Bare JSON object
      2. Fenced ```json ... ``` blocks
      3. NDJSON event stream (Kilo --format json emits one JSON per line;
         we look for the last "text" event and extract from there)
      4. JSON embedded in prose (outermost-brace matching with proper
         string/escape handling, not naive first/last brace slicing)
      5. ToolResult wrapper {"success": ..., "summary": "<json string>"}
      6. JSON inside a "summary" or "manager_decision" field

No silent fallbacks. No defaults. The caller is responsible for deciding
what to do with the error (route back to the persona, abort, etc.).
"""

from __future__ import annotations

import json
import re
from typing import Optional


class JSONExtractionError(Exception):
    """Raised when no valid JSON object can be extracted from the input.

    Carries enough context for the caller to log a useful gap:
      - reason: short tag (e.g. "no_json_object_found", "unbalanced_braces")
      - preview: first 400 chars of the raw text (safe for printing)
      - raw_text: full original input (caller decides whether to log it)
    """

    def __init__(self, reason: str, raw_text: str, message: Optional[str] = None):
        self.reason = reason
        self.raw_text = raw_text
        self.preview = (raw_text or "")[:400]
        if message is None:
            message = f"JSONExtractionError({reason}): preview={self.preview!r}"
        super().__init__(message)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"JSONExtractionError(reason={self.reason!r}, preview={self.preview!r})"


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _safe_loads(text: str) -> Optional[object]:
    """Try json.loads; return None on any error (including non-object types)."""
    if not text or not text.strip():
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _find_outermost_json_object(text: str) -> Optional[str]:
    """Locate the outermost {...} JSON object in text, respecting strings and escapes.

    Returns the substring (inclusive of braces) or None if not found / unbalanced.
    """
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False
    end = -1
    for i, c in enumerate(text[start:], start=start):
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return None
    return text[start:end]


def _extract_from_ndjson(text: str) -> Optional[str]:
    """If text is NDJSON, return the last 'text' event's text field (or None)."""
    if not text:
        return None
    last_text: Optional[str] = None
    saw_event = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = _safe_loads(line)
        if not isinstance(obj, dict):
            continue
        saw_event = True
        if obj.get("type") == "text":
            part = obj.get("part") or {}
            if isinstance(part, dict):
                t = part.get("text")
                if isinstance(t, str):
                    last_text = t
    return last_text if saw_event else None


def _try_toolresult_unwrap(text: str) -> Optional[object]:
    """If text is a ToolResult wrapper, look for JSON inside summary / manager_decision / decision."""
    obj = _safe_loads(text)
    if not isinstance(obj, dict):
        return None
    if "action" in obj:
        return obj  # already a ManagerDecision
    for key in ("manager_decision", "decision"):
        nested = obj.get(key)
        if isinstance(nested, dict) and "action" in nested:
            return nested
        if isinstance(nested, str):
            parsed = _safe_loads(nested)
            if isinstance(parsed, dict) and "action" in parsed:
                return parsed
    summary = obj.get("summary")
    if isinstance(summary, str):
        # Try summary as JSON first
        parsed = _safe_loads(summary)
        if isinstance(parsed, dict) and "action" in parsed:
            return parsed
        # Then try extracting outermost JSON object from summary prose
        candidate = _find_outermost_json_object(summary)
        if candidate:
            parsed = _safe_loads(candidate)
            if isinstance(parsed, dict) and "action" in parsed:
                return parsed
    return None


def extract_json(text: str) -> dict:
    """Extract a JSON object from Kilo CLI output. Returns dict or raises.

    Strategy (in order):
      1. Empty/None input → raise immediately with reason='empty_input'.
      2. Whole text is valid JSON object AND doesn't look like a ToolResult
         wrapper (i.e., has fields a real artifact would have, like 'action'
         or 'success' ONLY as part of a manager decision — not a wrapper).
         Specifically, if the dict has 'summary' + ('success' or 'files_created')
         we treat it as a wrapper and skip to step 3.
      3. ```json ... ``` fenced block(s); first one that parses.
      4. ToolResult-style wrapper unwrap: look for manager_decision /
         decision / JSON in summary.
      5. NDJSON: take last 'text' event, then recurse on its body.
      6. Outermost {...} match in text, with proper string/escape handling.

    Raises:
        JSONExtractionError if no valid JSON object can be found.
    """
    if text is None or text == "":
        raise JSONExtractionError("empty_input", text or "")
    raw = text

    # 1. Whole text as JSON object
    parsed = _safe_loads(raw)
    if isinstance(parsed, dict):
        # If this looks like a ToolResult wrapper or NDJSON event, fall
        # through to the unwrap/recursion steps instead of returning the
        # container itself.
        if not _is_wrapper_or_event(parsed):
            return parsed
        # else: fall through to step 3 (unwrapping)
    else:
        # 2. Fenced code blocks (only try this path if whole text isn't JSON
        # — we don't want to skip past a valid ToolResult wrapper).
        for match in _FENCE_RE.finditer(raw):
            candidate = (match.group(1) or "").strip()
            parsed = _safe_loads(candidate)
            if isinstance(parsed, dict):
                return parsed

    # 3. ToolResult wrapper unwrap
    unwrapped = _try_toolresult_unwrap(raw)
    if isinstance(unwrapped, dict):
        return unwrapped

    # 4. NDJSON: try the last 'text' event body, then recurse
    last_text = _extract_from_ndjson(raw)
    if last_text:
        try:
            return extract_json(last_text)
        except JSONExtractionError:
            # fall through to outermost-brace strategy on the last_text body
            candidate = _find_outermost_json_object(last_text)
            if candidate:
                parsed = _safe_loads(candidate)
                if isinstance(parsed, dict):
                    return parsed

    # 5. Outermost {...} match in the whole text
    candidate = _find_outermost_json_object(raw)
    if candidate:
        parsed = _safe_loads(candidate)
        if isinstance(parsed, dict):
            return parsed

    # Give up. Don't pretend we found something.
    raise JSONExtractionError("no_valid_json_object_found", raw)


def _is_wrapper_or_event(obj: dict) -> bool:
    """Heuristic: does this dict look like a *container* (ToolResult wrapper
    or NDJSON event) rather than a real artifact (VisualDirection,
    BuildManifest, ManagerDecision, etc.)?

    ToolResult shape: {success, files_created, ..., summary, recovery_suggestion}
    NDJSON event shape: {type, part: {...}}
    """
    if "action" in obj:
        return False  # already a ManagerDecision
    # NDJSON event
    if isinstance(obj.get("type"), str) and obj.get("type") == "text" and isinstance(obj.get("part"), dict):
        return True
    # ToolResult
    toolresult_keys = {
        "success", "files_created", "files_modified", "errors",
        "summary", "recovery_suggestion",
    }
    if any(k in obj for k in ("success", "files_created", "files_modified")):
        return any(k in obj for k in toolresult_keys)
    return False
