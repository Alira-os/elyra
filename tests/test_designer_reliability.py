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

from registry.prompts import (  # noqa: E402
    collect_last_text,
    build_designer_prompt,
    lenient_parse_visual_direction,
)
from memory.artifacts import (  # noqa: E402
    load_content_recommendation,
    load_site_understanding,
)
from tools.execution import ToolResult  # noqa: E402


# --- Persona markdown trim -------------------------------------------------

def test_persona_markdown_is_under_8kb():
    """The persona must be small — Kilo can hang on oversized prompts.

    14,632 bytes (original) -> 3,690 bytes (Phase 0.7) -> ~6,700 bytes
    (Phase D added Stitch + Discoverability sections). 8KB ceiling
    leaves headroom for future additions while still keeping the prompt
    well below the 16K warn threshold.
    """
    size = Path("registry/personas/ui_designer.md").stat().st_size
    assert size < 8_000, f"ui_designer.md is {size} bytes; expected <8KB (was 14.6KB)"


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
    prompt = build_designer_prompt(site, rec, "merimee", persona_text="")
    # Pydantic-generated schema markers
    for noise in ('"$defs"', '"$ref"', "additionalProperties", "anyOf", "allOf"):
        assert noise not in prompt, f"designer prompt contains schema noise: {noise}"


def test_designer_prompt_under_designer_budget():
    """The designer prompt must be well under the 14K budget.

    62,499 (original) -> 23,177 (after Phase 0.6) -> ~8,800 (Phase 0.7).
    """
    site = load_site_understanding("20260601_104145")
    rec = load_content_recommendation("20260601_104458")
    prompt = build_designer_prompt(site, rec, "merimee", persona_text="")
    assert len(prompt) < 14_000, f"designer prompt is {len(prompt)} chars; expected <14K"


def test_designer_prompt_lists_visual_direction_fields():
    """Kilo still needs to know which fields to populate — confirm the
    explicit field list survived the trim."""
    site = load_site_understanding("20260601_104145")
    rec = load_content_recommendation("20260601_104458")
    prompt = build_designer_prompt(site, rec, "merimee", persona_text="")
    for field in (
        "primary_change", "rationale", "stitch_status",
        "impacted_components", "impacted_pages",
        "color_delta", "typography_delta", "motion_delta",
        "designer_notes", "created_at",
    ):
        assert field in prompt, f"designer prompt missing field: {field}"


# --- collect_last_text: the building block of the retry loop -------------

def testcollect_last_text_returns_last_text_event():
    """Kilo emits NDJSON; we want the last 'text' event payload."""
    ndjson = (
        '{"type": "init"}\n'
        '{"type": "text", "part": {"text": "Working on it..."}}\n'
        '{"type": "text", "part": {"text": "Here is the JSON: {\\"x\\": 1}"}}\n'
        '{"type": "step_finish"}\n'
    )
    last = collect_last_text(ndjson)
    assert last == 'Here is the JSON: {"x": 1}'


def testcollect_last_text_handles_malformed_lines():
    """Robust to non-JSON lines (Kilo occasionally emits them)."""
    ndjson = (
        "garbage line\n"
        '{"type": "text", "part": {"text": "good payload"}}\n'
        "more garbage\n"
    )
    last = collect_last_text(ndjson)
    assert last == "good payload"


def testcollect_last_text_empty_input():
    assert collect_last_text("") is None
    assert collect_last_text("\n\n  \n") is None


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
