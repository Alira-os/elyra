"""
Tests for Phase C — Manager-driven planning loop.

Verifies that the procedural preflight has been collapsed into a single
LLM-driven manager loop, and that the manager can read a failing
Planning Coherence Gate and route_back to the responsible persona.

Run:
    python -m pytest tests/test_manager_loop.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import (  # noqa: E402
    CoherenceGateReport,
    GateBlock,
    HandoffBundle,
    ManagerDecision,
    SiteUnderstanding,
    SiteArchitecture,
    ContentRecommendation,
    VisualDirection,
    BrandSpec,
    ToneOfVoice,
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


def _make_site_architecture(confidence: float = 0.85) -> SiteArchitecture:
    return SiteArchitecture(
        source_url="https://example.com",
        target_stack={"framework": "nextjs", "styling": "tailwind"},
        pages=[],
        components=[],
        confidence=confidence,
        reasoning_trace=["Chose Next.js based on Wix structure"],
    )


def _make_content_recommendation() -> ContentRecommendation:
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


class _StubMgr(MigrationManager):
    """MigrationManager with stubbed persona invocation, planning gate,
    and a canned sequence of manager decisions.

    The forge-room preflight still runs (brief: do not change the forge
    room), so we stub its quality-gate runner too — but the FORGE manager
    loop never fires in this test because planning emits `complete`
    first and the forge room's loop detector would otherwise see no
    artifacts. We disable the forge preflight entirely by pre-populating
    `artifacts` (no — that breaks the planning test). Instead, we
    intercept `_invoke_persona` to be a no-op for forge personas.
    """

    def __init__(self, decisions):
        super().__init__(db_path=":memory:")
        self._decisions = list(decisions)
        self._decision_idx = 0
        self._invoke_log: list[str] = []
        # The planning gate is called multiple times. The default gate
        # fails with low fidelity on the first 4 turns (so the manager
        # will route_back) and passes on the 5th. Tests can override
        # _gate_should_pass to control this.
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
        # Return a real Pydantic artifact per persona so the handoff
        # ceremony can extract brand_spec / reasoning_trace / etc.
        if persona == "scraper":
            artifact = _make_site_understanding()
        elif persona == "architect":
            artifact = _make_site_architecture()
        elif persona == "marketing":
            artifact = _make_content_recommendation()
        elif persona == "designer":
            artifact = _make_visual_direction()
        else:
            artifact = MagicMock(name=f"artifact_for_{persona}")
        return {
            "success": True,
            "artifact": artifact,
            "gaps": [],
        }

    def _run_planning_coherence_gate(self, artifacts, gaps_logged):
        self._gate_call_count += 1
        # Build a fake gate report. We expose the persona-as-string map
        # so tests can verify route_back dispatch.
        blocking: list[GateBlock] = []
        # Coverage is computed from `artifacts` keys. The test stubs
        # _invoke_persona to ALWAYS succeed, so after each turn the
        # artifact for the just-invoked persona appears. We translate
        # long-name persona keys back to artifact names.
        _ARTIFACT_KEY_TO_ARTIFACT_NAME = {
            "scraper_specialist": "site_understanding",
            "architect_specialist": "site_architecture",
            "marketing_specialist": "content_recommendation",
            "ui_designer": "visual_direction",
        }
        covered = {_ARTIFACT_KEY_TO_ARTIFACT_NAME.get(k) for k in artifacts.keys()}
        all_artifacts = {
            "site_understanding",
            "site_architecture",
            "content_recommendation",
            "visual_direction",
        }
        for art in sorted(all_artifacts - covered):
            persona_for_fix = {
                "site_understanding": "scraper_specialist",
                "site_architecture": "architect_specialist",
                "content_recommendation": "marketing_specialist",
                "visual_direction": "ui_designer",
            }[art]
            blocking.append(
                GateBlock(
                    persona=persona_for_fix,
                    reason=f"missing planning artifact: {art}",
                    severity="high",
                )
            )
        # Simulate fidelity failure for the architect on the first run:
        # the gate blocks the architect persona until the manager routes
        # back to it.
        if not self._gate_should_pass and "architect_specialist" in artifacts and self._gate_call_count < 5:
            blocking.append(
                GateBlock(
                    persona="architect_specialist",
                    reason="fidelity_score=0.55 below threshold 0.70 — re-run architect with stronger grounding",
                    gap_id="fid-1",
                    severity="high",
                )
            )
        passed = len(blocking) == 0
        return CoherenceGateReport(
            gate_name="planning_coherence_gate",
            passed=passed,
            blocking=blocking,
            warnings=[],
            waivers=[],
            artifact_coverage={a: a in covered for a in all_artifacts},
            fidelity_score=0.85 if self._gate_should_pass else 0.55,
            fidelity_threshold=0.7,
        )

    def _run_quality_gates(self, site_dir, re_run_impeccable=False):
        # Forge preflight never runs in this test (we complete before
        # reaching it), but if it does, return a pass.
        return {"overall_passed": True}


def _stub_artifact_disk_for(mgr, site_slug):
    """Pre-populate the on-disk artifact stores the handoff ceremony reads.

    Without these the ceremony can't resolve artifact IDs and the bundle
    persistence fails. We mirror what test_phase1_wiring.ceremony_produces
    does.
    """
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


def test_manager_loop_handles_gate_failure_via_route_back(tmp_path):
    """7-turn sequence:
        1. invoke scraper
        2. invoke architect  (gate: low fidelity, missing visual_direction)
        3. invoke marketing (gate: missing visual_direction)
        4. invoke ui_designer (gate: fidelity still bad)
        5. route_back to architect (suggested_route_back)
        6. invoke architect (still failing — but we override the gate to
           pass so the manager can return complete next turn)
        7. complete

    We verify the manager dispatched `route_back` to architect_specialist
    AND that the loop eventually terminates.
    """
    decisions = [
        # Note: the manager loop's FIRST decision is seeded in code
        # (scraper_specialist, from PLANNING_ROOM.preflight_order[0]).
        # The stub is called for the SECOND decision onward — i.e. what
        # the manager returns AFTER the first persona completes.
        ManagerDecision(
            action="invoke_persona",
            persona="architect_specialist",
            reason="scraper_complete (manager picks next)",
        ),
        ManagerDecision(
            action="invoke_persona",
            persona="marketing_specialist",
            reason="architect_complete",
        ),
        ManagerDecision(
            action="invoke_persona",
            persona="ui_designer",
            reason="marketing_complete",
        ),
        ManagerDecision(
            action="route_back",
            persona="architect_specialist",
            reason="gate blocked: low fidelity",
            gap_context="• Re-derive SiteArchitecture with stronger grounding",
        ),
        ManagerDecision(
            action="invoke_persona",
            persona="architect_specialist",
            reason="architect_routed_back",
        ),
        ManagerDecision(
            action="complete",
            reason="all artifacts present, gate passed",
        ),
        # The legacy forge-room manager loop also runs (Phase C did not
        # touch the forge room). It needs at least one decision to
        # terminate; we give it `complete` so the test exits cleanly.
        ManagerDecision(
            action="complete",
            reason="forge loop: stub terminate",
        ),
    ]
    mgr = _StubMgr(decisions)

    # After the route_back, force the gate to pass on the next call so
    # the manager can return complete. _StubMgr._run_planning_coherence_gate
    # honors _gate_should_pass.
    original_gate = mgr._run_planning_coherence_gate
    call_count = {"n": 0}

    def gated_gate(artifacts, gaps):
        call_count["n"] += 1
        if call_count["n"] >= 6:
            mgr._gate_should_pass = True
        return original_gate(artifacts, gaps)

    mgr._run_planning_coherence_gate = gated_gate

    # Work in tmp_path so memory/ writes don't pollute the repo.
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        # The handoff ceremony reads artifact IDs from on-disk
        # memory/ stores. Pre-populate the directories so the
        # ceremony can resolve them.
        _stub_artifact_disk_for(mgr, "example")
        result = mgr.run({
            "url": "https://example.com",
            "platform": "generic",
            "site_name": "example",
            "migration_id": "m-phase-c-1",
            # Skip the (procedural) forge preflight by providing a flag
            # the manager loop respects — but our stubbed manager
            # returns `complete` before reaching the forge, so this
            # is belt-and-braces.
            "max_manager_iterations": 25,
        })
    finally:
        os.chdir(old_cwd)

    # The manager loop should have terminated via `complete`.
    assert result["phase_reached"] == "complete", (
        f"expected complete, got {result['phase_reached']}: {result}"
    )
    # All four planning artifacts should be in the artifacts dict.
    planning = ["scraper_specialist", "architect_specialist", "marketing_specialist", "ui_designer"]
    for p in planning:
        assert p in result["artifacts"], f"missing planning artifact: {p}"

    # The manager's 5th decision was `route_back` to architect_specialist.
    # We verify the dispatch happened by checking _invoke_log.
    # The planning manager loop produces the first 6 entries; the
    # legacy forge-room preflight adds 5 more (deploy_specialist, etc.)
    # which we don't assert about here — the planning manager loop's
    # dispatch is what Phase C is responsible for.
    planning_log = mgr._invoke_log[:6]
    assert planning_log == [
        "scraper", "architect", "marketing", "designer", "architect", "architect",
    ], f"unexpected planning invoke log: {planning_log}"

    # The handoff bundle was produced.
    assert result["handoff_bundle"] is not None, "handoff bundle missing"

    # The Coherence Gate report was attached.
    assert result["coherence_gate"] is not None


def test_manager_loop_first_decision_is_first_preflight_persona():
    """On the first turn, the seeded decision should be the first
    persona in PLANNING_ROOM.preflight_order (= scraper_specialist)."""
    decisions = [
        ManagerDecision(action="complete", reason="stub"),
    ]
    mgr = _StubMgr(decisions)
    assert mgr.PLANNING_ROOM.preflight_order[0] == "scraper_specialist"
    # Inspect what the orchestrator's run() seeds as the first decision:
    # the orchestrator sets it directly (not via _consult_manager_persona),
    # so we instead verify the value the loop uses by checking
    # PLANNING_ROOM.preflight_order.
    # A more direct check: trace events.
    mgr.run({
        "url": "https://example.com",
        "platform": "generic",
        "site_name": "ex",
        "migration_id": "m-seed-1",
    })
    seed_event = next(
        (e for e in mgr.trace if e["event"] == "decision"),
        None,
    )
    assert seed_event is not None
    assert seed_event["payload"]["action"] == "invoke_persona"
    assert seed_event["payload"]["persona"] == "scraper_specialist"


def test_gate_blocking_is_structured_gateblock_list():
    """Phase C sanity: the gate's blocking field carries structured
    GateBlock records, not prose strings."""
    m = MigrationManager(db_path=":memory:")
    artifacts = {
        "scraper": _make_site_understanding(),
        # architect / marketing / designer missing
    }
    report = m._run_planning_coherence_gate(artifacts, gaps_logged=[])
    assert report.passed is False
    assert all(isinstance(b, GateBlock) for b in report.blocking)
    # The missing artifacts map to the right personas.
    personas = {b.persona for b in report.blocking}
    assert "architect_specialist" in personas
    assert "marketing_specialist" in personas
    assert "ui_designer" in personas
    # suggested_route_back returns None because multiple personas are blocking.
    assert report.suggested_route_back() is None


def test_gate_suggested_route_back_when_single_persona():
    """If all blocks share one persona, the helper returns that persona."""
    m = MigrationManager(db_path=":memory:")
    # Provide 3 of 4 artifacts, all attributable to ui_designer, so
    # the only blocking persona is ui_designer.
    artifacts = {
        "scraper": _make_site_understanding(),
        "architect": _make_site_architecture(),
        "marketing": _make_content_recommendation(),
        # designer missing
    }
    report = m._run_planning_coherence_gate(artifacts, gaps_logged=[])
    assert report.passed is False
    # Only one missing artifact → one blocking persona → suggested_route_back
    # returns that persona.
    assert report.suggested_route_back() == "ui_designer"
