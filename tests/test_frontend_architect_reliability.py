"""
test_frontend_architect_reliability.py

Tests for the frontend_architect persona's reliability improvements:
- One-shot retry on BuildManifest Pydantic-validation failure.
- Lenient parse (unknown fields stripped).
- _try_validate_manifest / _validation_error_for helpers.
- Prompt includes the OUTPUT-ONLY / JSON-skeleton instructions.
- Prompt stays under the 40K prompt-size refusal threshold even with
  every upstream artifact populated.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from models.site_schemas import (
    APIContracts,
    BuildManifest,
    ContentRecommendation,
    DataContracts,
    DeploySpec,
    SiteArchitecture,
    SiteUnderstanding,
    ToneOfVoice,
    VisualDirection,
)
from skills.agentic.frontend_architect import (
    _try_validate_manifest,
    _validation_error_for,
    build_frontend_prompt,
    design_frontend,
)


# --- Fixtures -------------------------------------------------------------

def _site():
    return SiteUnderstanding(
        url="https://example.com",
        platform="wix",
        platform_confidence=0.9,
        site_name="example",
        total_pages_discovered=3,
        pages=[],
        global_assets={},
        contact_info={},
        navigation_structure=[],
        estimated_fidelity=0.7,
    )


def _arch():
    return SiteArchitecture(source_url="https://example.com")


def _rec():
    return ContentRecommendation(
        source_url="https://example.com",
        site_name="example",
        overall_content_strategy="Direct",
        chosen_variant="A",
        variants=[],
        final_rationale="A",
        tone_of_voice=ToneOfVoice(),
    )


def _vd():
    return VisualDirection(primary_change="x", rationale="y", stitch_status="unavailable")


def _data():
    return DataContracts(migration_id="m1", site_slug="example", contracts=[])


def _api():
    return APIContracts(migration_id="m1", site_slug="example", endpoints=[])


def _deploy():
    return DeploySpec(migration_id="m1", site_slug="example", platform="fly")


# --- Helper-level tests ---------------------------------------------------

def test_try_validate_manifest_accepts_valid_dict():
    ok = _try_validate_manifest(json.dumps({"output_dir": "sites/example/", "overall_quality_score": 80}))
    assert ok is not None
    assert ok.output_dir == "sites/example/"
    assert ok.overall_quality_score == 80


def test_try_validate_manifest_strips_unknown_fields():
    """The LLM sometimes adds commentary fields. They must be silently
    dropped, not raise."""
    payload = {
        "output_dir": "sites/example/",
        "overall_quality_score": 80,
        "commentary": "This was a great build",
        "narrative_summary": "lots of prose the LLM invented",
    }
    ok = _try_validate_manifest(json.dumps(payload))
    assert ok is not None
    assert not hasattr(ok, "commentary")


def test_try_validate_manifest_rejects_garbage_strings():
    assert _try_validate_manifest("not json at all") is None
    assert _try_validate_manifest("[1, 2, 3]") is None  # not a dict


def test_try_validate_manifest_rejects_pydantic_failures():
    # overall_quality_score must be in [0, 100] per the schema
    bad = json.dumps({"overall_quality_score": 250})
    assert _try_validate_manifest(bad) is None
    err = _validation_error_for(bad)
    assert err is not None
    assert "overall_quality_score" in err


def test_validation_error_for_returns_none_on_unparseable():
    assert _validation_error_for("not json") is None


# --- Prompt-shape tests ---------------------------------------------------

def test_prompt_mandates_output_only_json():
    prompt = build_frontend_prompt(
        _site(), _arch(), _rec(), "example",
        visual_direction=_vd(), data_contracts=_data(),
        api_contracts=_api(), deploy_spec=_deploy(),
    )
    # The OUTPUT-ONLY framing is the most important reliability lever
    # added in this round. The wording is mirrored across the persona
    # markdown and the prompt; assert both reinforce it.
    assert "Output ONLY" in prompt or "OUTPUT ONLY" in prompt
    assert "No markdown fences" in prompt or "no markdown fences" in prompt.lower()
    # The corrective-retry preamble is appended on retry, NOT on the
    # first attempt — make sure we don't ship it pre-baked.
    assert "CORRECTION (previous response failed validation)" not in prompt


def test_prompt_under_size_budget():
    """The 40K threshold is enforced by invoke_kilo_safe; ensure we
    never approach it with a realistic artifact set."""
    prompt = build_frontend_prompt(
        _site(), _arch(), _rec(), "example",
        visual_direction=_vd(), data_contracts=_data(),
        api_contracts=_api(), deploy_spec=_deploy(),
    )
    # 40K is the hard cap; 30K is a healthy working budget. The
    # frontend_architect is the largest persona, so it gets the most
    # headroom, but we still want comfortable margin.
    assert len(prompt) < 40_000, f"prompt is {len(prompt)} chars (> 40K cap)"
    assert len(prompt) < 30_000, f"prompt is {len(prompt)} chars (> 30K working budget)"


def test_prompt_includes_minimal_json_skeleton():
    prompt = build_frontend_prompt(
        _site(), _arch(), _rec(), "example",
        visual_direction=_vd(), data_contracts=_data(),
        api_contracts=_api(), deploy_spec=_deploy(),
    )
    # The minimal required-shape example anchors the LLM on which
    # fields are truly required when the schema makes everything
    # optional. Missing it is a regression.
    for needle in ["output_dir", "build_timestamp", "personas_used",
                   "overall_quality_score", "self_critique"]:
        assert needle in prompt, f"prompt missing {needle} in skeleton"


# --- End-to-end retry path ------------------------------------------------

def _valid_manifest_json() -> str:
    return json.dumps({
        "output_dir": "sites/example/",
        "build_timestamp": "2026-06-08T18:16:46-04:00",
        "personas_used": ["frontend_architect"],
        "overall_quality_score": 75,
    })


def test_design_frontend_returns_manifest_on_first_try():
    fake_json = _valid_manifest_json()
    with patch(
        "skills.agentic.frontend_architect.invoke_kilo_for_persona",
        return_value=(fake_json, None),
    ) as mock:
        manifest, slug = design_frontend(
            _site(), _arch(), _rec(), "example",
            visual_direction=_vd(), data_contracts=_data(),
            api_contracts=_api(), deploy_spec=_deploy(),
            migration_id="m1",
        )
    assert slug == "example"
    assert isinstance(manifest, BuildManifest)
    assert manifest.overall_quality_score == 75
    # First-try success: Kilo is called exactly once.
    assert mock.call_count == 1


def test_design_frontend_retries_on_validation_failure():
    """The first Kilo call returns a manifest that fails Pydantic
    (overall_quality_score=250 > 100). The second call returns a
    corrected manifest that passes. design_frontend should return the
    corrected one without logging a gap."""
    bad = json.dumps({"overall_quality_score": 250, "personas_used": ["frontend_architect"]})
    good = _valid_manifest_json()
    with patch(
        "skills.agentic.frontend_architect.invoke_kilo_for_persona",
        side_effect=[(bad, None), (good, None)],
    ) as mock:
        manifest, slug = design_frontend(
            _site(), _arch(), _rec(), "example",
            migration_id="m1",
        )
    assert slug == "example"
    assert manifest is not None
    assert manifest.overall_quality_score == 75
    # Two calls: initial + one corrective retry.
    assert mock.call_count == 2
    # The corrective prompt should explicitly carry the validation
    # error text so Kilo knows what to fix.
    corrective_prompt = mock.call_args_list[1].kwargs["prompt"]
    assert "CORRECTION" in corrective_prompt
    assert "overall_quality_score" in corrective_prompt


def test_design_frontend_aborts_after_two_failures():
    """If both attempts fail Pydantic validation, design_frontend
    returns None and the second-failure gap message is logged."""
    bad = json.dumps({"overall_quality_score": 250})
    with patch(
        "skills.agentic.frontend_architect.invoke_kilo_for_persona",
        return_value=(bad, None),
    ):
        manifest, slug = design_frontend(
            _site(), _arch(), _rec(), "example",
            migration_id="m1",
        )
    assert slug == "example"
    assert manifest is None


def test_design_frontend_returns_none_when_kilo_fails_extraction():
    """If Kilo can't even produce a parseable JSON object on the
    first try, we get None — no retry, because re-prompting with a
    'couldn't extract JSON' error would just produce the same noise."""
    with patch(
        "skills.agentic.frontend_architect.invoke_kilo_for_persona",
        return_value=(None, "garbled text"),
    ) as mock:
        manifest, slug = design_frontend(
            _site(), _arch(), _rec(), "example",
            migration_id="m1",
        )
    assert manifest is None
    assert slug == "example"
    # Extraction failure is terminal — exactly one Kilo call.
    assert mock.call_count == 1


if __name__ == "__main__":
    import traceback
    tests = [
        test_try_validate_manifest_accepts_valid_dict,
        test_try_validate_manifest_strips_unknown_fields,
        test_try_validate_manifest_rejects_garbage_strings,
        test_try_validate_manifest_rejects_pydantic_failures,
        test_validation_error_for_returns_none_on_unparseable,
        test_prompt_mandates_output_only_json,
        test_prompt_under_size_budget,
        test_prompt_includes_minimal_json_skeleton,
        test_design_frontend_returns_manifest_on_first_try,
        test_design_frontend_retries_on_validation_failure,
        test_design_frontend_aborts_after_two_failures,
        test_design_frontend_returns_none_when_kilo_fails_extraction,
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
    import sys
    sys.exit(0 if failures == 0 else 1)
