"""
Unit tests for skills/agentic/json_extract.py

Phase 0: locks in the behavior of the shared JSON extractor. Every test
exercises one of the failure modes seen in the last E2E run.

Run:
    cd C:\\Users\\micha\\DevProjects\\Alira\\elyra
    python -m pytest tests/test_json_extract.py -v

Or directly:
    python tests/test_json_extract.py
"""

import json
import sys
import os
from pathlib import Path

# Make the elyra package importable when running this file directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills.agentic.json_extract import extract_json, JSONExtractionError  # noqa: E402


# --- Happy paths ------------------------------------------------------------

def test_bare_json_object():
    out = extract_json('{"a": 1, "b": "two"}')
    assert out == {"a": 1, "b": "two"}


def test_pretty_printed_json():
    out = extract_json('{\n  "action": "invoke_persona",\n  "persona": "builder"\n}')
    assert out == {"action": "invoke_persona", "persona": "builder"}


def test_fenced_json_block():
    text = (
        "Here is the result:\n\n"
        "```json\n"
        '{"action": "complete", "reason": "all good"}\n'
        "```\n\n"
        "Done."
    )
    out = extract_json(text)
    assert out == {"action": "complete", "reason": "all good"}


def test_fenced_no_language_tag():
    text = "```\n{\"x\": 1}\n```"
    out = extract_json(text)
    assert out == {"x": 1}


def test_json_embedded_in_prose():
    text = (
        "I think the answer is roughly: {\"action\": \"invoke_persona\", "
        "\"persona\": \"designer\"} — go ahead and run that."
    )
    out = extract_json(text)
    assert out["action"] == "invoke_persona"
    assert out["persona"] == "designer"


def test_json_with_nested_braces_and_strings():
    text = (
        'Reason: {"action": "invoke_persona", "persona": "builder", '
        '"reason": "this {is} a tricky string with } braces"} end'
    )
    out = extract_json(text)
    assert out["action"] == "invoke_persona"
    assert "{" in out["reason"] and "}" in out["reason"]


def test_ndjson_last_text_event():
    text = (
        '{"type": "init", "session": "abc"}\n'
        '{"type": "text", "part": {"text": "Working on it..."}}\n'
        '{"type": "text", "part": {"text": "```json\\n{\\"action\\": \\"complete\\"}\\n```"}}\n'
    )
    out = extract_json(text)
    assert out == {"action": "complete"}


def test_toolresult_wrapper_with_action():
    text = json.dumps({
        "success": True,
        "files_created": [],
        "summary": "",
        "manager_decision": {"action": "complete", "reason": "done"},
    })
    out = extract_json(text)
    assert out == {"action": "complete", "reason": "done"}


def test_toolresult_wrapper_with_summary_containing_json():
    text = json.dumps({
        "success": True,
        "summary": 'The manager decided: {"action": "invoke_persona", "persona": "designer"}',
    })
    out = extract_json(text)
    assert out == {"action": "invoke_persona", "persona": "designer"}


def test_toolresult_wrapper_with_decision_field():
    text = json.dumps({
        "success": True,
        "summary": "thinking...",
        "decision": {"action": "abort", "reason": "no plan"},
    })
    out = extract_json(text)
    assert out == {"action": "abort", "reason": "no plan"}


# --- Failure paths (must RAISE, never silently return {}) -------------------

def test_empty_input_raises():
    try:
        extract_json("")
    except JSONExtractionError as e:
        assert e.reason == "empty_input"
        return
    raise AssertionError("expected JSONExtractionError on empty input")


def test_no_json_at_all_raises():
    try:
        extract_json("just a plain text response with no objects whatsoever")
    except JSONExtractionError as e:
        assert e.reason == "no_valid_json_object_found"
        assert "no objects" in e.preview
        return
    raise AssertionError("expected JSONExtractionError on plain prose")


def test_unbalanced_braces_raises():
    try:
        extract_json('{"action": "invoke_persona", "persona": "designer"')
    except JSONExtractionError as e:
        # Either "no_valid_json_object_found" or any other reason is fine —
        # what matters is that it raised.
        assert e.reason
        return
    raise AssertionError("expected JSONExtractionError on unbalanced braces")


def test_array_at_top_level_is_rejected():
    """An array is valid JSON but is not a JSON object. We want a dict."""
    try:
        extract_json('[1, 2, 3]')
    except JSONExtractionError:
        return
    raise AssertionError("expected JSONExtractionError on top-level array")


def test_none_input_raises():
    try:
        extract_json(None)
    except JSONExtractionError as e:
        assert e.reason == "empty_input"
        return
    raise AssertionError("expected JSONExtractionError on None")


# --- Regression cases for the original failure shape -----------------------

def test_fenced_with_extra_whitespace():
    """The original extractors failed on leading/trailing whitespace."""
    text = '\n```json\n   \n  {"a": 1}  \n   \n```\n'
    out = extract_json(text)
    assert out == {"a": 1}


def test_realistic_kilo_output():
    """A realistic Kilo text event payload, mimicking what the manager sees."""
    text = json.dumps({
        "type": "text",
        "part": {
            "text": (
                "Analyzed current state. My decision:\n\n"
                "```json\n"
                "{\n"
                '  "action": "route_back",\n'
                '  "persona": "designer",\n'
                '  "reason": "VisualDirection missing delta fields",\n'
                '  "gap_context": "Add typography_delta for headings"\n'
                "}\n"
                "```\n"
            )
        }
    })
    out = extract_json(text)
    assert out["action"] == "route_back"
    assert out["persona"] == "designer"
    assert "VisualDirection" in out["reason"]


# --- Direct runner ----------------------------------------------------------

if __name__ == "__main__":
    # Make it possible to run this file with plain `python tests/test_json_extract.py`.
    import traceback
    tests = [
        test_bare_json_object,
        test_pretty_printed_json,
        test_fenced_json_block,
        test_fenced_no_language_tag,
        test_json_embedded_in_prose,
        test_json_with_nested_braces_and_strings,
        test_ndjson_last_text_event,
        test_toolresult_wrapper_with_action,
        test_toolresult_wrapper_with_summary_containing_json,
        test_toolresult_wrapper_with_decision_field,
        test_empty_input_raises,
        test_no_json_at_all_raises,
        test_unbalanced_braces_raises,
        test_array_at_top_level_is_rejected,
        test_none_input_raises,
        test_fenced_with_extra_whitespace,
        test_realistic_kilo_output,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(0 if failures == 0 else 1)
