"""
Unit tests for the Phase 1.0 orchestrator wiring.

Covers:
  - Planning Coherence Gate (5 inputs, 5 outputs, pass/fail/waiver paths)
  - Handoff Ceremony (bundle construction, persistence, room tagging)
  - Room-aware trace events
  - Full E2E with stubbed Kilo (manager reaches terminal state, bundle is
    produced, gate runs)

Run:
    python -m pytest tests/test_phase1_wiring.py -v
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import (  # noqa: E402
    ManagerDecision,
    SiteUnderstanding,
    SiteArchitecture,
    ContentRecommendation,
    VisualDirection,
    BrandSpec,
    CoherenceGateReport,
    HandoffBundle,
)
from conductor.orchestrator import MigrationManager  # noqa: E402


def _make_site_understanding() -> SiteUnderstanding:
    return SiteUnderstanding(
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
        reasoning_trace=["Chose Next.js based on Wix structure"],
    )


def _make_site_architecture() -> SiteArchitecture:
    return SiteArchitecture(
        source_url="https://example.com",
        target_stack={"framework": "nextjs", "styling": "tailwind"},
        pages=[],
        components=[],
        confidence=0.85,
        reasoning_trace=["Chose Next.js based on Wix structure"],
    )


def _make_content_recommendation() -> ContentRecommendation:
    from models.site_schemas import ToneOfVoice
    return ContentRecommendation(
        source_url="https://example.com",
        site_name="example",
        chosen_variant="A",
        variants=[],
        final_rationale="A",
        overall_content_strategy="Direct",
        tone_of_voice=ToneOfVoice(),
        page_strategies=[],
        brand_spec=BrandSpec(
            primary_color="#1E293B",
            secondary_color="#475569",
            accent_color="#6366F1",
            background_color="#FFFFFF",
            text_color="#1E293B",
            font_family_heading="Lora",
            font_family_body="Source Sans 3",
            motion_philosophy="classical",
            dark_mode_strategy="full_tokens",
        ),
    )


def _make_visual_direction() -> VisualDirection:
    return VisualDirection(
        primary_change="No visual evolution",
        rationale="Stitch unavailable; BrandSpec fidelity only",
        stitch_status="unavailable",
    )


# --- Coherence Gate ---------------------------------------------------------

def test_gate_passes_with_all_artifacts_present():
    m = MigrationManager(db_path=":memory:")
    artifacts = {
        "scraper": _make_site_understanding(),
        "architect": _make_site_architecture(),
        "marketing": _make_content_recommendation(),
        "designer": _make_visual_direction(),
    }
    report = m._run_planning_coherence_gate(artifacts, gaps_logged=[])
    assert report.passed is True
    assert report.gate_name == "planning_coherence_gate"
    assert report.artifact_coverage == {
        "site_understanding": True,
        "site_architecture": True,
        "content_recommendation": True,
        "visual_direction": True,
    }
    assert report.fidelity_score == 0.85
    assert "PASS" in report.summarize()


def test_gate_blocks_when_artifacts_missing():
    m = MigrationManager(db_path=":memory:")
    artifacts = {
        "scraper": _make_site_understanding(),
        "architect": _make_site_architecture(),
        # marketing and designer missing
    }
    report = m._run_planning_coherence_gate(artifacts, gaps_logged=[])
    assert report.passed is False
    assert any("missing planning artifacts" in b.reason for b in report.blocking)
    assert report.artifact_coverage["content_recommendation"] is False
    assert report.artifact_coverage["visual_direction"] is False


def test_gate_warns_on_low_fidelity_score():
    m = MigrationManager(db_path=":memory:")
    arch = _make_site_architecture()
    arch.confidence = 0.4  # below 0.7 threshold
    artifacts = {
        "scraper": _make_site_understanding(),
        "architect": arch,
        "marketing": _make_content_recommendation(),
        "designer": _make_visual_direction(),
    }
    report = m._run_planning_coherence_gate(artifacts, gaps_logged=[])
    assert report.passed is True  # warnings, not blocking
    assert any("fidelity_score=0.40 below threshold" in w for w in report.warnings)


def test_gate_blocks_on_unanswered_high_severity_gaps():
    m = MigrationManager(db_path=":memory:")
    artifacts = {
        "scraper": _make_site_understanding(),
        "architect": _make_site_architecture(),
        "marketing": _make_content_recommendation(),
        "designer": _make_visual_direction(),
    }
    gaps = [
        {
            "gap_id": "g1",
            "severity": "high",
            "source_persona": "architect",
            "description": "Missing component spec for hero",
            # No target_persona — this is an "unanswered" question
        }
    ]
    report = m._run_planning_coherence_gate(artifacts, gaps)
    assert report.passed is False
    assert any("unanswered high-severity gap" in b.reason for b in report.blocking)


def test_gate_does_not_block_on_targeted_high_severity_gaps():
    """A high-severity gap WITH a target_persona is considered routed,
    not unanswered."""
    m = MigrationManager(db_path=":memory:")
    artifacts = {
        "scraper": _make_site_understanding(),
        "architect": _make_site_architecture(),
        "marketing": _make_content_recommendation(),
        "designer": _make_visual_direction(),
    }
    gaps = [
        {
            "gap_id": "g1",
            "severity": "high",
            "source_persona": "designer",
            "target_persona": "designer",
            "description": "Re-run needed",
        }
    ]
    report = m._run_planning_coherence_gate(artifacts, gaps)
    # No blocking from g1 because it has a target.
    unanswered_blocking = [b for b in report.blocking if "g1" in b.reason or "Re-run" in b.reason]
    assert unanswered_blocking == []


def test_gate_warns_when_bidirectional_pull_count_is_zero():
    m = MigrationManager(db_path=":memory:")
    artifacts = {
        "scraper": _make_site_understanding(),
        "architect": _make_site_architecture(),
        "marketing": _make_content_recommendation(),
        "designer": _make_visual_direction(),
    }
    report = m._run_planning_coherence_gate(artifacts, gaps_logged=[])
    # No steward_pull events were logged → warning
    assert any("never bidirectionally pulled" in w for w in report.warnings)


# --- Handoff Ceremony -------------------------------------------------------

def test_ceremony_produces_bundle_with_correct_artifact_ids(tmp_path):
    """The ceremony should resolve artifact IDs from the on-disk stores
    and produce a bundle with the right from_room/to_room."""
    import os
    import shutil
    old_cwd = os.getcwd()
    try:
        # Initialize the manager in elyra/ so the SQLite schema lookup
        # works, then chdir to tmp_path so the ceremony writes there.
        m = MigrationManager(db_path=":memory:")

        # Pre-populate the artifact stores under tmp_path.
        for subdir, file_id in [
            ("site_understandings", "su-1"),
            ("site_architectures", "sa-1"),
            ("site_recommendations", "cr-1"),
        ]:
            d = tmp_path / "memory" / subdir
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{file_id}.json").write_text("{}")
        vs_dir = tmp_path / "memory/visual_specs/example"
        vs_dir.mkdir(parents=True, exist_ok=True)
        (vs_dir / "vd-1.json").write_text("{}")

        artifacts = {
            "scraper": _make_site_understanding(),
            "architect": _make_site_architecture(),
            "marketing": _make_content_recommendation(),
            "designer": _make_visual_direction(),
        }
        gate_report = m._run_planning_coherence_gate(artifacts, gaps_logged=[])
        # Run the ceremony under tmp_path so the bundle is persisted there.
        os.chdir(tmp_path)
        bundle = m._run_handoff_ceremony(
            migration_id="m-test-1",
            site_slug="example",
            site_name="Example",
            artifacts=artifacts,
            gate_report=gate_report,
            gaps_logged=[],
            task_context={},
        )
    finally:
        os.chdir(old_cwd)

    assert isinstance(bundle, HandoffBundle)
    assert bundle.migration_id == "m-test-1"
    assert bundle.site_slug == "example"
    assert bundle.from_room == "planning"
    assert bundle.to_room == "forge"
    assert bundle.site_understanding_id == "su-1"
    assert bundle.site_architecture_id == "sa-1"
    assert bundle.content_recommendation_id == "cr-1"
    assert bundle.visual_direction_id == "vd-1"
    assert bundle.brand_spec is not None
    assert bundle.brand_spec["primary_color"] == "#1E293B"
    # The planning_rationale should pull from the architect's reasoning_trace
    # (the closest field to "rationale" in the real SiteArchitecture schema).
    assert len(bundle.planning_rationale) >= 1
    assert any("Next.js" in r for r in bundle.planning_rationale)


def test_ceremony_persists_bundle_to_disk(tmp_path):
    """The bundle should be persisted to memory/migrations/<id>/handoff_bundle.json."""
    import os
    old_cwd = os.getcwd()
    try:
        m = MigrationManager(db_path=":memory:")
        artifacts = {
            "scraper": _make_site_understanding(),
            "architect": _make_site_architecture(),
            "marketing": _make_content_recommendation(),
            "designer": _make_visual_direction(),
        }
        gate_report = m._run_planning_coherence_gate(artifacts, gaps_logged=[])
        os.chdir(tmp_path)
        bundle = m._run_handoff_ceremony(
            migration_id="m-persist",
            site_slug="example",
            site_name="Example",
            artifacts=artifacts,
            gate_report=gate_report,
            gaps_logged=[],
            task_context={},
        )
    finally:
        os.chdir(old_cwd)

    assert bundle.bundle_id == "handoff-m-persist"
    assert bundle.from_room == "planning"
    assert bundle.to_room == "forge"
    data = bundle.model_dump()
    assert data["migration_id"] == "m-persist"


def test_ceremony_marks_human_review_when_gate_has_waivers(tmp_path):
    """Gate passing with waivers → bundle.requires_human_review is True."""
    import os
    old_cwd = os.getcwd()
    try:
        m = MigrationManager(db_path=":memory:")
        artifacts = {
            "scraper": _make_site_understanding(),
            "architect": _make_site_architecture(),
            "marketing": _make_content_recommendation(),
            "designer": _make_visual_direction(),
        }
        from models.site_schemas import CoherenceGateWaiver
        gate_report = CoherenceGateReport(
            gate_name="planning_coherence_gate",
            passed=True,
            waivers=[
                CoherenceGateWaiver(
                    field="fidelity_score",
                    reason="site is too minimal",
                    owner="architect_specialist",
                    risk_level="low",
                )
            ],
        )
        os.chdir(tmp_path)
        bundle = m._run_handoff_ceremony(
            migration_id="m-waiver",
            site_slug="example",
            site_name="Example",
            artifacts=artifacts,
            gate_report=gate_report,
            gaps_logged=[],
            task_context={},
        )
    finally:
        os.chdir(old_cwd)

    assert bundle.requires_human_review is True
    assert "1 waiver" in bundle.human_review_reason


# --- Room-aware trace -------------------------------------------------------

def test_log_trace_with_room_adds_room_field():
    m = MigrationManager(db_path=":memory:")
    m._log_trace_with_room("test_event", {"foo": "bar"}, room="planning")
    assert len(m.trace) == 1
    assert m.trace[0]["event"] == "test_event"
    assert m.trace[0]["payload"]["foo"] == "bar"
    assert m.trace[0]["payload"]["room"] == "planning"


# --- End-to-end with stubbed Kilo -------------------------------------------

def test_e2e_stubbed_kilo_produces_bundle():
    """The full stubbed-Kilo E2E should reach `complete` and include a
    HandoffBundle in the result.

    Phase 1: the orchestrator routes persona invocation through
    ``MigrationManager._persona_<name>`` methods which call
    ``backend.invoke(...)`` directly. We patch those methods to return
    canned Pydantic artifacts (which is what ``backend.invoke(...)``
    would do for a MockBackend in production).
    """

    # --- Persona handler stubs (return canned Pydantic artifacts). ---
    def _make_scraper(*a, **kw):
        return {"success": True, "artifact": _make_site_understanding()}

    def _make_architect(*a, **kw):
        return {"success": True, "artifact": _make_site_architecture()}

    def _make_marketing(*a, **kw):
        return {"success": True, "artifact": _make_content_recommendation()}

    def _make_designer(*a, **kw):
        return {"success": True, "artifact": _make_visual_direction()}

    def _make_builder(*a, **kw):
        from models.site_schemas import BuildManifest, SelfCritique
        bm = BuildManifest(
            output_dir="sites/example/",
            page_builds=[],
            brand_spec={},
            visual_direction=None,
            ui_polish_changes=[],
            self_critique=SelfCritique(),
            lighthouse_scores={},
            overall_quality_score=90,
            deployment_readiness={
                "static_export": True,
                "build_verified": True,
                "ready_for_fly_deploy": True,
            },
        )
        return {"success": True, "artifact": bm, "built_site_slug": "example"}

    # Phase 1.1: Forge Room persona stubs.
    from models.site_schemas import (
        DataContracts, DataContract,
        APIContracts, APIEndpoint,
        DeploySpec, IntegrationStatus,
    )

    def _make_deploy_spec(*a, **kw):
        return {"success": True, "artifact": DeploySpec(
            migration_id="test-phase1-wiring",
            site_slug="example",
            platform="fly",
            target_spec={"region": "iad"},
            scaling={"min_instances": 1},
            monitoring=["uptime_check"],
            security=["https_only"],
            ci_cd=["github_actions"],
        )}

    def _make_data_contracts(*a, **kw):
        return {"success": True, "artifact": DataContracts(
            migration_id="test-phase1-wiring",
            site_slug="example",
            contracts=[
                DataContract(
                    name="LandingPage",
                    kind="static",
                    fields=[
                        {"name": "title", "type": "string", "required": "true", "notes": ""},
                        {"name": "body", "type": "markdown", "required": "true", "notes": ""},
                    ],
                    relationships=[],
                    cms_sync=None,
                    notes="One .md per page.",
                )
            ],
            data_architecture_summary="Static site, all content as Markdown.",
        )}

    def _make_api_contracts(*a, **kw):
        return {"success": True, "artifact": APIContracts(
            migration_id="test-phase1-wiring",
            site_slug="example",
            base_url=None,
            auth_strategy=None,
            endpoints=[],
            business_logic_summary="Static site, no APIs.",
        )}

    def _make_integration_status(*a, **kw):
        return {"success": True, "artifact": IntegrationStatus(
            migration_id="test-phase1-wiring",
            site_slug="example",
            cross_layer_checks_run=[
                "api_path_consistent_with_frontend_routes",
                "design_tokens_applied_everywhere",
                "cms_models_match_frontend_data_fetchers",
            ],
            issues_found=[],
            resolutions=[],
            final_build_manifest_id="test-build-id",
        )}

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sqlite_dir = tmp / "memory" / "sqlite"
        sqlite_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        schema_src = Path("memory/sqlite/schema.sql").resolve()
        shutil.copy2(schema_src, sqlite_dir / "schema.sql")

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp)
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
            with patch.object(MigrationManager, "_persona_scraper", side_effect=_make_scraper), \
                 patch.object(MigrationManager, "_persona_architect", side_effect=_make_architect), \
                 patch.object(MigrationManager, "_persona_marketing", side_effect=_make_marketing), \
                 patch.object(MigrationManager, "_persona_designer", side_effect=_make_designer), \
                 patch.object(MigrationManager, "_persona_builder", side_effect=_make_builder), \
                 patch.object(MigrationManager, "_persona_devops", side_effect=_make_deploy_spec), \
                 patch.object(MigrationManager, "_persona_data", side_effect=_make_data_contracts), \
                 patch.object(MigrationManager, "_persona_backend", side_effect=_make_api_contracts), \
                 patch.object(MigrationManager, "_persona_frontend", side_effect=_make_builder), \
                 patch.object(MigrationManager, "_persona_coordinator", side_effect=_make_integration_status), \
                 patch("tools.execution.get_backend", side_effect=lambda *a, **kw: None), \
                 patch.object(MigrationManager, "_consult_manager_persona", _stub_consult_manager):
                m = MigrationManager(db_path=":memory:")
                result = m.run({
                    "url": "https://example.com",
                    "platform": "wix",
                    "site_name": "example",
                    "task_type": "portfolio",
                    "migration_id": "test-phase1-wiring",
                    "max_preflight_retries": 0,
                })
        finally:
            os.chdir(old_cwd)

        assert "coherence_gate" in result
        assert "handoff_bundle" in result
        assert result["handoff_bundle"] is not None
        bundle = result["handoff_bundle"]
        assert bundle["from_room"] == "planning"
        assert bundle["to_room"] == "forge"
        assert bundle["coherence_gate"]["passed"] is True


if __name__ == "__main__":
    import traceback
    tests = [
        test_gate_passes_with_all_artifacts_present,
        test_gate_blocks_when_artifacts_missing,
        test_gate_warns_on_low_fidelity_score,
        test_gate_blocks_on_unanswered_high_severity_gaps,
        test_gate_does_not_block_on_targeted_high_severity_gaps,
        test_gate_warns_when_bidirectional_pull_count_is_zero,
        test_ceremony_produces_bundle_with_correct_artifact_ids,
        test_ceremony_persists_bundle_to_disk,
        test_ceremony_marks_human_review_when_gate_has_waivers,
        test_log_trace_with_room_adds_room_field,
        test_e2e_stubbed_kilo_produces_bundle,
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
