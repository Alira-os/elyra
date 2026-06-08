"""
Unit tests for the Phase 1.0 Room / Steward / CoherenceGateReport /
HandoffBundle schemas.

These tests are intentionally focused on the SHAPE of the schemas (fields,
defaults, round-trip via model_dump) rather than on the orchestrator's
behavior. The schemas are the contract for the next phase; once they're
wired into the orchestrator, those wirings will have their own tests.

Run:
    python -m pytest tests/test_phase1_schemas.py -v
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import (  # noqa: E402
    ManagerDecision,
    Room,
    Steward,
    CoherenceGateReport,
    CoherenceGateWaiver,
    HandoffBundle,
)


# --- ManagerDecision: room + steward fields ------------------------------

def test_manager_decision_room_default_is_none():
    d = ManagerDecision(action="complete")
    assert d.room is None
    assert d.steward is None


def test_manager_decision_accepts_planning_room():
    d = ManagerDecision(action="invoke_persona", persona="designer", room="planning")
    assert d.room == "planning"


def test_manager_decision_accepts_forge_room():
    d = ManagerDecision(action="route_back", persona="builder", room="forge")
    assert d.room == "forge"


def test_manager_decision_rejects_unknown_room():
    """The Literal enum should reject anything outside planning/forge."""
    try:
        ManagerDecision(action="complete", room="qa")
    except Exception:
        return
    raise AssertionError("expected ValidationError for room='qa'")


def test_manager_decision_steward_is_free_text():
    """steward is Optional[str] — any name should be accepted."""
    d = ManagerDecision(action="invoke_persona", steward="architect_specialist")
    assert d.steward == "architect_specialist"


# --- Room ---------------------------------------------------------------

def test_room_contains_persona_helper():
    r = Room(
        name="planning",
        description="test",
        personas=["scraper_specialist", "architect_specialist", "ui_designer"],
        steward="architect_specialist",
    )
    assert r.contains_persona("ui_designer") is True
    assert r.contains_persona("builder") is False


def test_room_rejects_unknown_name():
    """The Literal enum locks the room name to planning/forge."""
    try:
        Room(name="qa", description="x", steward="x")
    except Exception:
        return
    raise AssertionError("expected ValidationError for unknown room name")


def test_room_default_lists_are_empty():
    r = Room(name="planning", description="x", steward="y")
    assert r.personas == []
    assert r.inputs == []
    assert r.outputs == []
    assert r.coherence_gate is None
    assert r.preflight_order == []  # NEW Phase 1.0 field


def test_room_preflight_order_default_is_empty():
    r = Room(name="planning", description="d", steward="x")
    assert r.preflight_order == []


def test_room_ordered_personas_uses_preflight_order():
    r = Room(
        name="planning",
        description="d",
        steward="x",
        personas=["a", "b", "c", "d"],
        preflight_order=["c", "a"],
    )
    assert r.ordered_personas() == ["c", "a", "b", "d"]


def test_room_ordered_personas_falls_back_when_preflight_empty():
    r = Room(
        name="planning", description="d", steward="x",
        personas=["a", "b", "c"],
    )
    assert r.ordered_personas() == ["a", "b", "c"]


def test_room_ordered_personas_dedups():
    """If preflight_order contains a persona not in the room, or a
    duplicate, the result is deduped and in-steward-order."""
    r = Room(
        name="planning", description="d", steward="x",
        personas=["a", "b", "c"],
        preflight_order=["a", "a", "z", "b"],
    )
    assert r.ordered_personas() == ["a", "b", "c"]


def test_room_ordered_personas_empty_everything():
    r = Room(name="planning", description="d", steward="x")
    assert r.ordered_personas() == []


def test_room_round_trips():
    r = Room(
        name="planning",
        description="d",
        personas=["a", "b"],
        steward="architect_specialist",
        inputs=["url"],
        outputs=["site_understanding"],
        coherence_gate="planning_coherence_gate",
    )
    data = r.model_dump()
    r2 = Room.model_validate(data)
    assert r2 == r


# --- Steward -----------------------------------------------------------

def test_steward_required_fields():
    s = Steward(
        name="planning_steward",
        room="planning",
        persona_ref="architect_specialist",
        role_description="Architecture Owner",
    )
    assert s.capabilities == []  # default


def test_steward_capabilities_is_list():
    s = Steward(
        name="x",
        room="planning",
        persona_ref="architect_specialist",
        role_description="x",
        capabilities=["rich_bidirectional_pull", "coherence_gate"],
    )
    assert s.capabilities == ["rich_bidirectional_pull", "coherence_gate"]


# --- CoherenceGateWaiver -----------------------------------------------

def test_waiver_required_fields():
    w = CoherenceGateWaiver(
        field="fidelity_score",
        reason="too minimal",
        owner="architect_specialist",
        risk_level="low",
    )
    assert w.mitigation is None


def test_waiver_rejects_invalid_risk_level():
    """The Literal enum locks risk_level to the four named values."""
    try:
        CoherenceGateWaiver(
            field="x", reason="y", owner="z", risk_level="negligible"
        )
    except Exception:
        return
    raise AssertionError("expected ValidationError for invalid risk_level")


# --- CoherenceGateReport -----------------------------------------------

def test_gate_passed_summarize():
    g = CoherenceGateReport(gate_name="planning", passed=True)
    assert g.summarize() == "PASS"


def test_gate_failed_summarize():
    g = CoherenceGateReport(
        gate_name="planning",
        passed=False,
        blocking=["site_understanding missing"],
        warnings=["stitch unavailable"],
    )
    assert "FAIL" in g.summarize()
    assert "1 blocking" in g.summarize()
    assert "1 warnings" in g.summarize()


def test_gate_with_waivers():
    w = CoherenceGateWaiver(field="fidelity", reason="x", owner="y", risk_level="low")
    g = CoherenceGateReport(gate_name="x", passed=True, waivers=[w])
    assert g.summarize() == "PASS (1 waivers)"


def test_gate_default_threshold_is_0_7():
    g = CoherenceGateReport(gate_name="x", passed=True)
    assert g.fidelity_threshold == 0.7


# --- HandoffBundle -----------------------------------------------------

def test_bundle_minimal_required_fields():
    b = HandoffBundle(
        bundle_id="b1",
        migration_id="m1",
        site_slug="example",
        from_room="planning",
        to_room="forge",
    )
    # Defaults
    assert b.site_understanding_id is None
    assert b.brand_spec is None
    assert b.known_gaps == []
    assert b.coherence_gate is None
    assert b.requires_human_review is False


def test_bundle_to_memory_path():
    b = HandoffBundle(
        bundle_id="b1", migration_id="mig-abc",
        site_slug="example", from_room="planning", to_room="forge",
    )
    assert b.to_memory_path() == "memory/migrations/mig-abc/handoff_bundle.json"


def test_bundle_with_nested_gate_and_gaps():
    w = CoherenceGateWaiver(field="fidelity", reason="x", owner="y", risk_level="low")
    g = CoherenceGateReport(gate_name="planning", passed=True, waivers=[w])
    b = HandoffBundle(
        bundle_id="b1", migration_id="m1", site_slug="example",
        from_room="planning", to_room="forge",
        coherence_gate=g,
        known_gaps=[{"gap_id": "g1", "severity": "medium", "target_persona": "builder"}],
        requires_human_review=True,
        human_review_reason="novel architecture (XState machine)",
    )
    assert b.coherence_gate.passed is True
    assert len(b.coherence_gate.waivers) == 1
    assert b.requires_human_review is True
    assert b.known_gaps[0]["target_persona"] == "builder"


def test_bundle_round_trips():
    b = HandoffBundle(
        bundle_id="b1", migration_id="m1", site_slug="example",
        from_room="planning", to_room="forge",
        brand_spec={"primary_color": "#1E293B"},
        planning_rationale=["Chose Next.js"],
        open_questions=[{"question": "Confirm fonts", "owner": "client", "eta": "2026-06-15", "severity": "low"}],
        success_criteria=["Lighthouse perf > 90"],
    )
    data = b.model_dump()
    b2 = HandoffBundle.model_validate(data)
    assert b2 == b


def test_bundle_rejects_unknown_room_names():
    """The room fields should reject anything outside planning/forge."""
    try:
        HandoffBundle(
            bundle_id="b1", migration_id="m1", site_slug="example",
            from_room="qa", to_room="planning",
        )
    except Exception:
        return
    raise AssertionError("expected ValidationError for from_room='qa'")


if __name__ == "__main__":
    import traceback
    tests = [
        test_manager_decision_room_default_is_none,
        test_manager_decision_accepts_planning_room,
        test_manager_decision_accepts_forge_room,
        test_manager_decision_rejects_unknown_room,
        test_manager_decision_steward_is_free_text,
        test_room_contains_persona_helper,
        test_room_rejects_unknown_name,
        test_room_default_lists_are_empty,
        test_room_round_trips,
        test_steward_required_fields,
        test_steward_capabilities_is_list,
        test_waiver_required_fields,
        test_waiver_rejects_invalid_risk_level,
        test_gate_passed_summarize,
        test_gate_failed_summarize,
        test_gate_with_waivers,
        test_gate_default_threshold_is_0_7,
        test_bundle_minimal_required_fields,
        test_bundle_to_memory_path,
        test_bundle_with_nested_gate_and_gaps,
        test_bundle_round_trips,
        test_bundle_rejects_unknown_room_names,
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
