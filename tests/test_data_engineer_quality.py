"""
Tests for the data_engineer persona's quality-engineering fixes.

Covers:
  - The prompt builder's new explicit `deploy_spec is None` branch
    (so Kilo no longer sees a bare `{}` for DeploySpec).
  - The `_lenient_load_data_contracts` helper's tolerance for:
      * Unknown top-level keys (Kilo adds `id`, `timestamp`, etc.)
      * Unknown per-contract keys
      * Per-field `required` emitted as a boolean (not string)
      * Missing `required` / `notes` keys
  - End-to-end: a fake Kilo response with shape errors is recovered
    without invoking the repair Kilo call (lenient parse alone is
    enough).
  - End-to-end: a fake Kilo response that still fails the lenient
    parse triggers exactly ONE repair call.
  - Backwards-compat: the public function signature is unchanged.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --- Prompt builder: deploy_spec=None branch ----------------------------

def test_prompt_handles_missing_deploy_spec_explicitly():
    """When DevOps has not run yet, the prompt must NOT show a bare `{}`
    for the DeploySpec — it must tell Kilo to default to a static kind
    and forbid introducing a `database` contract without evidence."""
    from skills.agentic.data_engineer import build_data_engineer_prompt
    from models.site_schemas import SiteArchitecture, SiteUnderstanding

    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    prompt = build_data_engineer_prompt(site, arch, deploy_spec=None)
    assert "NOT YET AVAILABLE" in prompt
    assert "static" in prompt
    # Must NOT contain a bare {} placeholder that Kilo could misread.
    assert "## Input DeploySpec (from DevOps Engineer — early constraint)\n{}" not in prompt


def test_prompt_includes_explicit_required_string_rule():
    """The prompt must remind Kilo that `required` is a STRING, not a
    boolean — this is the most common validation error path."""
    from skills.agentic.data_engineer import build_data_engineer_prompt
    from models.site_schemas import SiteArchitecture, SiteUnderstanding

    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    prompt = build_data_engineer_prompt(site, arch, deploy_spec=None)
    assert "STRING" in prompt
    assert "true" in prompt and "false" in prompt
    assert "NOT a boolean" in prompt


# --- Lenient parser ----------------------------------------------------

def test_lenient_load_drops_unknown_top_level_keys():
    from skills.agentic.data_engineer import _lenient_load_data_contracts
    data = {
        "migration_id": "m1",
        "site_slug": "example",
        "contracts": [],
        "data_architecture_summary": "x",
        "id": "abc-123",
        "timestamp": "2026-06-08T10:00:00Z",
        "_meta": {"model": "kilo"},
    }
    cs = _lenient_load_data_contracts(data)
    assert cs.migration_id == "m1"
    assert not hasattr(cs, "id")


def test_lenient_load_drops_unknown_per_contract_keys():
    from skills.agentic.data_engineer import _lenient_load_data_contracts
    data = {
        "migration_id": "m1",
        "site_slug": "example",
        "contracts": [
            {
                "name": "BlogPost",
                "kind": "static",
                "fields": [],
                "relationships": [],
                "cms_sync": None,
                "notes": "",
                "description": "unused extra",
                "color": "blue",
            }
        ],
    }
    cs = _lenient_load_data_contracts(data)
    assert cs.contracts[0].name == "BlogPost"


def test_lenient_load_normalises_boolean_required_to_string():
    from skills.agentic.data_engineer import _lenient_load_data_contracts
    data = {
        "migration_id": "m1",
        "site_slug": "example",
        "contracts": [
            {
                "name": "BlogPost",
                "kind": "static",
                "fields": [
                    {"name": "title", "type": "string", "required": True,  "notes": ""},
                    {"name": "body",  "type": "string", "required": False, "notes": ""},
                ],
                "relationships": [],
                "cms_sync": None,
                "notes": "",
            }
        ],
    }
    cs = _lenient_load_data_contracts(data)
    fields = {f["name"]: f for f in cs.contracts[0].fields}
    assert fields["title"]["required"] == "true"
    assert fields["body"]["required"] == "false"


def test_lenient_load_fills_missing_required_and_notes():
    from skills.agentic.data_engineer import _lenient_load_data_contracts
    data = {
        "migration_id": "m1",
        "site_slug": "example",
        "contracts": [
            {
                "name": "BlogPost",
                "kind": "static",
                "fields": [
                    {"name": "title", "type": "string"},
                ],
            }
        ],
    }
    cs = _lenient_load_data_contracts(data)
    f = cs.contracts[0].fields[0]
    assert f["required"] == "false"
    assert f["notes"] == ""


def test_lenient_load_skips_malformed_contracts_silently():
    from skills.agentic.data_engineer import _lenient_load_data_contracts
    data = {
        "migration_id": "m1",
        "site_slug": "example",
        "contracts": [
            "garbage",
            {"name": "OK", "kind": "static", "fields": []},
        ],
    }
    cs = _lenient_load_data_contracts(data)
    assert len(cs.contracts) == 1
    assert cs.contracts[0].name == "OK"


# --- End-to-end recovery via fake Kilo --------------------------------

class _FakeKiloResult:
    def __init__(self, text):
        self.success = True
        self.summary = text
        self.errors = []


def test_design_recovers_leniently_without_repair_call(monkeypatch):
    """If the first Kilo response is parseable as JSON but has
    boolean `required` fields and an extra `id` key, the lenient parse
    alone should fix it — no repair call to Kilo."""
    from skills.agentic import data_engineer as de
    from skills.agentic import forge_common
    from models.site_schemas import SiteArchitecture, SiteUnderstanding

    bad_but_recoverable = {
        "migration_id": "",
        "site_slug": "",
        "contracts": [
            {
                "name": "BlogPost",
                "kind": "static",
                "fields": [
                    {"name": "title", "type": "string", "required": True, "notes": ""},
                ],
                "id": "extraneous",
            }
        ],
        "data_architecture_summary": "x",
    }

    calls = {"n": 0, "prompts": []}

    def fake_invoke_kilo_safe(prompt, context, working_dir, persona, timeout, on_timeout=None):
        calls["n"] += 1
        calls["prompts"].append(prompt)
        return _FakeKiloResult(json.dumps(bad_but_recoverable))

    # Patch the symbol bound into forge_common (NOT tools.kilo).
    monkeypatch.setattr(forge_common, "invoke_kilo_safe", fake_invoke_kilo_safe)

    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")

    result = de.design_data_contracts(
        site, arch, deploy_spec=None,
        migration_id="m-test", site_slug="example-test",
    )

    assert result is not None
    assert result.contracts[0].fields[0]["required"] == "true"
    assert result.migration_id == "m-test"
    assert result.site_slug == "example-test"
    assert calls["n"] == 1, f"expected 1 Kilo call, got {calls['n']}"


def test_design_uses_repair_call_when_lenient_parse_still_fails(monkeypatch):
    """If even the lenient parse fails, the function must invoke
    exactly ONE repair Kilo call and then succeed."""
    from skills.agentic import data_engineer as de
    from skills.agentic import forge_common
    from models.site_schemas import SiteArchitecture, SiteUnderstanding

    first = {
        "migration_id": "m1",
        "site_slug": "example",
        # cms_sync is Optional[str] but Kilo emitted an int. The lenient
        # parser cannot fix a type mismatch (only an unknown key or
        # boolean→string coercion), so this requires the repair call.
        "contracts": [
            {
                "name": "BlogPost",
                "kind": "static",
                "fields": [],
                "relationships": [],
                "cms_sync": 12345,
                "notes": "",
            },
        ],
    }
    repaired = {
        "migration_id": "m1",
        "site_slug": "example",
        "contracts": [
            {
                "name": "BlogPost",
                "kind": "static",
                "fields": [
                    {"name": "title", "type": "string", "required": "true", "notes": ""},
                ],
                "relationships": [],
                "cms_sync": None,
                "notes": "",
            }
        ],
        "data_architecture_summary": "x",
    }

    calls = {"n": 0, "prompts": []}

    def fake_invoke_kilo_safe(prompt, context, working_dir, persona, timeout, on_timeout=None):
        calls["n"] += 1
        calls["prompts"].append(prompt)
        if calls["n"] == 1:
            return _FakeKiloResult(json.dumps(first))
        return _FakeKiloResult(json.dumps(repaired))

    monkeypatch.setattr(forge_common, "invoke_kilo_safe", fake_invoke_kilo_safe)

    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")

    result = de.design_data_contracts(
        site, arch, deploy_spec=None,
        migration_id="m-test", site_slug="example-test",
    )

    assert result is not None, "expected recovery via repair call"
    assert result.contracts[0].name == "BlogPost"
    assert calls["n"] == 2, f"expected 2 Kilo calls (1 main + 1 repair), got {calls['n']}"
    assert "STRING" in calls["prompts"][1]


# --- Backwards compat: signature unchanged ----------------------------

def test_public_signature_unchanged():
    """The contract is `design_data_contracts(site, architecture,
    deploy_spec=None, *, migration_id, site_slug, gap_context=None)`.
    Don't accidentally break the orchestrator's call site."""
    import inspect
    from skills.agentic.data_engineer import design_data_contracts
    sig = inspect.signature(design_data_contracts)
    params = sig.parameters
    for name in ("site", "architecture", "deploy_spec", "migration_id", "site_slug", "gap_context"):
        assert name in params, f"signature lost parameter: {name}"
    assert params["deploy_spec"].default is None
    assert params["gap_context"].default is None
    assert params["migration_id"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["site_slug"].kind is inspect.Parameter.KEYWORD_ONLY


# --- Extraction retry (Phase 0.6.2 reliability) -----------------------
#
# When Kilo returns prose / truncated text and extract_json() raises
# JSONExtractionError, the forge_common.invoke_kilo_for_persona helper
# already logs a gap and returns (None, last_text). The data_engineer
# persona used to fail-fast on that. It now issues a single retry
# with a terse re-emit prompt (120s timeout) before logging a final gap.

def test_retry_prompt_is_short_and_snake_case():
    """The re-emit prompt must be terse (small chance of Kilo wrapping it
    in 2K summary truncation) and reference the persona-specific
    snake_case schema."""
    from skills.agentic.data_engineer import _retry_prompt_for_reemit
    p = _retry_prompt_for_reemit()
    assert len(p) < 800, f"retry prompt is {len(p)} chars; expected <800"
    assert "snake_case" in p
    assert "data_engineer" in p or "DataContracts" in p


def test_design_retries_on_extraction_failure(monkeypatch):
    """When the first Kilo call returns prose-only (no JSON), the persona
    must issue a retry with the terse re-emit prompt. The retry's clean
    JSON should be parsed and the artifact returned."""
    from skills.agentic import data_engineer as de
    from skills.agentic import forge_common
    from models.site_schemas import SiteArchitecture, SiteUnderstanding

    valid = {
        "migration_id": "m1",
        "site_slug": "example",
        "contracts": [],
        "data_architecture_summary": "Static site.",
        "reasoning_trace": [],
        "produced_at": "",
        "produced_by": "data_engineer",
    }

    calls = {"n": 0, "prompts": [], "timeouts": []}

    def fake_invoke_kilo_safe(prompt, context, working_dir, persona, timeout, on_timeout=None):
        calls["n"] += 1
        calls["prompts"].append(prompt)
        calls["timeouts"].append(timeout)
        if calls["n"] == 1:
            return _FakeKiloResult("just some prose, no JSON whatsoever")
        return _FakeKiloResult(json.dumps(valid))

    monkeypatch.setattr(forge_common, "invoke_kilo_safe", fake_invoke_kilo_safe)

    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")

    result = de.design_data_contracts(
        site, arch, deploy_spec=None,
        migration_id="m-test", site_slug="example-test",
    )

    assert result is not None, "expected recovery via re-emit retry"
    assert result.migration_id == "m-test"
    assert result.site_slug == "example-test"
    assert calls["n"] == 2, f"expected 2 Kilo calls (initial + retry), got {calls['n']}"
    # The retry should use the terse re-emit prompt.
    assert "Re-emit" in calls["prompts"][1] or "Re-emit" in calls["prompts"][1]
    # The retry should use the 120s timeout (consistent with architect).
    assert calls["timeouts"][1] == 120


def test_design_returns_none_and_logs_gap_when_both_calls_fail_extraction(monkeypatch):
    """If BOTH the first call and the retry fail to produce JSON, the
    persona must return None and log a gap with target_persona set to
    the persona so the manager's deterministic short-circuit routes
    back."""
    from skills.agentic import data_engineer as de
    from skills.agentic import forge_common
    from models.site_schemas import SiteArchitecture, SiteUnderstanding
    from memory import gap_ledger
    from pathlib import Path as _Path
    import tempfile as _tempfile

    # Redirect the gap ledger to a tmp file so we don't pollute the real one.
    tmp_ledger = _Path(_tempfile.gettempdir()) / "gap_ledger_test_data_engineer_reliability.jsonl"
    original = gap_ledger.LEDGER_FILE
    gap_ledger.LEDGER_FILE = tmp_ledger
    try:
        calls = {"n": 0}

        def fake_invoke_kilo_safe(prompt, context, working_dir, persona, timeout, on_timeout=None):
            calls["n"] += 1
            return _FakeKiloResult("prose, no JSON anywhere")

        monkeypatch.setattr(forge_common, "invoke_kilo_safe", fake_invoke_kilo_safe)

        site = SiteUnderstanding(
            url="https://example.com", platform="wix", platform_confidence=0.9,
            site_name="example", total_pages_discovered=1, pages=[],
            global_assets={}, contact_info={}, navigation_structure=[],
            estimated_fidelity=0.7,
        )
        arch = SiteArchitecture(source_url="https://example.com")

        result = de.design_data_contracts(
            site, arch, deploy_spec=None,
            migration_id="m-test", site_slug="example-test",
        )

        assert result is None
        assert calls["n"] == 2, f"expected 2 Kilo calls (initial + retry), got {calls['n']}"

        lines = [l for l in tmp_ledger.read_text().splitlines() if l.strip()]
        assert lines, "expected a gap entry to be logged"
        # The last entry is from data_engineer (the second-attempt gap).
        entry = json.loads(lines[-1])
        assert entry["source_persona"] == "data_engineer"
        assert entry["target_persona"] == "data_engineer"
    finally:
        gap_ledger.LEDGER_FILE = original


def test_design_does_not_retry_when_first_call_succeeds(monkeypatch):
    """Happy path: one Kilo call is enough; the re-emit retry must not
    fire when the first response is parseable."""
    from skills.agentic import data_engineer as de
    from skills.agentic import forge_common
    from models.site_schemas import SiteArchitecture, SiteUnderstanding

    valid = {
        "migration_id": "m1",
        "site_slug": "example",
        "contracts": [],
        "data_architecture_summary": "Static site.",
        "produced_by": "data_engineer",
    }

    calls = {"n": 0}

    def fake_invoke_kilo_safe(prompt, context, working_dir, persona, timeout, on_timeout=None):
        calls["n"] += 1
        return _FakeKiloResult(json.dumps(valid))

    monkeypatch.setattr(forge_common, "invoke_kilo_safe", fake_invoke_kilo_safe)

    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")

    result = de.design_data_contracts(
        site, arch, deploy_spec=None,
        migration_id="m-test", site_slug="example-test",
    )

    assert result is not None
    assert calls["n"] == 1, f"happy path should use 1 Kilo call, got {calls['n']}"


if __name__ == "__main__":
    import traceback
    tests = [
        test_prompt_handles_missing_deploy_spec_explicitly,
        test_prompt_includes_explicit_required_string_rule,
        test_lenient_load_drops_unknown_top_level_keys,
        test_lenient_load_drops_unknown_per_contract_keys,
        test_lenient_load_normalises_boolean_required_to_string,
        test_lenient_load_fills_missing_required_and_notes,
        test_lenient_load_skips_malformed_contracts_silently,
        test_design_recovers_leniently_without_repair_call,
        test_design_uses_repair_call_when_lenient_parse_still_fails,
        test_public_signature_unchanged,
        test_retry_prompt_is_short_and_snake_case,
        test_design_retries_on_extraction_failure,
        test_design_returns_none_and_logs_gap_when_both_calls_fail_extraction,
        test_design_does_not_retry_when_first_call_succeeds,
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
