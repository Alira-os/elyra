"""
Unit tests for Phase E — Discoverability Specialists (SEO + GEO-for-LLMs).

Covers:
  - Schema round-trip for SeoStrategy, GeoStrategy, GeoBuildArtifacts
  - HandoffBundle carries the two new strategy ID fields
  - build_quality_gate polish checks fail/pass per spec
  - Planning Room preflight order includes seo_specialist and
    geo_specialist in the right slots
  - MigrationManager.LOCKED_AI_CRAWLERS is 11 entries and matches the
    canonical list in docs/GEO_FOR_LLMS.md

Run:
    python -m pytest tests/test_discoverability_strategies.py -v
"""

import sys
import json
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import (  # noqa: E402
    SeoStrategy,
    GeoStrategy,
    GeoBuildArtifacts,
    HandoffBundle,
    ManagerDecision,
    CoherenceGateReport,
    GateBlock,
    SiteUnderstanding,
    SiteArchitecture,
    ContentRecommendation,
    VisualDirection,
    BrandSpec,
    ToneOfVoice,
)
from conductor.orchestrator import MigrationManager  # noqa: E402


# --- Schema round-trips -----------------------------------------------------

def test_seo_strategy_schema_round_trip():
    """SeoStrategy instantiates, model_dump round-trips, model_validate
    reconstructs equivalent fields."""
    original = SeoStrategy(
        site_slug="example",
        migration_id="20260620_143210",
        target_routes=["/", "/about"],
        meta_description_templates={"/": "{site_name} home"},
        title_templates={"/": "{site_name}"},
        canonical_base="https://example.com",
        internal_link_graph=[{"from_route": "/", "to_route": "/about", "anchor": "About"}],
        hreflang_targets=[],
        sitemap_priority_overrides={"/": 1.0},
        recommendations=[{"route": "/", "note": "primary"}],
    )
    dumped = original.model_dump()
    restored = SeoStrategy(**dumped)
    assert restored.site_slug == "example"
    assert restored.target_routes == ["/", "/about"]
    assert restored.canonical_base == "https://example.com"
    assert restored.sitemap_priority_overrides == {"/": 1.0}
    assert restored.recommendations == [{"route": "/", "note": "primary"}]


def test_geo_strategy_schema_round_trip():
    original = GeoStrategy(
        site_slug="example",
        migration_id="20260620_143210",
        target_first_class_routes=["/about", "/faq"],
        schema_org_types_by_route={
            "/about": ["Organization", "Person"],
            "/faq": ["FAQPage", "BreadcrumbList"],
        },
        llms_txt_outline="# Example\n\n## About\n## FAQ",
        author_block={"name": "Example Team", "role": "Editors"},
        organization_block={"name": "Example", "url": "https://example.com"},
        facts_with_sources=[
            {"claim": "Founded 2020", "source_url": "https://example.com/about",
             "retrieved_at": "2026-06-20"}
        ],
        recommendations=[],
    )
    dumped = original.model_dump()
    restored = GeoStrategy(**dumped)
    assert restored.site_slug == "example"
    assert restored.target_first_class_routes == ["/about", "/faq"]
    assert restored.schema_org_types_by_route["/faq"] == ["FAQPage", "BreadcrumbList"]
    assert restored.llms_txt_outline.startswith("# Example")
    assert restored.author_block["name"] == "Example Team"


def test_geo_build_artifacts_schema_round_trip():
    original = GeoBuildArtifacts(
        site_slug="example",
        migration_id="20260620_143210",
        llms_txt="# Example\n\nbody...",
        robots_txt_ai_stanza="User-agent: GPTBot\nAllow: /\n",
        sitemap_xml_extras=[{"loc": "https://example.com/faq", "priority": 0.7}],
        json_ld_blocks_by_route={
            "/": [{"@context": "https://schema.org", "@type": "WebSite",
                   "name": "Example"}],
        },
        ai_crawler_allowlist=["GPTBot", "ClaudeBot"],
        files_written=["/abs/path/to/llms.txt"],
        content_sha256={"llms.txt": "abc"},
        last_verified_at="2026-06-20T14:32:10Z",
    )
    dumped = original.model_dump()
    restored = GeoBuildArtifacts(**dumped)
    assert restored.site_slug == "example"
    assert restored.llms_txt.startswith("# Example")
    assert "GPTBot" in restored.ai_crawler_allowlist
    assert restored.json_ld_blocks_by_route["/"][0]["@type"] == "WebSite"


def test_handoff_bundle_carries_seo_and_geo_strategy_ids():
    bundle = HandoffBundle(
        bundle_id="b-1",
        migration_id="m-1",
        site_slug="example",
        from_room="planning",
        to_room="forge",
        seo_strategy_id="seo-123",
        geo_strategy_id="geo-456",
    )
    assert bundle.seo_strategy_id == "seo-123"
    assert bundle.geo_strategy_id == "geo-456"


# --- Locked allowlist -------------------------------------------------------

def test_locked_ai_crawlers_has_eleven_entries_and_matches_doc():
    """MigrationManager.LOCKED_AI_CRAWLERS is the canonical 11-entry
    allowlist. Must match docs/GEO_FOR_LLMS.md."""
    crawlers = MigrationManager.LOCKED_AI_CRAWLERS
    assert len(crawlers) == 11, f"expected 11, got {len(crawlers)}: {crawlers}"
    expected = {
        "GPTBot", "ClaudeBot", "Claude-User", "Google-Extended",
        "PerplexityBot", "Applebot-Extended", "anthropic-ai",
        "CCBot", "cohere-ai", "Amazonbot", "Bytespider",
    }
    assert set(crawlers) == expected, f"missing: {expected - set(crawlers)}; extra: {set(crawlers) - expected}"

    # Cross-check against the canonical doc
    doc_path = ROOT / "docs" / "GEO_FOR_LLMS.md"
    if doc_path.exists():
        doc_text = doc_path.read_text(encoding="utf-8")
        for c in expected:
            assert c in doc_text, f"{c} missing from docs/GEO_FOR_LLMS.md"


# --- Planning Room preflight order -----------------------------------------

def test_planning_room_preflight_invokes_seo_and_geo_in_order():
    """Drive the manager loop past planning; verify the spy saw
    seo_specialist and geo_specialist invoked between
    marketing_specialist and ui_designer."""
    decisions = [
        ManagerDecision(action="invoke_persona", persona="architect_specialist", reason="scraper_complete"),
        ManagerDecision(action="invoke_persona", persona="marketing_specialist", reason="architect_complete"),
        ManagerDecision(action="invoke_persona", persona="seo_specialist", reason="marketing_complete"),
        ManagerDecision(action="invoke_persona", persona="geo_specialist", reason="seo_complete"),
        ManagerDecision(action="invoke_persona", persona="ui_designer", reason="geo_complete"),
        ManagerDecision(action="complete", reason="planning done"),
        ManagerDecision(action="complete", reason="forge loop stub terminate"),
    ]
    mgr = _StubMgrPhaseE(decisions)
    # Stub the planner gate to pass at all times.
    mgr._gate_should_pass = True

    import os
    import gc
    old_cwd = os.getcwd()
    try:
        # ignore_cleanup_errors because the MigrationManager instance
        # keeps an open SQLite connection that Windows won't release
        # until the next GC pass after the test ends.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            os.chdir(tmp)
            # Pre-populate memory dirs so the handoff ceremony doesn't crash
            # when trying to resolve artifact IDs.
            _stub_artifact_disk_phase_e(mgr, "example")
            result = mgr.run({
                "url": "https://example.com",
                "platform": "generic",
                "site_name": "example",
                "migration_id": "m-phase-e-1",
                "max_manager_iterations": 25,
            })
            # Capture the invoke log BEFORE we drop the manager so the
            # assertions below can read it.
            planning_log = list(mgr._invoke_log[:6])
            # Force-close the manager's DB connections so the tempdir
            # cleanup can remove elyra_memory.db on Windows.
            try:
                if hasattr(mgr, "memory") and hasattr(mgr.memory, "db"):
                    if hasattr(mgr.memory.db, "close"):
                        mgr.memory.db.close()
                if hasattr(mgr, "memory_client"):
                    if hasattr(mgr.memory_client, "close"):
                        mgr.memory_client.close()
            except Exception:
                pass
            del mgr
            gc.collect()
    finally:
        os.chdir(old_cwd)

    # The seeded decision invokes scraper_specialist first. Then the
    # canned decisions drive the rest in order. Planning invoke log:
    # ["scraper", "architect", "marketing", "seo", "geo", "designer"].
    assert planning_log == [
        "scraper", "architect", "marketing", "seo", "geo", "designer",
    ], f"unexpected planning invoke log: {planning_log}"

    # And ui_designer ("designer") was invoked AFTER seo + geo.
    assert "seo" in planning_log
    assert "geo" in planning_log
    assert planning_log.index("seo") < planning_log.index("designer")
    assert planning_log.index("geo") < planning_log.index("designer")


# --- _run_polish_checks (build_quality_gate extension) ---------------------

def _write_seo_strategy(site_slug: str, migration_id: str, target_routes):
    """Helper: drop a SeoStrategy into memory/seo_strategies/<id>.json."""
    seo = SeoStrategy(
        site_slug=site_slug,
        migration_id=migration_id,
        target_routes=target_routes,
    )
    seo_dir = Path("memory/seo_strategies")
    seo_dir.mkdir(parents=True, exist_ok=True)
    seo_id = "seo-test"
    (seo_dir / f"{seo_id}.json").write_text(
        json.dumps(seo.model_dump()), encoding="utf-8"
    )
    return seo_id


def _write_geo_build(site_slug: str, migration_id: str, *, allowlist=None, blocks=None):
    geo = GeoBuildArtifacts(
        site_slug=site_slug,
        migration_id=migration_id,
        ai_crawler_allowlist=allowlist or [],
        json_ld_blocks_by_route=blocks or {},
    )
    geo_dir = Path("memory/geo_builds")
    geo_dir.mkdir(parents=True, exist_ok=True)
    geo_id = "geo-test"
    (geo_dir / f"{geo_id}.json").write_text(
        json.dumps(geo.model_dump()), encoding="utf-8"
    )
    return geo_id


def test_polish_checks_fail_on_missing_llms_txt():
    with tempfile.TemporaryDirectory() as tmp:
        site_dir = Path(tmp) / "example"
        site_dir.mkdir()
        # No llms.txt, no SEO strategy, no GEO build -> up to 4 gates fire
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            gaps = MigrationManager._run_polish_checks(site_dir)
        finally:
            os.chdir(old_cwd)
        gap_ids = [g["gap_id"] for g in gaps]
        assert "polish.llms_txt_missing" in gap_ids


def test_polish_checks_fail_on_incomplete_crawler_allowlist():
    with tempfile.TemporaryDirectory() as tmp:
        site_dir = Path(tmp) / "example"
        site_dir.mkdir()
        (site_dir / "llms.txt").write_text("# x\nbody", encoding="utf-8")
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            # Only one crawler in the allowlist
            _write_geo_build(
                site_slug="example",
                migration_id="m",
                allowlist=["GPTBot"],
                blocks={
                    "/": [{"@context": "https://schema.org", "@type": "WebSite"}],
                },
            )
            gaps = MigrationManager._run_polish_checks(site_dir)
        finally:
            os.chdir(old_cwd)
        gap_ids = [g.get("gap_id") for g in gaps]
        assert "polish.ai_crawler_allowlist_incomplete" in gap_ids
        # The target_persona is set so route_back dispatches correctly.
        gap = next(g for g in gaps if g.get("gap_id") == "polish.ai_crawler_allowlist_incomplete")
        assert gap["target_persona"] == "geo_specialist"
        assert gap["severity"] == "high"


def test_polish_checks_pass_on_valid_artifacts():
    """When llms.txt is present, SeoStrategy + GeoBuildArtifacts are
    fully populated, the polish checks return an empty list."""
    with tempfile.TemporaryDirectory() as tmp:
        site_dir = Path(tmp) / "example"
        site_dir.mkdir()
        (site_dir / "llms.txt").write_text("# x\nbody", encoding="utf-8")

        # Render HTML with one meta description per targeted route
        for route in ["/", "/about"]:
            if route == "/":
                page = site_dir / "index.html"
            else:
                page = site_dir / route.strip("/") / "index.html"
                page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                f"<html><head><meta name=\"description\" content=\"d\"></head></html>",
                encoding="utf-8",
            )

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            _write_seo_strategy(
                site_slug="example",
                migration_id="m",
                target_routes=["/", "/about"],
            )
            _write_geo_build(
                site_slug="example",
                migration_id="m",
                allowlist=list(MigrationManager.LOCKED_AI_CRAWLERS),
                blocks={
                    "/": [{"@context": "https://schema.org", "@type": "WebSite"}],
                },
            )
            gaps = MigrationManager._run_polish_checks(site_dir)
        finally:
            os.chdir(old_cwd)
        assert gaps == [], f"expected no gaps, got: {gaps}"


# --- Test stubs ------------------------------------------------------------

def _stub_artifact_disk_phase_e(mgr, site_slug):
    """Pre-populate the on-disk artifact stores the handoff ceremony reads."""
    base = Path("memory")
    (base / "site_understandings").mkdir(parents=True, exist_ok=True)
    (base / "site_understandings" / "su-1.json").write_text("{}")
    (base / "site_architectures").mkdir(parents=True, exist_ok=True)
    (base / "site_architectures" / "sa-1.json").write_text("{}")
    (base / "site_recommendations").mkdir(parents=True, exist_ok=True)
    (base / "site_recommendations" / "cr-1.json").write_text("{}")
    vs_dir = base / "visual_specs" / site_slug
    vs_dir.mkdir(parents=True, exist_ok=True)
    (vs_dir / "vd-1.json").write_text("{}")
    (base / "seo_strategies").mkdir(parents=True, exist_ok=True)
    (base / "seo_strategies" / "seo-1.json").write_text("{}")
    (base / "geo_strategies").mkdir(parents=True, exist_ok=True)
    (base / "geo_strategies" / "geo-1.json").write_text("{}")


class _StubMgrPhaseE(MigrationManager):
    """MigrationManager with stubbed persona invocation + planning gate.

    Used by test_planning_room_preflight_invokes_seo_and_geo_in_order to
    drive the manager loop without spawning Kilo subprocesses.
    """

    def __init__(self, decisions):
        super().__init__(db_path=":memory:")
        self._decisions = list(decisions)
        self._decision_idx = 0
        self._invoke_log: list = []
        self._gate_should_pass = False
        self._gate_call_count = 0

    def _consult_manager_persona(self, *a, **kw):
        if self._decision_idx >= len(self._decisions):
            raise AssertionError(
                f"Manager loop exceeded canned decisions ({len(self._decisions)})"
            )
        d = self._decisions[self._decision_idx]
        self._decision_idx += 1
        return d

    def _invoke_persona(self, persona, task_context, artifacts, site_slug, migration_id):
        self._invoke_log.append(persona)
        # Return real Pydantic artifacts per persona so the handoff
        # ceremony (which inspects brand_spec, confidence, etc.)
        # can extract the fields it needs without crashing.
        if persona == "scraper":
            artifact = SiteUnderstanding(
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
                reasoning_trace=["stub"],
            )
        elif persona == "architect":
            artifact = SiteArchitecture(
                source_url="https://example.com",
                target_stack={"framework": "nextjs"},
                pages=[],
                components=[],
                confidence=0.85,
                reasoning_trace=["stub"],
            )
        elif persona == "marketing":
            artifact = ContentRecommendation(
                source_url="https://example.com",
                site_name="example",
                chosen_variant="A",
                variants=[],
                final_rationale="stub",
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
        elif persona == "designer":
            artifact = VisualDirection(
                primary_change="No visual evolution",
                rationale="Stub for test",
                stitch_status="unavailable",
            )
        elif persona == "seo":
            artifact = SeoStrategy(
                site_slug="example",
                migration_id=task_context.get("migration_id") or "m-phase-e-1",
            )
        elif persona == "geo":
            # Planning pass — the stub never reaches the forge pass.
            artifact = GeoStrategy(
                site_slug="example",
                migration_id=task_context.get("migration_id") or "m-phase-e-1",
            )
        else:
            artifact = MagicMock(name=f"artifact_for_{persona}")
        return {
            "success": True,
            "artifact": artifact,
            "gaps": [],
        }

    def _run_planning_coherence_gate(self, artifacts, gaps_logged):
        self._gate_call_count += 1
        # Always pass — this test focuses on dispatch order, not gate logic.
        return CoherenceGateReport(
            gate_name="planning_coherence_gate",
            passed=True,
            blocking=[],
            warnings=[],
            waivers=[],
            artifact_coverage={a: True for a in (
                "site_understanding", "site_architecture",
                "content_recommendation", "visual_direction",
            )},
            fidelity_score=0.85,
            fidelity_threshold=0.7,
        )

    def _run_quality_gates(self, site_dir, re_run_impeccable=False):
        return {"overall_passed": True}