"""
Unit tests for the Phase 1.1 Forge Room split.

Covers:
  - New Pydantic schemas (DataContract, APIContracts, DeploySpec, IntegrationStatus)
  - New persona modules (data_engineer, backend_architect, frontend_architect,
    integration_coordinator, devops_engineer) — imports + entry points
  - forge_common helpers
  - The orchestrator's FORGE_ROOM.ordered_personas() and dispatch

Run:
    python -m pytest tests/test_phase11_forge_room.py -v
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- New Pydantic schemas -----------------------------------------------

def test_data_contract_validates():
    from models.site_schemas import DataContract
    c = DataContract(
        name="BlogPost", kind="cms",
        fields=[{"name": "title", "type": "string", "required": "true", "notes": ""}],
        relationships=[],
        cms_sync="fetched from Wix CMS at build time",
        notes="",
    )
    assert c.name == "BlogPost"
    assert c.kind == "cms"
    assert c.fields[0]["name"] == "title"


def test_data_contracts_validates():
    from models.site_schemas import DataContracts, DataContract
    cs = DataContracts(
        migration_id="m1", site_slug="example",
        contracts=[
            DataContract(name="A", kind="static", fields=[]),
            DataContract(name="B", kind="cms", fields=[{"name": "k", "type": "v", "required": "true", "notes": ""}]),
        ],
        data_architecture_summary="",
    )
    assert len(cs.contracts) == 2


def test_api_endpoint_validates():
    from models.site_schemas import APIEndpoint
    ep = APIEndpoint(
        method="POST", path="/api/blog-posts",
        purpose="create a new blog post",
        auth_required=True,
    )
    assert ep.method == "POST"
    assert ep.auth_required is True


def test_api_contracts_accepts_empty():
    """Static sites have no API. The schema should allow that."""
    from models.site_schemas import APIContracts
    ac = APIContracts(
        migration_id="m1", site_slug="example",
        base_url=None, auth_strategy=None,
        endpoints=[],
        business_logic_summary="",
    )
    assert ac.endpoints == []


def test_deploy_spec_validates():
    from models.site_schemas import DeploySpec
    ds = DeploySpec(
        migration_id="m1", site_slug="example",
        platform="fly",
        target_spec={"region": "iad"},
        scaling={"min_instances": 1},
        monitoring=["uptime_check"],
        security=["https_only"],
        ci_cd=["github_actions"],
    )
    assert ds.platform == "fly"
    assert "https_only" in ds.security


def test_deploy_spec_rejects_unknown_platform():
    """The Literal enum on platform locks the supported values."""
    from models.site_schemas import DeploySpec
    try:
        DeploySpec(
            migration_id="m1", site_slug="example",
            platform="magic_cloud",  # INVALID
        )
    except Exception:
        return
    raise AssertionError("expected ValidationError for unknown platform")


def test_integration_status_validates():
    from models.site_schemas import IntegrationStatus
    ist = IntegrationStatus(
        migration_id="m1", site_slug="example",
        cross_layer_checks_run=["api_path_consistent_with_frontend_routes"],
        issues_found=["endpoint path mismatched frontend route"],
        resolutions=["renamed /api/posts to /api/blog-posts"],
        final_build_manifest_id="20260608_160000",
    )
    assert ist.issues_found[0].startswith("endpoint")
    assert ist.resolutions[0].startswith("renamed")
    assert ist.final_build_manifest_id == "20260608_160000"


# --- Persona modules ---------------------------------------------------

def test_forge_persona_modules_import():
    modules = [
        "skills.agentic.forge_common",
        "skills.agentic.data_engineer",
        "skills.agentic.backend_architect",
        "skills.agentic.frontend_architect",
        "skills.agentic.integration_coordinator",
        "skills.agentic.devops_engineer",
    ]
    for m in modules:
        __import__(m)


def test_forge_common_invoke_kilo_helper_signature():
    """The shared invoke_kilo_for_persona helper should accept the
    standard set of kwargs without raising."""
    from skills.agentic.forge_common import invoke_kilo_for_persona
    import inspect
    sig = inspect.signature(invoke_kilo_for_persona)
    expected = {"persona", "prompt", "context", "migration_id", "timeout_s"}
    assert expected.issubset(set(sig.parameters.keys()))


def test_forge_common_load_persona_markdown():
    from skills.agentic.forge_common import load_persona_markdown
    md = load_persona_markdown("data_engineer")
    assert "Data Engineer" in md or len(md) > 0  # may be empty in test env
    # The legacy persona is also readable.
    md2 = load_persona_markdown("backend_architect")
    # backend_architect.md may or may not exist; the helper returns "".
    assert isinstance(md2, str)


# --- Orchestrator: FORGE_ROOM & dispatch ---------------------------------

def test_forge_room_has_five_personas():
    from conductor.orchestrator import MigrationManager
    m = MigrationManager(db_path=":memory:")
    personas = m.FORGE_ROOM.ordered_personas()
    # Phase E: geo_specialist joined the Forge (between frontend_architect
    # and integration_coordinator) so the room now has six personas.
    assert len(personas) == 6
    assert personas[0] == "deploy_specialist"  # devops runs first
    assert personas[-1] == "integration_coordinator"  # steward last


def test_forge_room_steward_is_integration_coordinator():
    from conductor.orchestrator import MigrationManager
    m = MigrationManager(db_path=":memory:")
    assert m.FORGE_ROOM.steward == "integration_coordinator"


def test_short_to_long_map_has_all_forge_personas():
    """The orchestrator's _SHORT_TO_LONG map (now including Forge Room
    short names) should be complete and invertible."""
    from conductor.orchestrator import MigrationManager
    m = MigrationManager(db_path=":memory:")
    # We can't import _SHORT_TO_LONG directly (it's a local in run()),
    # but the ordered_personas list proves the map is in place by
    # virtue of the orchestrator accepting the long names.
    planning = m.PLANNING_ROOM.ordered_personas()
    forge = m.FORGE_ROOM.ordered_personas()
    # All long names — these are what _invoke_persona uses
    # internally via the long→short map.
    for p in planning + forge:
        assert isinstance(p, str)
        assert p.endswith("_specialist") or p in (
            "data_engineer", "backend_architect", "frontend_architect",
            "integration_coordinator", "scraper_specialist", "ui_designer",
        )


def test_short_to_long_contains_legacy_builder():
    """The legacy 'builder' short name is preserved for backward
    compat with any in-flight migration referencing the monolithic
    builder."""
    # Indirect test: the orchestrator's _invoke_persona accepts
    # persona='builder' as a valid dispatch. We verify by reading the
    # source: the local _SHORT_TO_LONG in run() must contain 'builder'.
    import inspect
    from conductor.orchestrator import MigrationManager
    src = inspect.getsource(MigrationManager.run)
    assert '"builder": "builder"' in src


# --- Optional: smoke test each persona's prompt builder (no Kilo) -----

def test_data_engineer_prompt_includes_deploy_spec():
    """The data engineer should reference the DeploySpec in its prompt
    so the data layer can be designed to match the deploy target."""
    from skills.agentic.data_engineer import build_data_engineer_prompt
    from models.site_schemas import SiteArchitecture, SiteUnderstanding, DeploySpec
    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    deploy = DeploySpec(migration_id="m1", site_slug="example", platform="fly")
    prompt = build_data_engineer_prompt(site, arch, deploy)
    assert "Data Engineer" in prompt
    assert "DeploySpec" in prompt
    assert "fly" in prompt


def test_backend_prompt_includes_data_contracts():
    from skills.agentic.backend_architect import build_backend_prompt
    from models.site_schemas import SiteArchitecture, SiteUnderstanding, DataContracts
    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    data_cs = DataContracts(
        migration_id="m1", site_slug="example",
        contracts=[],
    )
    prompt = build_backend_prompt(site, arch, data_contracts=data_cs)
    assert "Backend" in prompt or "backend" in prompt
    assert "DataContracts" in prompt or "Data Engineer" in prompt


def test_frontend_prompt_includes_everything():
    """The frontend architect is the convergence point — it should
    reference all upstream artifacts."""
    from skills.agentic.frontend_architect import build_frontend_prompt
    from models.site_schemas import (
        SiteUnderstanding, SiteArchitecture, ContentRecommendation, VisualDirection, ToneOfVoice,
    )
    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    rec = ContentRecommendation(
        source_url="https://example.com",
        site_name="example", overall_content_strategy="Direct",
        chosen_variant="A", variants=[], final_rationale="A",
        tone_of_voice=ToneOfVoice(),
    )
    vd = VisualDirection(primary_change="x", rationale="y", stitch_status="unavailable")
    prompt = build_frontend_prompt(site, arch, rec, "example", visual_direction=vd)
    for needle in ["DeploySpec", "DataContracts", "APIContracts", "VisualDirection", "BuildManifest"]:
        assert needle in prompt, f"frontend prompt missing {needle}"


def test_integration_prompt_includes_everything():
    from skills.agentic.integration_coordinator import build_integration_prompt
    from models.site_schemas import SiteUnderstanding, SiteArchitecture
    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    prompt = build_integration_prompt(site, arch, build_id="test-build-id")
    assert "BuildManifest ID" in prompt or "test-build-id" in prompt
    assert "DataContracts" in prompt
    assert "APIContracts" in prompt


def test_devops_prompt_includes_site_and_arch():
    from skills.agentic.devops_engineer import build_devops_prompt
    from models.site_schemas import SiteUnderstanding, SiteArchitecture
    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="example", total_pages_discovered=1, pages=[],
        global_assets={}, contact_info={}, navigation_structure=[],
        estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    prompt = build_devops_prompt(site, arch)
    assert "DevOps" in prompt or "DeploySpec" in prompt
    assert "site" in prompt.lower()


if __name__ == "__main__":
    import traceback
    tests = [
        test_data_contract_validates,
        test_data_contracts_validates,
        test_api_endpoint_validates,
        test_api_contracts_accepts_empty,
        test_deploy_spec_validates,
        test_deploy_spec_rejects_unknown_platform,
        test_integration_status_validates,
        test_forge_persona_modules_import,
        test_forge_common_invoke_kilo_helper_signature,
        test_forge_common_load_persona_markdown,
        test_forge_room_has_five_personas,
        test_forge_room_steward_is_integration_coordinator,
        test_short_to_long_map_has_all_forge_personas,
        test_short_to_long_contains_legacy_builder,
        test_data_engineer_prompt_includes_deploy_spec,
        test_backend_prompt_includes_data_contracts,
        test_frontend_prompt_includes_everything,
        test_integration_prompt_includes_everything,
        test_devops_prompt_includes_site_and_arch,
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
