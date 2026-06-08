"""
Unit tests for skills/agentic/remediation.py

This is the experiment the user asked for: compare the dicts shape
(current HandoffBundle.known_gaps) against the Pydantic GapEntry shape
to see which is more ergonomic for remediation.

Result (per skills/agentic/remediation.py run): both produce identical
outcomes. Pydantic *could* surface bad data earlier, but only if
GapEntry is strict enough. Currently it isn't, so dicts are the right
choice for now.

These tests lock in the equivalence so the two paths don't drift.

Run:
    python -m pytest tests/test_remediation_harness.py -v
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory.gap_ledger import GapEntry  # noqa: E402
from models.site_schemas import (  # noqa: E402
    HandoffBundle,
    CoherenceGateReport,
    CoherenceGateWaiver,
)
from skills.agentic.remediation import (  # noqa: E402
    remediate_with_dicts,
    remediate_with_pydantic,
    side_by_side_report,
    RemediationOutcome,
)


def _sample_bundle() -> HandoffBundle:
    return HandoffBundle(
        bundle_id="b1", migration_id="m1", site_slug="example",
        from_room="planning", to_room="forge",
        known_gaps=[
            {"gap_id": "g1", "severity": "medium", "target_persona": "designer",
             "description": "VisualDirection has empty color_delta",
             "suggested_fix": "Re-run designer with explicit color tokens"},
            {"gap_id": "g2", "severity": "high", "target_persona": "builder",
             "description": "BuildManifest missing lighthouse scores",
             "suggested_fix": "Add lighthouse step"},
            {"gap_id": "g3", "severity": "low",
             "description": "No target_persona on this one"},
        ],
    )


# --- Dicts path -------------------------------------------------------------

def test_dicts_path_groups_by_target_persona():
    out = remediate_with_dicts(_sample_bundle(), persona_invoke_fn=None, dry_run=True)
    by_target = {o.target_persona: o.gap_id for o in out}
    assert by_target["designer"] == "g1"
    assert by_target["builder"] == "g2"
    assert by_target["(none)"] == "g3"


def test_dicts_path_dry_run_does_not_invoke():
    invoked = []
    def _invoke(target, context, mid):
        invoked.append((target, context, mid))
        return None
    out = remediate_with_dicts(_sample_bundle(), persona_invoke_fn=_invoke, dry_run=True)
    assert invoked == []  # dry_run skips the call
    assert all(o.notes.startswith("[dry_run]") for o in out if o.target_persona != "(none)")


def test_dicts_path_resolved_when_no_new_gap():
    def _resolve(target, context, mid):
        return None  # persona fixed it
    out = remediate_with_dicts(_sample_bundle(), persona_invoke_fn=_resolve, dry_run=False)
    designer_outcome = [o for o in out if o.gap_id == "g1"][0]
    assert designer_outcome.resolved is True
    assert designer_outcome.new_gap_emitted is False


def test_dicts_path_unresolved_when_new_gap_returned():
    def _emit_gap(target, context, mid):
        return {"description": "still broken", "severity": "medium"}
    out = remediate_with_dicts(_sample_bundle(), persona_invoke_fn=_emit_gap, dry_run=False)
    builder_outcome = [o for o in out if o.gap_id == "g2"][0]
    assert builder_outcome.resolved is False
    assert builder_outcome.new_gap_emitted is True


# --- Pydantic path ---------------------------------------------------------

def test_pydantic_path_groups_by_target_persona():
    bundle = _sample_bundle()
    pyd_gaps = [GapEntry(**g) for g in bundle.known_gaps]
    out = remediate_with_pydantic(pyd_gaps, persona_invoke_fn=None, dry_run=True)
    by_target = {o.target_persona: o.gap_id for o in out}
    assert by_target["designer"] == "g1"
    assert by_target["builder"] == "g2"
    assert by_target["(none)"] == "g3"


def test_pydantic_path_uses_attribute_access():
    """Pydantic gives us .gap_id, .description, etc. — verify access works."""
    bundle = _sample_bundle()
    pyd_gaps = [GapEntry(**g) for g in bundle.known_gaps]
    designer_gap = [g for g in pyd_gaps if g.gap_id == "g1"][0]
    assert designer_gap.description == "VisualDirection has empty color_delta"
    assert designer_gap.target_persona == "designer"


def test_pydantic_path_resolved_when_no_new_gap():
    def _resolve(target, context, mid):
        return None
    bundle = _sample_bundle()
    pyd_gaps = [GapEntry(**g) for g in bundle.known_gaps]
    out = remediate_with_pydantic(pyd_gaps, persona_invoke_fn=_resolve, dry_run=False)
    designer_outcome = [o for o in out if o.gap_id == "g1"][0]
    assert designer_outcome.resolved is True


# --- Equivalence test (the point of the experiment) -----------------------

def test_dicts_and_pydantic_produce_same_outcomes():
    """On a well-formed bundle, the two paths should agree."""
    bundle = _sample_bundle()
    pyd_gaps = [GapEntry(**g) for g in bundle.known_gaps]

    def _stub(target, context, mid):
        if target == "designer":
            return None
        return {"description": f"still need work on {target}", "severity": "medium"}

    out_a = remediate_with_dicts(bundle, persona_invoke_fn=_stub, dry_run=False)
    out_b = remediate_with_pydantic(pyd_gaps, persona_invoke_fn=_stub, dry_run=False)

    assert len(out_a) == len(out_b)
    for a, b in zip(out_a, out_b):
        assert a.gap_id == b.gap_id
        assert a.target_persona == b.target_persona
        assert a.resolved == b.resolved
        assert a.new_gap_emitted == b.new_gap_emitted


# --- Side-by-side report ---------------------------------------------------

def test_side_by_side_report_shape():
    bundle = _sample_bundle()
    report = side_by_side_report(bundle, dry_run=True)
    assert "bundle_id" in report
    assert "gap_count_dicts" in report
    assert "gap_count_pydantic" in report
    assert "pydantic_accepted" in report
    assert "outcomes_dicts" in report
    assert "outcomes_pydantic" in report
    assert report["gap_count_dicts"] == 3
    assert report["gap_count_pydantic"] == 3
    assert report["pydantic_accepted"] is True


if __name__ == "__main__":
    import traceback
    tests = [
        test_dicts_path_groups_by_target_persona,
        test_dicts_path_dry_run_does_not_invoke,
        test_dicts_path_resolved_when_no_new_gap,
        test_dicts_path_unresolved_when_new_gap_returned,
        test_pydantic_path_groups_by_target_persona,
        test_pydantic_path_uses_attribute_access,
        test_pydantic_path_resolved_when_no_new_gap,
        test_dicts_and_pydantic_produce_same_outcomes,
        test_side_by_side_report_shape,
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
