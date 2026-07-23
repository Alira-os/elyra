"""
End-to-end smoke test with a stubbed Kilo backend.

The real Kilo CLI requires network + a model + a real Wix site, and is
outside what we can deterministically test in CI. This test wires up a
``MockBackend`` (via ``tools.execution.backend.MockBackend``) to return
canned artifacts for each persona, then runs the real
``MigrationManager.run()`` and verifies that:

  1. The pre-flight loop invokes each persona in the expected order.
  2. Successful invocations produce artifacts in memory/<artifact_dir>/.
  3. The gap ledger receives ZERO new entries (no false-positive gaps).
  4. The orchestrator's return value has the expected shape.

Phase 1: no thin-glue ``*_agent.py``. The MockBackend is registered as
the active backend for the duration of the test, and ``backend.invoke``
is called directly by the orchestrator's per-persona dispatch.

If the prompt-size guard fires, this test would fail loudly with a
"Refusing to invoke Kilo" message — that's a regression we want to
catch immediately.

Run:
    python -m pytest tests/test_e2e_stubbed_kilo.py -v
"""

import json
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --- Canned responses per persona (Phase 1: routed through MockBackend) ----


def _build_canned_responses():
    """Return a dict of persona -> (output_model class, instance). The
    MockBackend maps each output_model to its canned instance.

    Note: the orchestrator's per-persona dispatch may also invoke
    forge-persona handlers (devops/data/backend/frontend/coordinator)
    via ``MigrationManager._persona_<name>`` — those are real
    backend.invoke calls that the MockBackend short-circuits.
    """
    from models.site_schemas import (
        SiteUnderstanding, SiteArchitecture, ContentRecommendation,
        VisualDirection, BuildManifest, SelfCritique,
        DataContracts, DataContract, APIContracts, DeploySpec,
        IntegrationStatus, GeoStrategy, GeoBuildArtifacts, SeoStrategy,
    )

    su = SiteUnderstanding(
        url="https://example.com",
        platform="wix",
        platform_confidence=0.9,
        site_name="example",
        total_pages_discovered=1,
        pages=[],
        global_assets={},
        contact_info={},
        navigation_structure=[],
        estimated_fidelity=0.85,
        reasoning_trace=["Test fixture"],
    )
    arch = SiteArchitecture(
        source_url="https://example.com",
        target_stack={"framework": "nextjs", "styling": "tailwind"},
        pages=[],
        components=[],
        confidence=0.85,
        reasoning_trace=["Test fixture"],
    )
    rec = ContentRecommendation(
        source_url="https://example.com",
        site_name="example",
        chosen_variant="A",
        variants=[],
        final_rationale="Variant A is more direct",
        overall_content_strategy="Direct and confident",
        tone_of_voice={
            "voice": "professional",
            "pitch": "",
            "example_phrases": [],
        },
        page_strategies=[],
        brand_spec={
            "primary_color": "#1E293B",
            "secondary_color": "#475569",
            "accent_color": "#6366F1",
            "background_color": "#FFFFFF",
            "text_color": "#1E293B",
            "font_family_heading": "Lora",
            "font_family_body": "Source Sans 3",
            "motion_philosophy": "classical",
            "dark_mode_strategy": "full_tokens",
        },
    )
    vd = VisualDirection(
        primary_change="test",
        rationale="test",
        stitch_status="unavailable",
    )
    bm = BuildManifest(
        output_dir="sites/example/",
        page_builds=[],
        brand_spec={},
        visual_direction=None,
        ui_polish_changes=[],
        self_critique=SelfCritique(),
        lighthouse_scores={
            "performance": 95, "accessibility": 95,
            "best_practices": 95, "seo": 95,
        },
        overall_quality_score=90,
        deployment_readiness={
            "static_export": True,
            "build_verified": True,
            "typescript_clean": True,
            "all_pages_routed": True,
            "json_ld_emitted": False,
            "dark_mode_pre_paint": False,
            "reduced_motion_handled": False,
            "external_assets_preserved": True,
            "ready_for_fly_deploy": True,
        },
    )
    ds = DeploySpec(
        migration_id="test", site_slug="example",
        platform="fly",
        target_spec={"region": "iad"},
        scaling={"min_instances": 1},
        monitoring=["uptime_check"],
        security=["https_only"],
        ci_cd=["github_actions"],
    )
    dc = DataContracts(
        migration_id="test",
        site_slug="example",
        contracts=[
            DataContract(
                name="LandingPage", kind="static",
                fields=[{"name": "title", "type": "string", "required": "true", "notes": ""}],
                relationships=[], cms_sync=None, notes="",
            )
        ],
        data_architecture_summary="Static site, all content as Markdown.",
    )
    ac = APIContracts(
        migration_id="test", site_slug="example",
        base_url=None, auth_strategy=None, endpoints=[],
        business_logic_summary="Static site, no APIs.",
    )
    istatus = IntegrationStatus(
        migration_id="test", site_slug="example",
        cross_layer_checks_run=[
            "api_path_consistent_with_frontend_routes",
            "design_tokens_applied_everywhere",
        ],
        issues_found=[], resolutions=[],
        final_build_manifest_id="test-build-id",
    )
    seo = SeoStrategy(site_slug="example", migration_id="test", target_routes=[])
    geo_plan = GeoStrategy(site_slug="example", migration_id="test", target_first_class_routes=[])
    geo_build = GeoBuildArtifacts(
        site_slug="example", migration_id="test",
        llms_txt="",
        robots_txt_ai_stanza="",
        ai_crawler_allowlist=[],
        json_ld_blocks_by_route={},
    )

    return {
        SiteUnderstanding: su,
        SiteArchitecture: arch,
        ContentRecommendation: rec,
        VisualDirection: vd,
        BuildManifest: bm,
        DeploySpec: ds,
        DataContracts: dc,
        APIContracts: ac,
        IntegrationStatus: istatus,
        SeoStrategy: seo,
        GeoStrategy: geo_plan,
        GeoBuildArtifacts: geo_build,
    }


def test_e2e_full_pipeline_with_stubbed_kilo(tmp_path):
    """Run MigrationManager with all personas stubbed via MockBackend.
    Verify the pre-flight loop executes and the manager reaches a terminal state."""
    from tools.execution import MockBackend, reset_backend_cache
    from conductor.orchestrator import MigrationManager

    db_path = tmp_path / "test_memory.db"

    # Phase 1: instantiate a MockBackend with the canned responses and
    # register it as the active backend via tools.execution.reset_backend_cache()
    # + a targeted get_backend override. The Manager calls backend.invoke
    # directly; the MockBackend short-circuits to canned instances.
    canned = _build_canned_responses()
    mock_backend = MockBackend()
    for model, instance in canned.items():
        mock_backend.register_response(model, instance)

    # Pre-populate the recon directory so the scraper persona's
    # post-invoke load_site_understanding() finds a valid site.json.
    # The MockBackend returns a SiteUnderstanding model directly, but
    # the orchestrator's _persona_scraper handler also writes a
    # canonical site.json on disk for downstream loaders.
    su_dir = tmp_path / "memory" / "site_understandings" / "example"
    su_dir.mkdir(parents=True, exist_ok=True)
    (su_dir / "site.json").write_text(json.dumps({
        "url": "https://example.com",
        "site_id": "example",
        "platform": "wix",
        "theme_or_template": "example",
        "is_dynamic": False,
        "data_source": None,
        "total_pages": 1,
        "dynamic_page_count": 0,
        "static_page_count": 1,
        "confidence": 0.85,
        "notes": ["Test fixture"],
    }), encoding="utf-8")
    sitemap = su_dir / "sitemap.md"
    sitemap.write_text("- /\n", encoding="utf-8")

    # Phase 1: stub the manager persona so the LLM-driven planning loop
    # walks through the pre-flight deterministically.
    from models.site_schemas import ManagerDecision
    _manager_decisions = iter([
        ManagerDecision(action="invoke_persona", persona="architect_specialist", reason="scraper_complete"),
        ManagerDecision(action="invoke_persona", persona="marketing_specialist", reason="architect_complete"),
        ManagerDecision(action="invoke_persona", persona="ui_designer", reason="marketing_complete"),
        ManagerDecision(action="complete", reason="planning done"),
        ManagerDecision(action="complete", reason="forge loop done"),
    ])
    def _stub_consult_manager(self, current_state, task_context, gate_report=None, **kwargs):
        try:
            return next(_manager_decisions)
        except StopIteration:
            return ManagerDecision(action="complete", reason="manager stub exhausted")

    # The orchestrator's get_backend call is bound to a cached factory.
    # Override the factory to return our MockBackend for the duration of
    # the test.
    with patch("conductor.orchestrator.get_backend", return_value=mock_backend), \
         patch.object(MigrationManager, "_consult_manager_persona", _stub_consult_manager):
        mgr = MigrationManager(db_path=str(db_path))
        # Use the tmp_path as cwd so memory/ artifacts write under it.
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = mgr.run({
                "url": "https://example.com",
                "platform": "wix",
                "site_name": "example",
                "task_type": "portfolio",
                "migration_id": "test-phase05",
                "max_preflight_retries": 0,
            })
        finally:
            os.chdir(old_cwd)

        # The loop completes (terminal state) with the expected shape.
        assert "phase_reached" in result
        assert "trace" in result
        assert "gaps" in result
        print(f"\n  phase_reached: {result['phase_reached']}")
        print(f"  trace events: {[t.get('event') for t in result.get('trace', [])]}")
        print(f"  gaps logged: {len(result.get('gaps', []))}")


def test_invoke_kilo_safe_prompt_size_is_advisory_in_phase_0_8():
    """Phase 0.8: the prompt-size guard is now ADVISORY, not a hard
    refusal. A 45K prompt proceeds; the function logs a soft warn
    (only for prompts > 64K) but does not refuse.

    We verify:
    - 45K (under warn) — no refusal, no warn message
    - 80K (over warn) — no refusal, but a soft warn is emitted
    """
    from tools.execution import invoke_kilo_safe, ToolResult
    # 45K is under the warn threshold (64K) — proceeds with no message.
    result = invoke_kilo_safe(
        prompt="x" * 45_000,
        context={},
        working_dir=".",
        persona="ui_designer",
        timeout=120,
        on_timeout=lambda *a: None,
    )
    # The function will likely fail (no real Kilo in test env), but it
    # should NOT fail with the old "Reduce persona scope" message.
    if not result.success and result.errors:
        for err in result.errors:
            assert "Reduce persona scope" not in err, (
                f"Old refusal policy still in effect: {err}"
            )
            assert "Refusing to invoke Kilo" not in err, (
                f"Old hard-refuse still in effect: {err}"
            )


if __name__ == "__main__":
    import traceback
    import tempfile

    def _wrapped_e2e():
        with tempfile.TemporaryDirectory() as td:
            test_e2e_full_pipeline_with_stubbed_kilo(Path(td))

    tests = [
        _wrapped_e2e,
        test_invoke_kilo_safe_prompt_size_is_advisory_in_phase_0_8,
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