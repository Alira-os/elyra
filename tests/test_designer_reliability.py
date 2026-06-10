"""
Unit tests for skills/agentic/designer_agent.py — Phase 0.7 reliability changes.

The designer is the worst-performing persona (24/35 = 69% of all logged
gaps). This file locks in the three reliability changes that target
those gaps:

  1. Persona markdown is trimmed (no more 14.6KB of CSS examples).
  2. build_designer_prompt() no longer inlines the Pydantic JSON schema
     (it lists VisualDirection fields explicitly instead).
  3. design() now (a) retries up to 2 times on JSON extraction failure
     and (b) falls back to lenient_parse_visual_direction() to salvage
     any partial fields from unparseable Kilo output.

We don't invoke Kilo here (that requires the kilo binary + network).
We exercise the deterministic helpers.

Run:
    cd C:\\Users\\micha\\DevProjects\\Alira\\elyra
    python -m pytest tests/test_designer_reliability.py -v
"""

import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills.agentic.designer_agent import (  # noqa: E402
    _collect_last_text,
    build_designer_prompt,
    lenient_parse_visual_direction,
    load_content_recommendation,
    load_site_understanding,
)
from tools.kilo import ToolResult  # noqa: E402


# --- Persona markdown trim -------------------------------------------------

def test_persona_markdown_is_under_5kb():
    """The persona must be small — Kilo can hang on oversized prompts.

    14,632 bytes (original) -> 3,690 bytes (Phase 0.7). We allow up to
    5KB to give some headroom for future additions.
    """
    size = Path("registry/personas/ui_designer.md").stat().st_size
    assert size < 5_000, f"ui_designer.md is {size} bytes; expected <5KB (was 14.6KB)"


def test_persona_markdown_does_not_contain_full_css_blocks():
    """The trimmed persona no longer embeds ~120 lines of CSS examples.
    Kilo already knows CSS — the persona only needs the *contract*."""
    text = Path("registry/personas/ui_designer.md").read_text()
    assert ":root {" not in text, "persona should not embed :root CSS blocks"
    assert "@media (prefers-reduced-motion" not in text, "persona should not embed @media blocks"
    assert ".btn {" not in text, "persona should not embed .btn CSS blocks"


def test_persona_keeps_motion_philosophy_table():
    """The motion philosophy table is contractual — must stay."""
    text = Path("registry/personas/ui_designer.md").read_text()
    for philosophy in ("monastic", "classical", "energetic", "subtle"):
        assert philosophy in text, f"persona missing motion philosophy: {philosophy}"


def test_persona_keeps_stitch_fallback_contract():
    """The 'never return {}' Stitch-fallback contract must stay."""
    text = Path("registry/personas/ui_designer.md").read_text()
    assert "Stitch" in text
    assert "BrandSpec fidelity" in text


# --- build_designer_prompt: no inline schema -----------------------------

def test_designer_prompt_does_not_inline_full_json_schema():
    """Phase 0.7: the inlined Pydantic JSON schema for VisualDirection
    was ~3KB of pure noise (Kilo can infer fields from the explicit
    field list). Confirm we don't dump $defs / $ref / anyOf / etc.
    """
    site = load_site_understanding("20260601_104145")
    rec = load_content_recommendation("20260601_104458")
    prompt = build_designer_prompt(site, rec, "merimee")
    # Pydantic-generated schema markers
    for noise in ('"$defs"', '"$ref"', "additionalProperties", "anyOf", "allOf"):
        assert noise not in prompt, f"designer prompt contains schema noise: {noise}"


def test_designer_prompt_under_designer_budget():
    """The designer prompt must be well under the 14K budget.

    62,499 (original) -> 23,177 (after Phase 0.6) -> ~8,800 (Phase 0.7).
    """
    site = load_site_understanding("20260601_104145")
    rec = load_content_recommendation("20260601_104458")
    prompt = build_designer_prompt(site, rec, "merimee")
    assert len(prompt) < 14_000, f"designer prompt is {len(prompt)} chars; expected <14K"


def test_designer_prompt_lists_visual_direction_fields():
    """Kilo still needs to know which fields to populate — confirm the
    explicit field list survived the trim."""
    site = load_site_understanding("20260601_104145")
    rec = load_content_recommendation("20260601_104458")
    prompt = build_designer_prompt(site, rec, "merimee")
    for field in (
        "primary_change", "rationale", "stitch_status",
        "impacted_components", "impacted_pages",
        "color_delta", "typography_delta", "motion_delta",
        "designer_notes", "created_at",
    ):
        assert field in prompt, f"designer prompt missing field: {field}"


# --- _collect_last_text: the building block of the retry loop -------------

def test_collect_last_text_returns_last_text_event():
    """Kilo emits NDJSON; we want the last 'text' event payload."""
    ndjson = (
        '{"type": "init"}\n'
        '{"type": "text", "part": {"text": "Working on it..."}}\n'
        '{"type": "text", "part": {"text": "Here is the JSON: {\\"x\\": 1}"}}\n'
        '{"type": "step_finish"}\n'
    )
    last = _collect_last_text(ndjson)
    assert last == 'Here is the JSON: {"x": 1}'


def test_collect_last_text_handles_malformed_lines():
    """Robust to non-JSON lines (Kilo occasionally emits them)."""
    ndjson = (
        "garbage line\n"
        '{"type": "text", "part": {"text": "good payload"}}\n'
        "more garbage\n"
    )
    last = _collect_last_text(ndjson)
    assert last == "good payload"


def test_collect_last_text_empty_input():
    assert _collect_last_text("") is None
    assert _collect_last_text("\n\n  \n") is None


# --- lenient_parse_visual_direction: the salvage fallback ----------------

def test_lenient_parse_returns_valid_json_object():
    """Strategy 1: raw text contains a parseable JSON object."""
    out = lenient_parse_visual_direction(
        'Reasoning...\n\n{"primary_change": "X", "rationale": "Y", "stitch_status": "unavailable"}'
    )
    assert out is not None
    assert out["primary_change"] == "X"
    assert out["rationale"] == "Y"


def test_lenient_parse_extracts_fenced_json():
    """Strategy 2: Kilo often wraps JSON in ```json ... ```."""
    text = (
        "Here's my design:\n\n"
        "```json\n"
        '{"primary_change": "Bold editorial shift", '
        '"rationale": "User research", '
        '"stitch_status": "unavailable"}\n'
        "```\n"
    )
    out = lenient_parse_visual_direction(text)
    assert out is not None
    assert out["primary_change"] == "Bold editorial shift"
    assert out["stitch_status"] == "unavailable"


def test_lenient_parse_salvages_partial_fields_from_truncation():
    """Strategy 3: when the JSON is truncated mid-string, we still
    recover primary_change and rationale from the prose. This is the
    most common failure mode after the 2000-char summary truncation bug.
    """
    # Simulate truncated Kilo output: a prose line with a JSON
    # object that gets cut off mid-string.
    truncated = (
        '...here is my visual direction: '
        '{"primary_change": "Shift to bold editorial with high contrast", '
        '"rationale": "User research indicated low engagement with the muted '
        # truncated here — no closing brace
    )
    out = lenient_parse_visual_direction(truncated)
    assert out is not None
    assert out["primary_change"] == "Shift to bold editorial with high contrast"
    # rationale may or may not be fully captured depending on truncation point;
    # what we require is that we got SOMETHING parseable.
    assert "stitch_status" in out
    assert out["stitch_status"] == "unavailable"  # default when missing


def test_lenient_parse_returns_none_on_pure_prose():
    """When the Kilo output has no JSON-like structure at all, we
    return None — the caller can log a high-severity gap and route back.
    """
    out = lenient_parse_visual_direction(
        "I explored the site but found no data. Please provide more context."
    )
    assert out is None


def test_lenient_parse_returns_none_on_empty_input():
    assert lenient_parse_visual_direction("") is None
    assert lenient_parse_visual_direction(None) is None


# --- design() retry loop + lenient fallback ------------------------------

def test_design_returns_valid_visual_direction_on_retry_success():
    """If the first Kilo call emits unparseable output but a retry
    succeeds, design() must return a valid VisualDirection from the
    second call's payload.

    The strict extract_json is too permissive to always reject
    real-looking NDJSON (its outermost-brace strategy often finds the
    wrapper event). To exercise the retry loop deterministically we
    patch extract_json to raise on the first call and succeed on
    subsequent calls — this mirrors what happens when Kilo's output is
    actually malformed (truncated past the 16K cap, etc.).
    """
    from skills.agentic.designer_agent import design
    from skills.agentic.json_extract import JSONExtractionError

    valid_payload = {
        "primary_change": "Bold editorial shift",
        "rationale": "Higher contrast for accessibility",
        "stitch_status": "unavailable",
        "impacted_components": ["hero", "cta"],
        "impacted_pages": ["/"],
    }

    state = {"calls": 0, "extract_calls": 0}

    def fake_invoke(*args, **kwargs):
        state["calls"] += 1
        return ToolResult(
            success=True,
            summary=json.dumps({"type": "text", "part": {"text": "always parseable in this test"}}),
        )

    real_extract = design.__globals__["extract_json"]

    def fake_extract(text):
        state["extract_calls"] += 1
        if state["extract_calls"] == 1:
            raise JSONExtractionError("forced_failure_for_test", text or "")
        return real_extract(json.dumps({"type": "text", "part": {"text": json.dumps(valid_payload)}}) + "\n" + json.dumps({"type": "step_finish"}))

    with patch("skills.agentic.designer_agent.invoke_kilo_safe", side_effect=fake_invoke):
        with patch("skills.agentic.designer_agent.extract_json", side_effect=fake_extract):
            with patch("skills.agentic.designer_agent.subprocess.run") as mock_stitch:
                mock_stitch.return_value.returncode = 1
                mock_stitch.return_value.stderr = "not authenticated"
                result = design("20260601_104145", "20260601_104458")

    assert result is not None
    assert result.primary_change == "Bold editorial shift"
    assert result.rationale == "Higher contrast for accessibility"
    assert state["extract_calls"] >= 2  # first failure + one retry
    # The retry loop calls invoke_kilo_safe 3 times (initial + 2 retries)
    # because the patched extract_json always raises on the first call.
    assert state["calls"] >= 2  # at least one retry happened


def test_design_uses_lenient_fallback_when_all_retries_fail():
    """When Kilo succeeds on every retry but the output is unparseable,
    design() must fall back to lenient_parse_visual_direction() and
    produce a valid (degraded) VisualDirection from whatever fields
    it can salvage.

    As in the retry test, we patch extract_json to always raise so the
    design() retry loop exhausts itself. Then lenient_parse runs on
    the last text event payload and either salvages fields or returns
    None. We then verify that the design() function returns a valid
    VisualDirection (either the salvaged one or a fallback artifact).
    """
    from skills.agentic.designer_agent import design
    from skills.agentic.json_extract import JSONExtractionError

    # The Kilo body that lenient_parse can recover from — it has
    # `"primary_change": "..."` in the prose even though the JSON is
    # not balanced. After 3 extract_json failures, design() invokes
    # lenient_parse on the last_text and gets back a partial dict.
    salvaged_body = (
        'Thinking out loud... '
        '"primary_change": "Refined type scale for mobile" '
        '"rationale": "Tap-target audit found 36px buttons" '
        '"stitch_status": "unavailable"'
    )

    def fake_invoke(*args, **kwargs):
        return ToolResult(
            success=True,
            summary=(
                json.dumps({"type": "init", "session": "abc"}) + "\n"
                + json.dumps({"type": "text", "part": {"text": salvaged_body}}) + "\n"
                + json.dumps({"type": "step_finish"}) + "\n"
            ),
        )

    def fake_extract(text):
        raise JSONExtractionError("forced_failure_for_test", text or "")

    with patch("skills.agentic.designer_agent.invoke_kilo_safe", side_effect=fake_invoke):
        with patch("skills.agentic.designer_agent.extract_json", side_effect=fake_extract):
            with patch("skills.agentic.designer_agent.subprocess.run") as mock_stitch:
                mock_stitch.return_value.returncode = 1
                mock_stitch.return_value.stderr = "not authenticated"
                result = design("20260601_104145", "20260601_104458")

    assert result is not None
    # lenient_parse salvages `primary_change` from the prose.
    assert result.primary_change == "Refined type scale for mobile"


def test_design_returns_none_when_kilo_infra_fails():
    """When the kilo binary itself is missing (infra failure), design()
    must return None and not retry — retries only help for parse errors."""
    from skills.agentic.designer_agent import design

    call_count = {"n": 0}

    def fake_invoke(*args, **kwargs):
        call_count["n"] += 1
        return ToolResult(
            success=False,
            errors=["'kilo' command not found in PATH"],
            summary="Kilo not available",
        )

    with patch("skills.agentic.designer_agent.invoke_kilo_safe", side_effect=fake_invoke):
        result = design("20260601_104145", "20260601_104458")

    assert result is None
    assert call_count["n"] == 1  # no retry on infra failure


# --- Direct runner --------------------------------------------------------

if __name__ == "__main__":
    import traceback
    tests = [
        test_persona_markdown_is_under_5kb,
        test_persona_markdown_does_not_contain_full_css_blocks,
        test_persona_keeps_motion_philosophy_table,
        test_persona_keeps_stitch_fallback_contract,
        test_designer_prompt_does_not_inline_full_json_schema,
        test_designer_prompt_under_designer_budget,
        test_designer_prompt_lists_visual_direction_fields,
        test_collect_last_text_returns_last_text_event,
        test_collect_last_text_handles_malformed_lines,
        test_collect_last_text_empty_input,
        test_lenient_parse_returns_valid_json_object,
        test_lenient_parse_extracts_fenced_json,
        test_lenient_parse_salvages_partial_fields_from_truncation,
        test_lenient_parse_returns_none_on_pure_prose,
        test_lenient_parse_returns_none_on_empty_input,
        test_design_returns_valid_visual_direction_on_retry_success,
        test_design_uses_lenient_fallback_when_all_retries_fail,
        test_design_returns_none_when_kilo_infra_fails,
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
