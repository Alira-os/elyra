"""
Unit tests for the Phase 1.1 integration_coordinator hardening.

Covers:
  - Lenient Pydantic parse: strips unknown fields, auto-fills missing
    migration_id / site_slug from function args, defaults null list
    fields to [].
  - Single retry on Kilo output-extraction failure (uses a tightened
    JSON-only retry prompt).
  - Deterministic fallback IntegrationStatus when BOTH Kilo attempts
    fail: artifact is still returned (not None), has
    cross_layer_checks_run=["requires_kilo_re_invocation"], and sets
    final_build_manifest_id to the input build_id so the build can
    complete.
  - The persona markdown's new "How to perform cross-layer checks"
    section mentions the key artifacts (DataContracts, APIContracts,
    DeploySpec) and the JSON-only retry phrase.
  - The build_integration_prompt now includes the migration_id and
    site_slug "REQUIRED context fields" header.

Run:
    python -m pytest tests/test_integration_coordinator_hardening.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --- Lenient parse -------------------------------------------------------


def test_lenient_parse_strips_unknown_fields():
    """Kilo often adds e.g. 'recommendations' or 'notes' to the JSON.
    The lenient parser must drop them silently rather than raising."""
    from skills.agentic.integration_coordinator import (
        _lenient_parse_integration_status,
    )
    from models.site_schemas import IntegrationStatus

    data = {
        "migration_id": "m1",
        "site_slug": "example",
        "cross_layer_checks_run": ["api_path_consistent_with_frontend_routes"],
        "issues_found": [],
        "resolutions": [],
        "final_build_manifest_id": "20260608_180000",
        "recommendations": ["a totally made-up field"],   # not in schema
        "notes": "extra commentary",                       # not in schema
    }
    status = _lenient_parse_integration_status(
        data, fallback_migration_id="", fallback_site_slug="",
    )
    assert isinstance(status, IntegrationStatus)
    assert status.migration_id == "m1"
    assert status.site_slug == "example"
    assert status.final_build_manifest_id == "20260608_180000"


def test_lenient_parse_injects_blank_migration_id_and_site_slug():
    """If Kilo leaves migration_id / site_slug blank, the lenient parser
    fills them from the function args (which the orchestrator supplies
    from MigrationState)."""
    from skills.agentic.integration_coordinator import (
        _lenient_parse_integration_status,
    )

    data = {
        "migration_id": "",
        "site_slug": "",
        "cross_layer_checks_run": ["api_path_consistent_with_frontend_routes"],
        "issues_found": [],
        "resolutions": [],
    }
    status = _lenient_parse_integration_status(
        data,
        fallback_migration_id="fb-mig-id",
        fallback_site_slug="fb-slug",
    )
    assert status is not None
    assert status.migration_id == "fb-mig-id"
    assert status.site_slug == "fb-slug"


def test_lenient_parse_handles_null_list_fields():
    """If Kilo emits null for a List[str] field, default to [] so the
    schema accepts it."""
    from skills.agentic.integration_coordinator import (
        _lenient_parse_integration_status,
    )

    data = {
        "migration_id": "m1",
        "site_slug": "x",
        "cross_layer_checks_run": None,
        "issues_found": None,
        "resolutions": None,
        "reasoning_trace": None,
    }
    status = _lenient_parse_integration_status(
        data, fallback_migration_id="", fallback_site_slug="",
    )
    assert status is not None
    assert status.cross_layer_checks_run == []
    assert status.issues_found == []
    assert status.resolutions == []
    assert status.reasoning_trace == []


def test_lenient_parse_returns_none_for_non_dict():
    from skills.agentic.integration_coordinator import (
        _lenient_parse_integration_status,
    )
    assert _lenient_parse_integration_status(
        "not a dict", fallback_migration_id="", fallback_site_slug="",
    ) is None
    assert _lenient_parse_integration_status(
        None, fallback_migration_id="", fallback_site_slug="",
    ) is None


# --- Deterministic fallback ----------------------------------------------


def test_fallback_integration_status_is_well_formed():
    """The fallback must be a valid IntegrationStatus with no invented
    issues, the build_id promoted to final_build_manifest_id, and an
    explicit 'requires_kilo_re_invocation' marker."""
    from skills.agentic.integration_coordinator import (
        _build_fallback_integration_status,
    )
    from models.site_schemas import IntegrationStatus

    fb = _build_fallback_integration_status(
        migration_id="mig-123",
        site_slug="my-site",
        build_id="20260608_180000",
        reason="kilo_invoke_failed",
    )
    assert isinstance(fb, IntegrationStatus)
    assert fb.migration_id == "mig-123"
    assert fb.site_slug == "my-site"
    assert fb.final_build_manifest_id == "20260608_180000"
    assert fb.cross_layer_checks_run == ["requires_kilo_re_invocation"]
    assert fb.issues_found == []
    assert fb.resolutions == []
    assert fb.produced_by == "integration_coordinator_fallback"


def test_fallback_handles_blank_inputs():
    """Blank migration_id/site_slug should not crash the fallback."""
    from skills.agentic.integration_coordinator import (
        _build_fallback_integration_status,
    )
    fb = _build_fallback_integration_status(
        migration_id="", site_slug="", build_id="", reason="x",
    )
    assert fb.migration_id == "unknown"
    assert fb.site_slug == "unknown"
    assert fb.final_build_manifest_id is None  # no build_id → None


# --- coordinate_integration: retry + fallback paths ----------------------


def _make_site_arch():
    from models.site_schemas import SiteUnderstanding, SiteArchitecture
    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    return site, arch


def test_coordinate_integration_retries_on_extraction_failure(monkeypatch, tmp_path):
    """First Kilo call: extraction fails (returns None).
    Retry Kilo call: succeeds with a valid IntegrationStatus JSON.
    Expected: the retry's JSON is parsed, no fallback, no gap for retry path."""
    from skills.agentic import integration_coordinator as ic

    call_log: list[str] = []
    good_json = json.dumps({
        "migration_id": "mig-1",
        "site_slug": "example",
        "cross_layer_checks_run": ["api_path_consistent_with_frontend_routes"],
        "issues_found": [],
        "resolutions": [],
        "final_build_manifest_id": "20260608_180000",
    })

    def fake_invoke(persona, prompt, context, migration_id, timeout_s):
        call_log.append(context.get("retry", False) and "retry" or "primary")
        if len(call_log) == 1:
            return None, None  # extraction failure
        return good_json, None  # retry succeeds

    # Use a tmp memory dir so the test doesn't write to the real one.
    monkeypatch.setattr(ic, "INTEGRATION_STATUS_DIR", tmp_path / "integration_status")
    monkeypatch.setattr(ic, "invoke_kilo_for_persona", fake_invoke)

    site, arch = _make_site_arch()
    status = ic.coordinate_integration(
        site, arch,
        migration_id="mig-1", site_slug="example",
        build_id="20260608_180000",
    )
    assert status is not None
    assert status.migration_id == "mig-1"
    assert status.final_build_manifest_id == "20260608_180000"
    assert call_log == ["primary", "retry"]


def test_coordinate_integration_falls_back_when_both_kilo_calls_fail(monkeypatch, tmp_path):
    """Both Kilo calls return None (extraction failure).
    Expected: deterministic fallback IntegrationStatus is returned
    (not None), with the marker check name and the build_id promoted."""
    from skills.agentic import integration_coordinator as ic

    def fake_invoke(persona, prompt, context, migration_id, timeout_s):
        return None, None  # always fails

    monkeypatch.setattr(ic, "INTEGRATION_STATUS_DIR", tmp_path / "integration_status")
    monkeypatch.setattr(ic, "invoke_kilo_for_persona", fake_invoke)
    # Suppress gap logging side effects (no migration row in test DB).
    monkeypatch.setattr(ic, "make_failed_invocation_gap", lambda **kw: None)

    site, arch = _make_site_arch()
    status = ic.coordinate_integration(
        site, arch,
        migration_id="mig-1", site_slug="example",
        build_id="20260608_180000",
    )
    assert status is not None, "fallback must always return a non-None IntegrationStatus"
    assert status.migration_id == "mig-1"
    assert status.site_slug == "example"
    assert status.final_build_manifest_id == "20260608_180000"
    assert "requires_kilo_re_invocation" in status.cross_layer_checks_run
    assert status.issues_found == []   # no invented issues
    assert status.produced_by == "integration_coordinator_fallback"


def test_coordinate_integration_falls_back_on_pydantic_validation_failure(monkeypatch, tmp_path):
    """Kilo returns a JSON object that fails Pydantic validation even
    after lenient parse (e.g. one of the list fields contains a
    non-string that bypasses the lenient strip).
    Expected: deterministic fallback is returned."""
    from skills.agentic import integration_coordinator as ic

    def fake_invoke(persona, prompt, context, migration_id, timeout_s):
        # Return a top-level non-dict so _lenient_parse_integration_status
        # returns None and we hit the fallback path.
        return json.dumps(["not", "a", "dict"]), None

    monkeypatch.setattr(ic, "INTEGRATION_STATUS_DIR", tmp_path / "integration_status")
    monkeypatch.setattr(ic, "invoke_kilo_for_persona", fake_invoke)
    monkeypatch.setattr(ic, "make_failed_invocation_gap", lambda **kw: None)

    site, arch = _make_site_arch()
    status = ic.coordinate_integration(
        site, arch,
        migration_id="mig-1", site_slug="example",
        build_id="20260608_180000",
    )
    assert status is not None
    assert "requires_kilo_re_invocation" in status.cross_layer_checks_run
    assert status.final_build_manifest_id == "20260608_180000"


def test_coordinate_integration_handles_valid_response_with_unknown_fields(monkeypatch, tmp_path):
    """Kilo returns a valid IntegrationStatus plus an invented
    'recommendations' field. The lenient parser should drop it and
    the orchestrator should still get a clean IntegrationStatus."""
    from skills.agentic import integration_coordinator as ic

    def fake_invoke(persona, prompt, context, migration_id, timeout_s):
        return json.dumps({
            "migration_id": "mig-1",
            "site_slug": "example",
            "cross_layer_checks_run": ["api_path_consistent_with_frontend_routes"],
            "issues_found": ["endpoint /api/posts unreachable"],
            "resolutions": ["renamed to /api/blog-posts"],
            "final_build_manifest_id": "20260608_180000",
            "recommendations": ["some other LLM drift"],  # not in schema
        }), None

    monkeypatch.setattr(ic, "INTEGRATION_STATUS_DIR", tmp_path / "integration_status")
    monkeypatch.setattr(ic, "invoke_kilo_for_persona", fake_invoke)

    site, arch = _make_site_arch()
    status = ic.coordinate_integration(
        site, arch,
        migration_id="mig-1", site_slug="example",
        build_id="20260608_180000",
    )
    assert status is not None
    assert status.issues_found == ["endpoint /api/posts unreachable"]
    assert status.resolutions == ["renamed to /api/blog-posts"]


# --- Prompt + markdown content checks ------------------------------------


def test_prompt_includes_migration_id_and_site_slug_explicitly():
    """The Task section must tell Kilo what to put in migration_id and
    site_slug (a known Phase 0 gap: Kilo invents these)."""
    from skills.agentic.integration_coordinator import build_integration_prompt
    site, arch = _make_site_arch()
    prompt = build_integration_prompt(
        site, arch,
        migration_id="MIG-ABC", site_slug="acme-co", build_id="B1",
    )
    assert "MIG-ABC" in prompt
    assert "acme-co" in prompt
    assert "REQUIRED context fields" in prompt


def test_persona_markdown_documents_cross_layer_check_strategy():
    """The persona markdown's new 'How to perform cross-layer checks'
    section must tell Kilo to compare JSONs, and the
    'requires_visual_inspection' anti-pattern must be present so Kilo
    doesn't fake-pass checks it cannot verify."""
    md_path = Path("registry/personas/integration_coordinator.md")
    md = md_path.read_text(encoding="utf-8")
    assert "How to perform cross-layer checks" in md
    assert "JSON" in md
    assert "requires_visual_inspection" in md
    assert "migration_id" in md and "site_slug" in md
    # The example output JSON must use the new REQUIRED context header
    # convention so Kilo follows it.
    assert "USE THE MIGRATION_ID FROM THE TASK HEADER" in md
    assert "USE THE SITE_SLUG FROM THE TASK HEADER" in md
    # Anti-pattern: no fake defaults
    assert "No fake defaults" in md
    # Anti-pattern: no invented issues
    assert "No invented issues" in md


if __name__ == "__main__":
    import traceback
    tests = [
        test_lenient_parse_strips_unknown_fields,
        test_lenient_parse_injects_blank_migration_id_and_site_slug,
        test_lenient_parse_handles_null_list_fields,
        test_lenient_parse_returns_none_for_non_dict,
        test_fallback_integration_status_is_well_formed,
        test_fallback_handles_blank_inputs,
        test_coordinate_integration_retries_on_extraction_failure,
        test_coordinate_integration_falls_back_when_both_kilo_calls_fail,
        test_coordinate_integration_falls_back_on_pydantic_validation_failure,
        test_coordinate_integration_handles_valid_response_with_unknown_fields,
        test_prompt_includes_migration_id_and_site_slug_explicitly,
        test_persona_markdown_documents_cross_layer_check_strategy,
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
