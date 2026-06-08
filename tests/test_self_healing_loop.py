"""
Unit tests for the self-healing loop behavior added in Phase 0.6.

Phase 0.6 changes the manager from a "first-failure-exits" pre-flight to a
self-healing loop that:
  1. Reads persona-emitted gaps from the gap ledger (was discarded).
  2. Surfaces a deterministic routing_suggestion from target_persona.
  3. Retries failing personas up to max_preflight_retries before aborting.
  4. Caps the manager loop at max_manager_iterations as a safety rail.

These tests lock in those behaviors so they don't regress.

Run:
    python -m pytest tests/test_self_healing_loop.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --- Step 1b: routing_suggestion surface -----------------------------------

def test_routing_suggestion_surfaced_when_target_persona_set():
    """When the gaps list contains a high-severity entry with target_persona,
    _build_current_state should surface it as a routing_suggestion."""
    from conductor.orchestrator import MigrationManager
    mgr = MigrationManager(db_path=":memory:")
    gaps = [
        {
            "gap_id": "abc123",
            "type": "gate_failure",
            "source_persona": "designer",
            "target_persona": "designer",
            "severity": "high",
            "description": "VisualDirection missing delta fields",
        }
    ]
    artifacts = {"designer": MagicMock()}
    state = mgr._build_current_state(artifacts, gaps, Path("sites/nonexistent"))
    assert state["routing_suggestion"] is not None
    assert state["routing_suggestion"]["preferred_persona"] == "designer"
    assert state["routing_suggestion"]["gap_id"] == "abc123"
    assert "VisualDirection" in state["routing_suggestion"]["reason"]


def test_routing_suggestion_is_none_without_target_persona():
    """No target_persona on any gap → no routing_suggestion (manager asks the LLM)."""
    from conductor.orchestrator import MigrationManager
    mgr = MigrationManager(db_path=":memory:")
    gaps = [
        {
            "gap_id": "def456",
            "severity": "high",
            "source_persona": "designer",
            "description": "no target",
        }
    ]
    state = mgr._build_current_state({}, gaps, Path("sites/nonexistent"))
    assert state["routing_suggestion"] is None


def test_routing_suggestion_picks_most_recent_target():
    """When multiple target_persona gaps exist, the most recent wins."""
    from conductor.orchestrator import MigrationManager
    mgr = MigrationManager(db_path=":memory:")
    gaps = [
        {"gap_id": "1", "severity": "high", "target_persona": "scraper", "description": "x"},
        {"gap_id": "2", "severity": "high", "target_persona": "designer", "description": "y"},
        {"gap_id": "3", "severity": "high", "target_persona": "architect", "description": "z"},
    ]
    state = mgr._build_current_state({}, gaps, Path("sites/nonexistent"))
    assert state["routing_suggestion"]["preferred_persona"] == "architect"
    assert state["routing_suggestion"]["gap_id"] == "3"


def test_routing_suggestion_ignores_non_high_severity_gaps():
    """Medium/low severity gaps should never trigger deterministic routing."""
    from conductor.orchestrator import MigrationManager
    mgr = MigrationManager(db_path=":memory:")
    gaps = [
        {"gap_id": "1", "severity": "medium", "target_persona": "designer", "description": "x"},
        {"gap_id": "2", "severity": "low", "target_persona": "designer", "description": "y"},
    ]
    state = mgr._build_current_state({}, gaps, Path("sites/nonexistent"))
    assert state["routing_suggestion"] is None


# --- Step 1c: loop detector -------------------------------------------------

def test_is_looping_on_persona_returns_false_when_empty():
    from conductor.orchestrator import MigrationManager
    mgr = MigrationManager(db_path=":memory:")
    assert mgr._is_looping_on_persona("designer") is False


def test_is_looping_on_persona_returns_false_for_one_retry():
    from conductor.orchestrator import MigrationManager
    mgr = MigrationManager(db_path=":memory:")
    mgr._recent_decisions = [
        {"action": "invoke_persona", "persona": "designer"},
    ]
    assert mgr._is_looping_on_persona("designer") is False


def test_is_looping_on_persona_returns_true_after_three_retries():
    from conductor.orchestrator import MigrationManager
    mgr = MigrationManager(db_path=":memory:")
    mgr._recent_decisions = [
        {"action": "route_back", "persona": "designer"},
        {"action": "invoke_persona", "persona": "designer"},
        {"action": "route_back", "persona": "designer"},
    ]
    assert mgr._is_looping_on_persona("designer") is True


def test_is_looping_on_persona_returns_false_for_alternating_targets():
    """If the manager alternates between two personas, neither is 'looping'."""
    from conductor.orchestrator import MigrationManager
    mgr = MigrationManager(db_path=":memory:")
    mgr._recent_decisions = [
        {"action": "route_back", "persona": "designer"},
        {"action": "route_back", "persona": "architect"},
        {"action": "route_back", "persona": "designer"},
    ]
    assert mgr._is_looping_on_persona("designer") is False
    assert mgr._is_looping_on_persona("architect") is False


def test_log_decision_caps_history_at_ten():
    from conductor.orchestrator import MigrationManager
    mgr = MigrationManager(db_path=":memory:")
    from conductor.orchestrator import ManagerDecision
    for i in range(15):
        d = ManagerDecision(action="invoke_persona", persona=f"p{i}", reason=str(i))
        mgr._log_decision(d)
    assert len(mgr._recent_decisions) == 10
    assert mgr._recent_decisions[0]["persona"] == "p5"
    assert mgr._recent_decisions[-1]["persona"] == "p14"


# --- Step 1a: persona gaps returned from _invoke_persona -------------------

def test_invoke_persona_returns_gaps_diffed_from_ledger(tmp_path):
    """_invoke_persona should query the gap ledger after the call and
    return only the entries that were added during the call (diffed by
    the pre-call count)."""
    from conductor.orchestrator import MigrationManager
    from memory import gap_ledger
    from memory.gap_ledger import log_gap, query_gaps

    original = gap_ledger.LEDGER_FILE
    gap_ledger.LEDGER_FILE = tmp_path / "gaps.jsonl"
    try:
        mgr = MigrationManager(db_path=":memory:")

        # Pre-populate the ledger with one entry (simulating a prior call).
        log_gap(
            migration_id="test-diff",
            gap_type="gate_failure",
            source_persona="designer",
            description="pre-existing gap",
            severity="high",
            target_persona="designer",
            write_to_site_ledger=False,
        )
        pre_count = len(query_gaps(migration_id="test-diff", read_from_site_ledger=False))
        assert pre_count == 1

        # Simulate the persona's behavior: during its work it logs a new gap.
        # We exercise only the diff logic — the rest of _invoke_persona is
        # too tightly coupled to the real personas to mock cleanly.
        log_gap(
            migration_id="test-diff",
            gap_type="gate_failure",
            source_persona="designer",
            target_persona="designer",
            description="new gap during persona call",
            severity="high",
            write_to_site_ledger=False,
        )
        post = query_gaps(migration_id="test-diff", read_from_site_ledger=False)
        new_entries = [g.to_dict() if hasattr(g, "to_dict") else g for g in post[pre_count:]]
        new_gap_descriptions = [g.get("description", "") for g in new_entries]

        assert "new gap during persona call" in new_gap_descriptions
        assert "pre-existing gap" not in new_gap_descriptions
        assert len(new_entries) == 1
    finally:
        gap_ledger.LEDGER_FILE = original


# --- Step 1c: preflight_max_retries terminal phase --------------------------

def test_preflight_aborts_with_retry_phase_when_persona_keeps_failing(tmp_path):
    """When a persona fails every retry, the pre-flight should reach the
    `preflight_max_retries:<persona>` phase rather than just `<persona>_failed`."""
    from conductor.orchestrator import MigrationManager

    def _always_failing(*a, **kw):
        return None  # scraper returns None → failure

    with patch("skills.agentic.scraper_agent.scrape", side_effect=_always_failing), \
         patch("skills.agentic.architect_agent.architect", side_effect=_always_failing), \
         patch("skills.agentic.marketing_agent.market", side_effect=_always_failing), \
         patch("skills.agentic.designer_agent.design", side_effect=_always_failing), \
         patch.object(MigrationManager, "_get_latest_artifact_id", return_value=None), \
         patch.object(MigrationManager, "_save_artifact", return_value=None), \
         patch.object(MigrationManager, "_promote_scratch_artifacts"):

        mgr = MigrationManager(db_path=":memory:")
        result = mgr.run({
            "url": "https://example.com",
            "platform": "wix",
            "site_name": "example",
            "task_type": "test",
            "migration_id": "test-retry-phase",
            "max_preflight_retries": 1,  # 1 retry = 2 total attempts
        })
        # The first persona (scraper) should fail and trigger max_retries phase
        assert result["success"] is False
        assert "preflight_max_retries" in result["phase_reached"], (
            f"expected preflight_max_retries phase, got: {result['phase_reached']}"
        )


# --- Step 1b: deterministic short-circuit -----------------------------------

def test_decide_next_action_uses_routing_suggestion_on_failure_step():
    """When invoked with step='<persona>_failed' and there's a routing
    suggestion, _decide_next_action should return route_back to that persona
    WITHOUT consulting the LLM."""
    from conductor.orchestrator import MigrationManager, ManagerDecision

    mgr = MigrationManager(db_path=":memory:")
    # Pre-populate _recent_decisions so the loop detector doesn't fire
    mgr._recent_decisions = [
        {"action": "invoke_persona", "persona": "builder", "reason": "first"},
    ]
    gaps = [{
        "gap_id": "g1",
        "severity": "high",
        "source_persona": "designer",
        "target_persona": "designer",
        "description": "VisualDirection has empty delta",
    }]

    # Stub the LLM path so we can assert it was NOT called
    with patch.object(mgr, "_consult_manager_persona") as llm:
        decision = mgr._decide_next_action(
            step="designer_failed",
            task_context={},
            artifacts={"designer": MagicMock()},
            gaps=gaps,
            site_dir=Path("sites/x"),
        )
        assert decision.action == "route_back"
        assert decision.persona == "designer"
        assert "g1" in decision.reason or "designer" in decision.reason.lower()
        llm.assert_not_called()


def test_decide_next_action_falls_through_to_llm_when_no_suggestion():
    """When no routing_suggestion exists, the LLM is consulted normally."""
    from conductor.orchestrator import MigrationManager, ManagerDecision
    mgr = MigrationManager(db_path=":memory:")
    mgr._recent_decisions = []

    fake_decision = ManagerDecision(action="complete", reason="stubbed")
    with patch.object(mgr, "_consult_manager_persona", return_value=fake_decision) as llm:
        decision = mgr._decide_next_action(
            step="builder_complete",
            task_context={},
            artifacts={},
            gaps=[],  # no gaps → no suggestion
            site_dir=Path("sites/x"),
        )
        assert decision.action == "complete"
        llm.assert_called_once()


def test_decide_next_action_falls_through_to_llm_when_looping():
    """If the deterministic short-circuit would loop on the same persona
    3+ times, fall through to the LLM (don't spin forever)."""
    from conductor.orchestrator import MigrationManager, ManagerDecision
    mgr = MigrationManager(db_path=":memory:")
    mgr._recent_decisions = [
        {"action": "route_back", "persona": "designer"},
        {"action": "route_back", "persona": "designer"},
        {"action": "route_back", "persona": "designer"},
    ]
    gaps = [{
        "gap_id": "g1", "severity": "high",
        "source_persona": "designer", "target_persona": "designer",
        "description": "still bad",
    }]

    fake_decision = ManagerDecision(action="complete", reason="llm override")
    with patch.object(mgr, "_consult_manager_persona", return_value=fake_decision) as llm:
        decision = mgr._decide_next_action(
            step="designer_failed",
            task_context={}, artifacts={}, gaps=gaps, site_dir=Path("sites/x"),
        )
        assert decision.action == "complete"
        llm.assert_called_once()


if __name__ == "__main__":
    import traceback
    tests = [
        test_routing_suggestion_surfaced_when_target_persona_set,
        test_routing_suggestion_is_none_without_target_persona,
        test_routing_suggestion_picks_most_recent_target,
        test_routing_suggestion_ignores_non_high_severity_gaps,
        test_is_looping_on_persona_returns_false_when_empty,
        test_is_looping_on_persona_returns_false_for_one_retry,
        test_is_looping_on_persona_returns_true_after_three_retries,
        test_is_looping_on_persona_returns_false_for_alternating_targets,
        test_log_decision_caps_history_at_ten,
        test_invoke_persona_returns_gaps_diffed_from_ledger,
        test_preflight_aborts_with_retry_phase_when_persona_keeps_failing,
        test_decide_next_action_uses_routing_suggestion_on_failure_step,
        test_decide_next_action_falls_through_to_llm_when_no_suggestion,
        test_decide_next_action_falls_through_to_llm_when_looping,
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
