"""
Tests for the backend_architect persona reliability improvements.

Covers:
  - lenient_parse_api_contracts: tolerates common LLM schema drift
  - build_backend_prompt: identity fields, strict-format reinforcement,
    static-site default answer baked into the prompt
  - design_api_contracts: retry-then-empty-fallback behavior when Kilo
    fails entirely (so static sites never get stuck routing back)
  - _empty_contracts: the canonical empty artifact is always valid

Run:
    python -m pytest tests/test_backend_architect_reliability.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --- Lenient parse: schema drift tolerance --------------------------------

def test_lenient_parse_handles_empty_static_site():
    """The most common case: Kilo returns endpoints: [], base_url: null."""
    from skills.agentic.backend_architect import lenient_parse_api_contracts
    data = {
        "migration_id": "m1",
        "site_slug": "example",
        "base_url": None,
        "auth_strategy": None,
        "endpoints": [],
        "business_logic_summary": "Static site, no API.",
        "reasoning_trace": ["Wix static site."],
        "produced_at": "2026-06-08T18:00:00",
        "produced_by": "backend_architect",
    }
    c = lenient_parse_api_contracts(data)
    assert c is not None
    assert c.endpoints == []
    assert c.base_url is None
    assert c.migration_id == "m1"


def test_lenient_parse_handles_endpoints_as_none():
    """LLMs often return endpoints: null instead of endpoints: []."""
    from skills.agentic.backend_architect import lenient_parse_api_contracts
    data = {
        "migration_id": "m1", "site_slug": "example",
        "endpoints": None,
    }
    c = lenient_parse_api_contracts(data)
    assert c is not None
    assert c.endpoints == []


def test_lenient_parse_strips_unknown_fields():
    """Extra top-level fields (LLM adds 'confidence', 'score', etc.) are
    silently dropped — Pydantic would otherwise reject them."""
    from skills.agentic.backend_architect import lenient_parse_api_contracts
    data = {
        "migration_id": "m1", "site_slug": "example",
        "endpoints": [],
        "confidence": 0.92,
        "score": 87,
        "model_version": "gpt-4o",
    }
    c = lenient_parse_api_contracts(data)
    assert c is not None
    assert not hasattr(c, "confidence")


def test_lenient_parse_fills_missing_identity_from_caller():
    """If the LLM drops migration_id / site_slug, fall back to the
    caller's provided values rather than failing."""
    from skills.agentic.backend_architect import lenient_parse_api_contracts
    data = {"endpoints": []}
    c = lenient_parse_api_contracts(
        data, migration_id="caller-mig", site_slug="caller-slug"
    )
    assert c is not None
    assert c.migration_id == "caller-mig"
    assert c.site_slug == "caller-slug"


def test_lenient_parse_coerces_lowercase_method():
    """Common LLM drift: method in lowercase. Coerced to uppercase."""
    from skills.agentic.backend_architect import lenient_parse_api_contracts
    data = {
        "migration_id": "m1", "site_slug": "example",
        "endpoints": [
            {"method": "get", "path": "/api/posts", "purpose": "list posts"},
            {"method": "post", "path": "/api/posts", "purpose": "create post"},
        ],
    }
    c = lenient_parse_api_contracts(data)
    assert c is not None
    assert len(c.endpoints) == 2
    assert c.endpoints[0].method == "GET"
    assert c.endpoints[1].method == "POST"


def test_lenient_parse_drops_invalid_endpoints():
    """Endpoints that can't be coerced (bad method, bad path) are
    dropped silently rather than failing the whole artifact."""
    from skills.agentic.backend_architect import lenient_parse_api_contracts
    data = {
        "migration_id": "m1", "site_slug": "example",
        "endpoints": [
            {"method": "GET", "path": "/api/good", "purpose": "ok"},
            {"method": "FETCH", "path": "/api/bad", "purpose": "bad method"},
            {"method": "GET", "path": "no-leading-slash", "purpose": "bad path"},
            {"method": "POST", "path": "/api/posts", "purpose": "create", "auth_required": "true"},
        ],
    }
    c = lenient_parse_api_contracts(data)
    assert c is not None
    assert len(c.endpoints) == 2
    assert c.endpoints[0].path == "/api/good"
    assert c.endpoints[1].path == "/api/posts"
    assert c.endpoints[1].auth_required is True


def test_lenient_parse_accepts_string_auth_required():
    """auth_required as the string "true" / "false" is coerced to bool."""
    from skills.agentic.backend_architect import lenient_parse_api_contracts
    data = {
        "migration_id": "m1", "site_slug": "example",
        "endpoints": [
            {"method": "GET", "path": "/a", "auth_required": "true"},
            {"method": "GET", "path": "/b", "auth_required": "false"},
            {"method": "GET", "path": "/c", "auth_required": 1},
        ],
    }
    c = lenient_parse_api_contracts(data)
    assert c is not None
    assert c.endpoints[0].auth_required is True
    assert c.endpoints[1].auth_required is False
    assert c.endpoints[2].auth_required is True


def test_lenient_parse_returns_none_for_non_dict():
    """If Kilo hands us a list or a string, we can't recover."""
    from skills.agentic.backend_architect import lenient_parse_api_contracts
    assert lenient_parse_api_contracts("not a dict") is None
    assert lenient_parse_api_contracts([1, 2, 3]) is None
    assert lenient_parse_api_contracts(None) is None


def test_lenient_parse_guaranteed_valid_when_caller_provides_identity():
    """Even with garbage data, if the caller provides identity fields,
    we can produce a valid empty artifact rather than None."""
    from skills.agentic.backend_architect import lenient_parse_api_contracts
    data = {"endpoints": "this should be a list, not a string"}
    c = lenient_parse_api_contracts(data, migration_id="m1", site_slug="s1")
    assert c is not None
    assert c.migration_id == "m1"
    assert c.endpoints == []


# --- Empty fallback -------------------------------------------------------

def test_empty_contracts_is_valid_and_correct():
    """The canonical empty APIContracts for a static site is a valid,
    Pydantic-valid artifact with the expected shape."""
    from skills.agentic.backend_architect import _empty_contracts
    c = _empty_contracts("m1", "example")
    assert c.migration_id == "m1"
    assert c.site_slug == "example"
    assert c.endpoints == []
    assert c.base_url is None
    assert c.auth_strategy is None
    assert c.produced_by == "backend_architect"
    assert c.produced_at


# --- Prompt builder -------------------------------------------------------

def test_backend_prompt_emphasizes_static_site_default():
    """The prompt must make the empty-list case the obvious default
    answer for static sites, not a fallback."""
    from skills.agentic.backend_architect import build_backend_prompt
    from models.site_schemas import SiteArchitecture, SiteUnderstanding
    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    prompt = build_backend_prompt(
        site, arch, migration_id="m1", site_slug="example"
    )
    assert "endpoints: []" in prompt
    assert "static" in prompt.lower()
    assert "APIContracts" in prompt
    assert "m1" in prompt
    assert "example" in prompt


def test_backend_prompt_strict_format_adds_reinforcement():
    """When strict_format=True, the prompt should include the explicit
    format reminder for the retry path."""
    from skills.agentic.backend_architect import build_backend_prompt
    from models.site_schemas import SiteArchitecture, SiteUnderstanding
    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")

    base_prompt = build_backend_prompt(
        site, arch, migration_id="m1", site_slug="example"
    )
    strict_prompt = build_backend_prompt(
        site, arch, migration_id="m1", site_slug="example", strict_format=True
    )

    assert len(strict_prompt) > len(base_prompt)
    assert "FORMAT REMINDER" in strict_prompt
    assert "Retry" in strict_prompt
    assert "FORMAT REMINDER" not in base_prompt


# --- design_api_contracts: retry + fallback behavior ----------------------

def _make_site_and_arch():
    from models.site_schemas import SiteArchitecture, SiteUnderstanding
    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    return site, arch


def test_design_api_contracts_returns_artifact_on_first_success():
    """Happy path: Kilo returns valid empty APIContracts on first try."""
    from skills.agentic.backend_architect import design_api_contracts

    good_json = json.dumps({
        "migration_id": "m1", "site_slug": "example",
        "base_url": None, "auth_strategy": None,
        "endpoints": [],
        "business_logic_summary": "static",
        "reasoning_trace": ["wix static"],
        "produced_at": "", "produced_by": "",
    })

    site, arch = _make_site_and_arch()
    with patch("skills.agentic.backend_architect.invoke_kilo_for_persona",
               return_value=(good_json, "raw text")):
        result = design_api_contracts(
            site, arch, migration_id="m1", site_slug="example"
        )
    assert result is not None
    assert result.endpoints == []
    assert result.migration_id == "m1"
    assert result.produced_by == "backend_architect"


def test_design_api_contracts_recovers_via_lenient_parse_on_drift():
    """First response has schema drift (extra field, missing identity
    fields) — lenient_parse fixes it without a retry."""
    from skills.agentic.backend_architect import design_api_contracts

    drift_json = json.dumps({
        "endpoints": [],
        "base_url": None,
        "confidence": 0.95,
        "notes_top_level": "this is not in the schema",
    })

    site, arch = _make_site_and_arch()
    with patch("skills.agentic.backend_architect.invoke_kilo_for_persona",
               return_value=(drift_json, "raw text")):
        result = design_api_contracts(
            site, arch, migration_id="m1", site_slug="example"
        )
    assert result is not None
    assert result.migration_id == "m1"
    assert result.site_slug == "example"
    assert result.endpoints == []


def test_design_api_contracts_retries_then_succeeds():
    """First response is unparseable garbage; second (retry) succeeds."""
    from skills.agentic.backend_architect import design_api_contracts

    good_json = json.dumps({
        "migration_id": "m1", "site_slug": "example",
        "endpoints": [],
        "base_url": None, "auth_strategy": None,
        "business_logic_summary": "",
        "reasoning_trace": [], "produced_at": "", "produced_by": "",
    })

    call_count = {"n": 0}

    def fake_invoke(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (None, None)
        return (good_json, "raw text")

    site, arch = _make_site_and_arch()
    with patch("skills.agentic.backend_architect.invoke_kilo_for_persona",
               side_effect=fake_invoke):
        result = design_api_contracts(
            site, arch, migration_id="m1", site_slug="example"
        )
    assert result is not None
    assert result.endpoints == []
    assert call_count["n"] == 2


def test_design_api_contracts_falls_back_to_empty_on_double_failure():
    """If both Kilo calls fail, design_api_contracts returns the
    canonical empty APIContracts (the right answer for static sites)
    rather than None."""
    from skills.agentic.backend_architect import design_api_contracts

    site, arch = _make_site_and_arch()
    with patch("skills.agentic.backend_architect.invoke_kilo_for_persona",
               return_value=(None, None)):
        result = design_api_contracts(
            site, arch, migration_id="m1", site_slug="example"
        )
    assert result is not None
    assert result.endpoints == []
    assert result.base_url is None
    assert result.migration_id == "m1"
    assert result.produced_by == "backend_architect"


def test_design_api_contracts_handles_invalid_json_string():
    """Kilo returns a non-JSON string (e.g. truncated output). Should
    retry, and on second failure fall back to empty."""
    from skills.agentic.backend_architect import design_api_contracts

    site, arch = _make_site_and_arch()
    with patch("skills.agentic.backend_architect.invoke_kilo_for_persona",
               return_value=("this is not json at all", "raw text")):
        result = design_api_contracts(
            site, arch, migration_id="m1", site_slug="example"
        )
    assert result is not None
    assert result.endpoints == []


def test_design_api_contracts_end_to_end_with_api_endpoints():
    """When the site genuinely has APIs, the persona should surface them."""
    from skills.agentic.backend_architect import design_api_contracts

    cms_json = json.dumps({
        "migration_id": "m1", "site_slug": "blog",
        "base_url": "https://api.blog.example.com",
        "auth_strategy": "JWT via Supabase",
        "endpoints": [
            {
                "method": "GET", "path": "/api/posts",
                "purpose": "list published posts",
                "auth_required": False, "notes": "",
            },
            {
                "method": "POST", "path": "/api/posts/{id}/comments",
                "purpose": "create comment",
                "auth_required": True, "notes": "rate-limited",
            },
        ],
        "business_logic_summary": "Headless CMS with authenticated comments.",
        "reasoning_trace": ["Has CMS contracts", "Has auth-gated writes"],
        "produced_at": "2026-06-08T18:00:00", "produced_by": "backend_architect",
    })

    site, arch = _make_site_and_arch()
    with patch("skills.agentic.backend_architect.invoke_kilo_for_persona",
               return_value=(cms_json, "raw text")):
        result = design_api_contracts(
            site, arch, migration_id="m1", site_slug="blog"
        )
    assert result is not None
    assert len(result.endpoints) == 2
    assert result.endpoints[0].method == "GET"
    assert result.endpoints[0].path == "/api/posts"
    assert result.endpoints[1].auth_required is True
    assert result.auth_strategy == "JWT via Supabase"


# --- Persona markdown content -------------------------------------------

def test_persona_markdown_emphasizes_empty_default():
    """The persona markdown should be tailored for APIContracts
    production, not the legacy 'guide the Builder' charter."""
    from skills.agentic.forge_common import load_persona_markdown
    md = load_persona_markdown("backend_architect")
    assert "APIContracts" in md
    assert "empty" in md.lower()
    assert "Anti-Patterns" in md or "anti-pattern" in md.lower()


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in globals().items() if k.startswith("test_")]
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
