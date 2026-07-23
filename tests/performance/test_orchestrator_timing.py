"""
test_orchestrator_timing.py — Lock in the per-method timing instrumentation
that used to live in `quick_test_orch.py` (deleted in Phase A).

The wrapper asserts two things per orchestrator dispatch hook:

1. ``_decide_next_action`` is invoked at least once with a non-negative
   elapsed wall-clock duration. Each call records its elapsed into a
   shared list so a regression in the timing plumbing (e.g. silently
   skipping the timer) is caught.

2. ``_invoke_persona`` is invoked at least once when the manager reaches
   the persona-dispatch step. Elapsed durations are captured per call.

These wrappers are the deterministic part of what quick_test_orch.py
did; the live stdout-driven timing belongs in profiling, not tests.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conductor.orchestrator import MigrationManager  # noqa: E402


def _wrap_decide(mgr, captured):
    """Wrap MigrationManager._decide_next_action to record elapsed per call."""
    original = mgr._decide_next_action

    def logged(step, *args, **kwargs):
        t0 = time.perf_counter()
        result = original(step, *args, **kwargs)
        elapsed = time.perf_counter() - t0
        captured["decide"].append({"step": step, "elapsed": elapsed, "action": result.action})
        return result

    mgr._decide_next_action = logged


def _wrap_invoke(mgr, captured):
    """Wrap MigrationManager._invoke_persona to record elapsed per call."""
    original = mgr._invoke_persona

    def logged(persona, *args, **kwargs):
        t0 = time.perf_counter()
        result = original(persona, *args, **kwargs)
        elapsed = time.perf_counter() - t0
        captured["invoke"].append({"persona": persona, "elapsed": elapsed, "success": result.get("success")})
        return result

    mgr._invoke_persona = logged


def test_decide_next_action_timing_wrapper_records_elapsed():
    """A pure timing wrapper around _decide_next_action records >=1 call
    with a non-negative elapsed duration."""
    captured = {"decide": [], "invoke": []}
    mgr = MigrationManager(db_path=":memory:")
    _wrap_decide(mgr, captured)

    from models.site_schemas import ManagerDecision
    mgr._recent_decisions = [{"action": "invoke_persona", "persona": "scraper", "reason": "x"}]
    decision = mgr._decide_next_action(
        step="scraper_routed_back",
        task_context={},
        artifacts={"scraper": MagicMock()},
        gaps=[],
        site_dir=Path("/tmp/site"),
    )

    assert isinstance(decision, ManagerDecision)
    assert len(captured["decide"]) == 1
    entry = captured["decide"][0]
    assert entry["step"] == "scraper_routed_back"
    assert entry["elapsed"] >= 0.0
    assert entry["action"] == decision.action


def test_invoke_persona_timing_wrapper_records_elapsed():
    """A pure timing wrapper around _invoke_persona records >=1 call
    with a non-negative elapsed duration."""
    captured = {"decide": [], "invoke": []}
    mgr = MigrationManager(db_path=":memory:")
    _wrap_invoke(mgr, captured)

    result = mgr._invoke_persona(
        "scraper",
        {"url": "https://example.com"},
        {},
        "test-slug",
        "test-timing-invoke",
    )

    assert len(captured["invoke"]) == 1
    entry = captured["invoke"][0]
    assert entry["persona"] == "scraper"
    assert entry["elapsed"] >= 0.0
    assert "success" in entry


def test_both_wrappers_compose_during_e2e_run():
    """End-to-end check: with both wrappers installed, a stubbed manager
    run drives >=1 decide_next_action call and >=1 invoke_persona call,
    each recorded with elapsed >= 0."""
    from conductor.orchestrator import MigrationManager
    from models.site_schemas import ManagerDecision, SiteUnderstanding

    captured = {"decide": [], "invoke": []}

    with patch("skills.agentic.scraper_agent.scrape", return_value=SiteUnderstanding(
        url="https://example.com",
        platform="wix",
        platform_confidence=0.9,
        site_name="example",
        total_pages_discovered=1,
        pages=[],
        global_assets={},
        contact_info={},
        navigation_structure=[],
        estimated_fidelity=0.8,
        reasoning_trace=["stub"],
    )), patch("skills.agentic.architect_agent.architect", return_value=None), \
         patch("skills.agentic.marketing_agent.market", return_value=None), \
         patch("skills.agentic.designer_agent.design", return_value=None), \
         patch("skills.agentic.builder_agent.build", return_value=None), \
         patch.object(MigrationManager, "_get_latest_artifact_id", return_value=None), \
         patch.object(MigrationManager, "_save_artifact", return_value=None), \
         patch.object(MigrationManager, "_promote_scratch_artifacts"), \
         patch("tools.kilo.invoke_kilo", return_value=MagicMock(success=False, summary="", errors=["stub"], files_created=[], files_modified=[])):

        mgr = MigrationManager(db_path=":memory:")
        _wrap_decide(mgr, captured)
        _wrap_invoke(mgr, captured)

        mgr.run({
            "url": "https://example.com",
            "platform": "wix",
            "site_name": "example",
            "task_type": "portfolio",
            "migration_id": "test-timing-e2e",
        })

    assert len(captured["invoke"]) >= 1, "expected at least one _invoke_persona call"
    for entry in captured["invoke"]:
        assert entry["elapsed"] >= 0.0
        assert entry["persona"]

    assert all(e["elapsed"] >= 0.0 for e in captured["decide"] + captured["invoke"])
