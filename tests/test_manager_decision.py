"""
Unit tests for skills/agentic/manager_decision.py

Phase 0.7: validate_and_repair_manager_decision() is the new entry point
for processing the LLM's manager output. It must:
  1. Return a valid Pydantic ManagerDecision on well-formed input.
  2. Repair common LLM slips (e.g. "create_github_issue" instead of
     "github_issue_created", or "stop" / "done" / "fail" for action).
  3. Return a deterministic abort on garbage input (no raising).
  4. Handle ToolResult-like objects (with .summary) and raw strings.

These tests lock the contract — if any test fails, the manager loop is
no longer self-healing through the helper.

Run:
    python -m pytest tests/test_manager_decision.py -v
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import ManagerDecision  # noqa: E402
from skills.agentic.manager_decision import validate_and_repair_manager_decision  # noqa: E402


# --- Happy paths ------------------------------------------------------------

def test_valid_json_string_passes():
    d = validate_and_repair_manager_decision(
        '{"action": "invoke_persona", "persona": "designer", "reason": "redo the visual"}'
    )
    assert d.action == "invoke_persona"
    assert d.persona == "designer"
    assert d.reason == "redo the visual"
    assert d.gaps_detected == []  # defaulted


def test_fenced_json_block_passes():
    d = validate_and_repair_manager_decision(
        "Here is the decision:\n```json\n"
        '{"action": "complete", "reason": "all done"}\n'
        "```\nThanks."
    )
    assert d.action == "complete"
    assert d.reason == "all done"


def test_prose_embedded_json_passes():
    d = validate_and_repair_manager_decision(
        'The manager decided: {"action": "route_back", "persona": "scraper", "reason": "missing fields"}'
    )
    assert d.action == "route_back"
    assert d.persona == "scraper"


def test_dict_input_passes():
    d = validate_and_repair_manager_decision(
        {"action": "complete", "reason": "all set"}
    )
    assert d.action == "complete"


def test_toolresult_with_summary():
    """The helper should pull .summary from ToolResult-like objects."""
    class FakeToolResult:
        def __init__(self, summary):
            self.summary = summary
        def to_json(self):
            return json.dumps({"success": True, "summary": self.summary})

    fake = FakeToolResult('{"action": "complete", "reason": "stub"}')
    d = validate_and_repair_manager_decision(fake)
    assert d.action == "complete"
    assert d.reason == "stub"


def test_toolresult_wrapper_with_action_inside_summary():
    """A ToolResult wrapper with a manager_decision nested should be unwrapped."""
    class FakeToolResult:
        def __init__(self, summary):
            self.summary = summary

    fake = FakeToolResult(json.dumps({
        "action": "invoke_persona",
        "persona": "designer",
        "reason": "visual incomplete",
    }))
    d = validate_and_repair_manager_decision(fake)
    assert d.action == "invoke_persona"
    assert d.persona == "designer"


# --- Action enum repair (common LLM slips) ----------------------------------

def test_repair_create_github_issue_to_github_issue_created():
    d = validate_and_repair_manager_decision(
        '{"action": "create_github_issue", "reason": "track this failure"}'
    )
    assert d.action == "github_issue_created"


def test_repair_loose_action_synonyms():
    """'stop' → abort; 'done' / 'finish' / 'continue' → complete."""
    for loose, expected in [
        ("stop", "abort"),
        ("fail", "abort"),
        ("done", "complete"),
        ("finish", "complete"),
        ("continue", "complete"),
        ("retry", "invoke_persona"),
    ]:
        d = validate_and_repair_manager_decision(
            json.dumps({"action": loose, "reason": f"loose={loose}"})
        )
        assert d.action == expected, f"{loose!r} should map to {expected!r}, got {d.action!r}"


def test_unknown_action_falls_through_to_abort():
    """A syntactically valid action that isn't in the repair map should
    fall through to the deterministic abort."""
    d = validate_and_repair_manager_decision(
        '{"action": "perform_magic", "reason": "nonsense"}'
    )
    assert d.action == "abort"
    assert "manager decision" in d.reason or "failed" in d.reason.lower()


# --- Failure paths (must return abort, never raise) --------------------------

def test_none_input_returns_abort():
    d = validate_and_repair_manager_decision(None)
    assert d.action == "abort"
    assert "None" in d.reason


def test_empty_string_returns_abort():
    d = validate_and_repair_manager_decision("")
    assert d.action == "abort"


def test_whitespace_only_returns_abort():
    d = validate_and_repair_manager_decision("   \n\t  ")
    assert d.action == "abort"


def test_prose_only_returns_abort():
    d = validate_and_repair_manager_decision(
        "I think we should probably retry the builder with more context."
    )
    assert d.action == "abort"
    # The reason should be informative
    assert "manager persona" in d.reason or "no valid JSON" in d.reason.lower()


def test_invalid_json_returns_abort():
    d = validate_and_repair_manager_decision(
        '{"action": "invoke_persona", "persona":'  # truncated
    )
    assert d.action == "abort"


def test_json_array_at_top_level_returns_abort():
    d = validate_and_repair_manager_decision('[1, 2, 3]')
    assert d.action == "abort"


def test_missing_action_field_returns_abort():
    """A JSON object that has persona + reason but no action should fail."""
    d = validate_and_repair_manager_decision(
        '{"persona": "designer", "reason": "no action field"}'
    )
    assert d.action == "abort"


def test_non_dict_extracted_value_returns_abort():
    """If the extractor pulls out a non-dict (e.g. a string), abort."""
    # extract_json on plain text returns a dict normally; force the
    # edge case by passing a bare quoted string.
    d = validate_and_repair_manager_decision('"just a string, not an object"')
    assert d.action == "abort"


# --- Pydantic validation enforces strictness -------------------------------

def test_valid_decision_is_a_pydantic_model():
    d = validate_and_repair_manager_decision(
        '{"action": "complete", "persona": "designer", "reason": "x", "confidence": 0.95, "iteration": 3}'
    )
    assert isinstance(d, ManagerDecision)
    assert d.confidence == 0.95
    assert d.iteration == 3


def test_gaps_detected_list_is_preserved():
    d = validate_and_repair_manager_decision(json.dumps({
        "action": "route_back",
        "persona": "designer",
        "reason": "redo",
        "gaps_detected": [
            {"gap_id": "g1", "severity": "high", "target_persona": "designer"}
        ]
    }))
    assert d.action == "route_back"
    assert len(d.gaps_detected) == 1
    assert d.gaps_detected[0]["gap_id"] == "g1"


def test_extra_fields_are_silently_dropped():
    """Pydantic should drop fields that aren't in the schema, not raise."""
    d = validate_and_repair_manager_decision(json.dumps({
        "action": "complete",
        "reason": "x",
        "future_field": "should be dropped",
        "another_extra": 42,
    }))
    assert d.action == "complete"
    assert not hasattr(d, "future_field")


def test_unknown_action_not_in_repair_map_does_not_crash():
    """Torture test: an action value that is neither in the enum nor
    in the repair map. Must still produce a clean ManagerDecision."""
    d = validate_and_repair_manager_decision(
        json.dumps({"action": "???", "reason": "test"})
    )
    assert isinstance(d, ManagerDecision)
    assert d.action == "abort"


if __name__ == "__main__":
    import traceback
    tests = [
        test_valid_json_string_passes,
        test_fenced_json_block_passes,
        test_prose_embedded_json_passes,
        test_dict_input_passes,
        test_toolresult_with_summary,
        test_toolresult_wrapper_with_action_inside_summary,
        test_repair_create_github_issue_to_github_issue_created,
        test_repair_loose_action_synonyms,
        test_unknown_action_falls_through_to_abort,
        test_none_input_returns_abort,
        test_empty_string_returns_abort,
        test_whitespace_only_returns_abort,
        test_prose_only_returns_abort,
        test_invalid_json_returns_abort,
        test_json_array_at_top_level_returns_abort,
        test_missing_action_field_returns_abort,
        test_non_dict_extracted_value_returns_abort,
        test_valid_decision_is_a_pydantic_model,
        test_gaps_detected_list_is_preserved,
        test_extra_fields_are_silently_dropped,
        test_unknown_action_not_in_repair_map_does_not_crash,
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
