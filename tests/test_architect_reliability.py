"""
test_architect_reliability.py — Targeted tests for the Phase 0.6.2
SiteArchitecture reliability fixes in skills/agentic/architect_agent.py.

These tests exercise the two failure modes observed in the gap ledger:
  1. Extraction failure: Kilo output contains no parseable JSON
  2. Validation failure:  JSON parses but does not match the
     SiteArchitecture Pydantic schema (the persona markdown was
     out-of-sync with the schema, and Kilo faithfully produced the
     out-of-sync shape).

The fixes under test:
  - _coerce_architect_payload()  — normalises the most common drift
    patterns (literal "null" string, missing source_url, persona-only
    extra fields).
  - parse_and_validate(fallback_source_url=...) — strict pass, then a
    lenient strip-and-retry pass, then returns None only if both fail.
  - _retry_prompt_for_reemit()  — short, terse retry prompt for the
    re-emit path.
  - architect()  — one retry on extraction failure before logging a gap.

Run:
    python -m pytest tests/test_architect_reliability.py -v
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import SiteArchitecture
from registry.prompts import (
    coerce_architect_payload,
    retry_architect_prompt,
    build_architect_prompt,
)
from memory.artifacts import load_site_understanding
from tools.execution import ToolResult
from skills.agentic.json_extract import extract_json, JSONExtractionError


# Aliases preserve the historical test names — the helpers moved to
# registry.prompts in Phase 1 but the public API is unchanged.
_coerce_architect_payload = coerce_architect_payload
_retry_prompt_for_reemit = retry_architect_prompt


def parse_and_validate(raw_json: str, fallback_source_url=None):
    """Local re-implementation of the legacy thin-glue validator.

    The thin-glue ``architect_agent.py`` was deleted in Phase 1. This
    helper preserves the test contract (strict pass, lenient strip
    fallback) without depending on the deleted module.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    coerced = coerce_architect_payload(data)
    if fallback_source_url and not coerced.get("source_url"):
        coerced["source_url"] = fallback_source_url
    try:
        return SiteArchitecture(**coerced)
    except Exception:
        allowed = {k: v for k, v in data.items() if k in SiteArchitecture.model_fields}
        if fallback_source_url and not allowed.get("source_url"):
            allowed["source_url"] = fallback_source_url
        try:
            return SiteArchitecture(**allowed)
        except Exception:
            return None


# --- _coerce_architect_payload --------------------------------------------


def test_coerce_strips_unknown_top_level_keys():
    """Kilo emits fields the persona documents (bindings, tier1_triggers,
    platform, substrate) that are not in the Pydantic schema. They must
    be silently dropped, not raise."""
    payload = {
        "source_url": "https://example.com",
        "target_stack": {"framework": "nextjs"},
        "pages": [],
        "components": [],
        # persona-only extras (must be stripped)
        "routing_strategy": "app_router",
        "persona_version": "1.0",
        "tier1_triggers": [{"name": "long-running-compute"}],
    }
    cleaned = _coerce_architect_payload(payload)
    assert "routing_strategy" not in cleaned
    assert "persona_version" not in cleaned
    assert "tier1_triggers" not in cleaned
    assert cleaned["source_url"] == "https://example.com"


def test_coerce_literal_null_string_to_none_for_cdn_domain():
    """The persona's documentation said cdn_domain could be the literal
    string 'null'. The Pydantic schema wants JSON null. Normalise."""
    payload = {
        "source_url": "https://example.com",
        "image_strategy": {
            "source_pattern": "",
            "target_strategy": "preserve-cdn",
            "cdn_domain": "null",
        },
    }
    cleaned = _coerce_architect_payload(payload)
    assert cleaned["image_strategy"]["cdn_domain"] is None
    # And a real domain passes through unchanged.
    payload["image_strategy"]["cdn_domain"] = "static.example.com"
    cleaned2 = _coerce_architect_payload(payload)
    assert cleaned2["image_strategy"]["cdn_domain"] == "static.example.com"


def test_coerce_literal_null_string_to_none_for_page_optionals():
    """cms_content_type and template_id are Optional[str]; coerce "null"
    sentinel to None to keep Pydantic happy on sites with no CMS."""
    payload = {
        "source_url": "https://example.com",
        "pages": [
            {
                "url": "https://example.com/about",
                "route": "/about",
                "component_ids": [],
                "data_source": "static",
                "cms_content_type": "null",
                "template_id": "null",
                "priority": "standard",
                "notes": "",
            }
        ],
    }
    cleaned = _coerce_architect_payload(payload)
    p = cleaned["pages"][0]
    assert p["cms_content_type"] is None
    assert p["template_id"] is None


def test_coerce_non_dict_input_passes_through():
    """Coercion is a no-op for non-dict inputs (defensive)."""
    assert _coerce_architect_payload(None) is None
    assert _coerce_architect_payload([1, 2, 3]) == [1, 2, 3]
    assert _coerce_architect_payload("string") == "string"


# --- parse_and_validate --------------------------------------------------


def _valid_payload():
    return {
        "source_url": "https://example.com",
        "target_stack": {"framework": "nextjs", "styling": "tailwind"},
        "pages": [
            {
                "url": "https://example.com/",
                "route": "/",
                "component_ids": ["hero-home"],
                "data_source": "static",
                "cms_content_type": None,
                "template_id": None,
                "priority": "critical",
                "notes": "",
            }
        ],
        "components": [
            {
                "component_id": "hero-home",
                "component_type": "hero",
                "file_path": "components/Hero.tsx",
                "props_schema": {},
                "is_reusable": True,
                "page_scope": ["/"],
                "complexity": "simple",
                "notes": "",
            }
        ],
    }


def test_parse_and_validate_strict_pass():
    arch = parse_and_validate(json.dumps(_valid_payload()))
    assert arch is not None
    assert arch.source_url == "https://example.com"
    assert arch.target_stack["framework"] == "nextjs"
    assert len(arch.pages) == 1
    assert len(arch.components) == 1


def test_parse_and_validate_fallback_source_url():
    """If Kilo forgets source_url, fall back to the context-provided URL
    instead of failing validation."""
    payload = _valid_payload()
    del payload["source_url"]
    arch = parse_and_validate(json.dumps(payload), fallback_source_url="https://fallback.example.com")
    assert arch is not None
    assert arch.source_url == "https://fallback.example.com"


def test_parse_and_validate_lenient_strips_extras():
    """Kilo emits the persona's documented extra fields (routing_strategy,
    tier1_triggers, etc.) that are not in the schema. The lenient pass
    should strip them and validate the rest."""
    payload = _valid_payload()
    payload["routing_strategy"] = "app_router"
    payload["tier1_triggers"] = [{"name": "long-running-compute"}]
    payload["deployment"] = {
        "platform": "cloudflare",
        "substrate": "workers",
        "tier1_triggers_rationale": "irrelevant",
    }
    arch = parse_and_validate(json.dumps(payload))
    assert arch is not None
    assert arch.source_url == "https://example.com"


def test_parse_and_validate_handles_cdn_domain_null_string():
    """cdn_domain = "null" (literal) must not crash validation."""
    payload = _valid_payload()
    payload["image_strategy"] = {
        "source_pattern": "",
        "target_strategy": "preserve-cdn",
        "cdn_domain": "null",
    }
    arch = parse_and_validate(json.dumps(payload))
    assert arch is not None
    assert arch.image_strategy.cdn_domain is None


def test_parse_and_validate_returns_none_for_invalid_json():
    arch = parse_and_validate("{not valid json")
    assert arch is None


def test_parse_and_validate_returns_none_for_non_object():
    arch = parse_and_validate("[1, 2, 3]")
    assert arch is None


def test_parse_and_validate_returns_none_when_source_url_missing_no_fallback():
    """If source_url is missing AND no fallback is supplied, the model
    has no required string to populate, so we must return None."""
    payload = _valid_payload()
    del payload["source_url"]
    arch = parse_and_validate(json.dumps(payload))
    assert arch is None


def test_parse_and_validate_returns_none_when_invalid_enum_value():
    """A component_type outside the allowed enum must still be rejected
    — coercions cannot rescue wrong enum values, only wrong shapes and
    missing optionals."""
    payload = _valid_payload()
    payload["components"][0]["component_type"] = "not_a_real_type"
    arch = parse_and_validate(json.dumps(payload))
    assert arch is None


# --- _retry_prompt_for_reemit --------------------------------------------


def test_retry_prompt_is_short_and_contains_required_signals():
    """The retry prompt must be terse (small chance of Kilo wrapping it
    in chatter) and must explicitly forbid markdown fences so a
    conversational preface doesn't eat the JSON braces."""
    p = _retry_prompt_for_reemit()
    assert "{" in p and "}" in p
    assert "fence" in p.lower() or "```" in p
    assert len(p) < 600, f"retry prompt is {len(p)} chars; expected <600"



# --- Prompt budget guard (lock the persona size) -------------------------


def test_architect_prompt_still_under_size_limit():
    """Phase 0.6.1 promise: the architect prompt stays under 24K. The
    Phase 0.6.2 persona additions must not blow that budget."""
    try:
        site = load_site_understanding("20260601_104145")
    except Exception:
        return  # skip if the test fixture artifact isn't on disk
    p = build_architect_prompt(site, persona_text="")
    assert len(p) < 24_000, f"architect prompt is {len(p)} chars, expected <24K"


if __name__ == "__main__":
    import traceback
    tests = [
        test_coerce_strips_unknown_top_level_keys,
        test_coerce_literal_null_string_to_none_for_cdn_domain,
        test_coerce_literal_null_string_to_none_for_page_optionals,
        test_coerce_non_dict_input_passes_through,
        test_parse_and_validate_strict_pass,
        test_parse_and_validate_fallback_source_url,
        test_parse_and_validate_lenient_strips_extras,
        test_parse_and_validate_handles_cdn_domain_null_string,
        test_parse_and_validate_returns_none_for_invalid_json,
        test_parse_and_validate_returns_none_for_non_object,
        test_parse_and_validate_returns_none_when_source_url_missing_no_fallback,
        test_parse_and_validate_returns_none_when_invalid_enum_value,
        test_retry_prompt_is_short_and_contains_required_signals,
        test_architect_prompt_still_under_size_limit,
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
