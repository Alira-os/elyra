"""
remediation.py — Test harness: re-invoke target_persona for each gap
in HandoffBundle.known_gaps.

This is the experiment the user requested: we have a list of gaps
discovered at handoff time, each with a `target_persona` field. The
remediation harness should:

  1. Group the gaps by target_persona.
  2. For each target, re-invoke the persona with the gap as context.
  3. Verify whether the gap was resolved (no new gap with the same
     source + description) or persisted (the persona couldn't fix it).

We deliberately try TWO shapes for known_gaps to see which is more
ergonomic:
  - Option A: List[Dict] (current schema) — gap ledger's to_dict() format.
  - Option B: List[GapEntry] (Pydantic) — typed, validated.

This module implements BOTH and produces a side-by-side report.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Path setup: this file lives at skills/agentic/remediation.py. The
# elyra root is parents[2] of this file. (Note: the persona modules use
# parents[1] which is a latent bug — they work only because sys.path[0]
# is the CWD when running from elyra/. We get it right here.)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory.gap_ledger import log_gap, query_gaps, GapEntry  # noqa: E402
from models.site_schemas import HandoffBundle, CoherenceGateReport  # noqa: E402


# --- Result types -----------------------------------------------------------

@dataclass
class RemediationOutcome:
    """The result of trying to remediate one gap."""
    gap_id: str
    target_persona: str
    description: str
    resolved: bool  # True if a re-invocation cleared the gap
    new_gap_emitted: bool  # True if a follow-up invocation emitted a new gap
    notes: str = ""


# --- Option A: known_gaps as List[Dict] (current schema) -------------------

def remediate_with_dicts(
    bundle: HandoffBundle,
    persona_invoke_fn,
    *,
    dry_run: bool = True,
) -> List[RemediationOutcome]:
    """Remediate gaps when known_gaps is a list of plain dicts.

    The current HandoffBundle schema uses List[Dict[str, Any]]. This
    function shows what it's like to work with that shape: every access
    uses dict-key lookup, every validation is a manual `if "field" in gap`
    check, and the type system gives us no help.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for gap in bundle.known_gaps:
        target = gap.get("target_persona")
        if not target:
            # No target → can't route. Surface this as a "not actionable" outcome.
            grouped["__no_target__"].append(gap)
            continue
        grouped[target].append(gap)

    outcomes: List[RemediationOutcome] = []
    for target, gaps in grouped.items():
        if target == "__no_target__":
            for g in gaps:
                outcomes.append(RemediationOutcome(
                    gap_id=g.get("gap_id", ""),
                    target_persona="(none)",
                    description=g.get("description", ""),
                    resolved=False,
                    new_gap_emitted=False,
                    notes="gap has no target_persona — cannot route",
                ))
            continue
        for g in gaps:
            gap_context = (
                f"Re-run requested because of gap {g.get('gap_id', '?')}: "
                f"{g.get('description', '')}. "
                f"Suggested fix: {g.get('suggested_fix', 'n/a')}"
            )
            if dry_run:
                outcomes.append(RemediationOutcome(
                    gap_id=g.get("gap_id", ""),
                    target_persona=target,
                    description=g.get("description", ""),
                    resolved=False,
                    new_gap_emitted=False,
                    notes=f"[dry_run] would invoke {target} with context: {gap_context[:80]}",
                ))
                continue
            # Real invocation
            t0 = time.time()
            try:
                new_gap = persona_invoke_fn(target, gap_context, bundle.migration_id)
            except Exception as e:
                outcomes.append(RemediationOutcome(
                    gap_id=g.get("gap_id", ""),
                    target_persona=target,
                    description=g.get("description", ""),
                    resolved=False,
                    new_gap_emitted=False,
                    notes=f"invoke failed: {type(e).__name__}: {e}",
                ))
                continue
            elapsed = time.time() - t0
            resolved = (new_gap is None)
            outcomes.append(RemediationOutcome(
                gap_id=g.get("gap_id", ""),
                target_persona=target,
                description=g.get("description", ""),
                resolved=resolved,
                new_gap_emitted=not resolved,
                notes=f"re-invoked {target} in {elapsed:.1f}s; new_gap={'yes' if not resolved else 'no'}",
            ))
    return outcomes


# --- Option B: known_gaps as List[GapEntry] (Pydantic) ---------------------

def remediate_with_pydantic(
    bundle_pydantic_gaps_field: List[GapEntry],
    persona_invoke_fn,
    *,
    dry_run: bool = True,
) -> List[RemediationOutcome]:
    """Remediate gaps when known_gaps is a list of GapEntry (Pydantic).

    This function shows what it's like to work with the typed shape:
    every access is a Pydantic attribute, the type system catches typos,
    and `target_persona` is required by the schema (not optional).
    """
    grouped: Dict[Optional[str], List[GapEntry]] = defaultdict(list)
    for gap in bundle_pydantic_gaps_field:
        grouped[gap.target_persona].append(gap)

    outcomes: List[RemediationOutcome] = []
    for target, gaps in grouped.items():
        for g in gaps:
            # A gap without target_persona is not routable. Surface it
            # the same way the dicts path does, but the type system
            # made the absence explicit (None) rather than letting
            # `.get("target_persona")` silently return None.
            if target is None:
                outcomes.append(RemediationOutcome(
                    gap_id=g.gap_id,
                    target_persona="(none)",
                    description=g.description,
                    resolved=False,
                    new_gap_emitted=False,
                    notes="gap has no target_persona — cannot route",
                ))
                continue
            gap_context = (
                f"Re-run requested because of gap {g.gap_id}: "
                f"{g.description}. "
                f"Suggested fix: {g.suggested_fix or 'n/a'}"
            )
            if dry_run:
                outcomes.append(RemediationOutcome(
                    gap_id=g.gap_id,
                    target_persona=target,
                    description=g.description,
                    resolved=False,
                    new_gap_emitted=False,
                    notes=f"[dry_run] would invoke {target} with context: {gap_context[:80]}",
                ))
                continue
            try:
                new_gap = persona_invoke_fn(target, gap_context, getattr(g, "migration_id", ""))
            except Exception as e:
                outcomes.append(RemediationOutcome(
                    gap_id=g.gap_id,
                    target_persona=target,
                    description=g.description,
                    resolved=False,
                    new_gap_emitted=False,
                    notes=f"invoke failed: {type(e).__name__}: {e}",
                ))
                continue
            resolved = (new_gap is None)
            outcomes.append(RemediationOutcome(
                gap_id=g.gap_id,
                target_persona=target,
                description=g.description,
                resolved=resolved,
                new_gap_emitted=not resolved,
                notes=f"re-invoked {target}; new_gap={'yes' if not resolved else 'no'}",
            ))
    return outcomes


# --- Side-by-side report --------------------------------------------------

def side_by_side_report(
    bundle: HandoffBundle,
    *,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Run both remediation paths against the same bundle and compare."""
    # Path A: dicts (the shape HandoffBundle.known_gaps currently is).
    out_a = remediate_with_dicts(bundle, persona_invoke_fn=None, dry_run=dry_run)

    # Path B: Pydantic GapEntry list. We have to convert.
    pyd_gaps: List[GapEntry] = []
    for d in bundle.known_gaps:
        try:
            pyd_gaps.append(GapEntry(**d))
        except Exception as e:
            # This is exactly the point: dicts are loose; Pydantic validates.
            pyd_gaps = None
            break
    if pyd_gaps is not None:
        out_b = remediate_with_pydantic(pyd_gaps, persona_invoke_fn=None, dry_run=dry_run)
        pydantic_accepted = True
    else:
        out_b = []
        pydantic_accepted = False

    return {
        "bundle_id": bundle.bundle_id,
        "gap_count_dicts": len(bundle.known_gaps),
        "gap_count_pydantic": len(pyd_gaps) if pyd_gaps is not None else None,
        "pydantic_accepted": pydantic_accepted,
        "outcomes_dicts": [
            {
                "gap_id": o.gap_id,
                "target_persona": o.target_persona,
                "resolved": o.resolved,
                "new_gap_emitted": o.new_gap_emitted,
                "notes": o.notes,
            }
            for o in out_a
        ],
        "outcomes_pydantic": [
            {
                "gap_id": o.gap_id,
                "target_persona": o.target_persona,
                "resolved": o.resolved,
                "new_gap_emitted": o.new_gap_emitted,
                "notes": o.notes,
            }
            for o in out_b
        ],
    }


# --- CLI for ad-hoc testing ----------------------------------------------

def _build_sample_bundle() -> HandoffBundle:
    g = CoherenceGateReport(
        gate_name="planning_coherence_gate",
        passed=True,
        warnings=["one open question"],
        artifact_coverage={
            "site_understanding": True,
            "site_architecture": True,
            "content_recommendation": True,
            "visual_direction": True,
        },
        fidelity_score=0.85,
        evaluated_at="2026-06-08T13:00:00Z",
    )
    return HandoffBundle(
        bundle_id="b-test-001",
        migration_id="mig-test-001",
        site_slug="example",
        from_room="planning",
        to_room="forge",
        site_understanding_id="su-1",
        site_architecture_id="sa-1",
        content_recommendation_id="cr-1",
        visual_direction_id="vd-1",
        brand_spec={"primary_color": "#1E293B"},
        planning_rationale=["Chose Next.js based on Wix structure"],
        open_questions=[{"question": "Confirm motion_philosophy=classical", "owner": "client", "eta": "2026-06-15", "severity": "low"}],
        known_gaps=[
            {
                "gap_id": "g1",
                "severity": "medium",
                "target_persona": "designer",
                "description": "VisualDirection has empty color_delta",
                "suggested_fix": "Re-run designer with explicit color tokens",
            },
            {
                "gap_id": "g2",
                "severity": "high",
                "target_persona": "builder",
                "description": "BuildManifest missing lighthouse scores",
                "suggested_fix": "Add lighthouse step to builder flow",
            },
            {
                "gap_id": "g3",
                "severity": "low",
                "description": "No target_persona on this one",
            },
        ],
        coherence_gate=g,
        success_criteria=["Lighthouse perf > 90"],
        handoff_at="2026-06-08T13:00:00Z",
    )


if __name__ == "__main__":
    print("=" * 70)
    print("Test 1: well-formed bundle (the happy path)")
    print("=" * 70)
    bundle = _build_sample_bundle()
    report = side_by_side_report(bundle, dry_run=True)
    print(f"Bundle: {report['bundle_id']}")
    print(f"Gaps as dicts: {report['gap_count_dicts']}")
    print(f"Gaps as Pydantic: {report['gap_count_pydantic']} (accepted: {report['pydantic_accepted']})")
    print(f"\nDicts path produced {len(report['outcomes_dicts'])} outcomes:")
    for o in report["outcomes_dicts"]:
        print(f"  - {str(o['target_persona']):20s} | {o['gap_id']:5s} | notes: {o['notes'][:80]}")
    print(f"\nPydantic path produced {len(report['outcomes_pydantic'])} outcomes:")
    for o in report["outcomes_pydantic"]:
        print(f"  - {str(o['target_persona']):20s} | {o['gap_id']:5s} | notes: {o['notes'][:80]}")

    print("\n" + "=" * 70)
    print("Test 2: bundle with malformed gaps (typo in severity, missing fields)")
    print("=" * 70)
    bundle.known_gaps.append({
        "gap_id": "g4",
        "severity": "kinda_high",  # INVALID — should be low/medium/high/critical
        "target_persona": "ui_designer",
        # description missing — INVALID
    })
    bundle.known_gaps.append({
        "gap_id": "g5",
        "severity": "high",
        "target_persona": "not_a_real_persona_xyz",  # not a real persona, but schema doesn't know that
    })
    report = side_by_side_report(bundle, dry_run=True)
    print(f"Gaps as dicts: {report['gap_count_dicts']}")
    print(f"Gaps as Pydantic: {report['gap_count_pydantic']} (accepted: {report['pydantic_accepted']})")
    if report['pydantic_accepted']:
        print("  -> Pydantic accepted the bundle as-is (no validation surface here).")
        print(f"  -> dicts and Pydantic produced {len(report['outcomes_dicts'])} / {len(report['outcomes_pydantic'])} outcomes respectively.")
    else:
        print("  -> Pydantic REJECTED the bundle. dicts path runs anyway, Pydantic path refuses.")
        print("  -> the rejection is the *desired* behavior — surface bad data to the manager.")

    print("\n" + "=" * 70)
    print("Test 3: simulated real invocation (resolve g1 via designer stub)")
    print("=" * 70)
    def _stub_designer_invoke(target_persona, gap_context, migration_id):
        # Simulate that designer "fixed" the issue.
        if target_persona == "designer" and "color_delta" in gap_context:
            return None  # no new gap → resolved
        # Otherwise simulate that the persona emitted a follow-up gap.
        return {"description": f"still need work on {target_persona}", "severity": "medium"}

    # Re-build a clean bundle
    bundle2 = _build_sample_bundle()
    out_a = remediate_with_dicts(bundle2, persona_invoke_fn=_stub_designer_invoke, dry_run=False)
    out_b = remediate_with_pydantic(
        [GapEntry(**g) for g in bundle2.known_gaps],
        persona_invoke_fn=_stub_designer_invoke,
        dry_run=False,
    )
    print("Dicts path outcomes:")
    for o in out_a:
        print(f"  {o.gap_id}: resolved={o.resolved} new_gap={o.new_gap_emitted} | {o.notes[:60]}")
    print("Pydantic path outcomes:")
    for o in out_b:
        print(f"  {o.gap_id}: resolved={o.resolved} new_gap={o.new_gap_emitted} | {o.notes[:60]}")

    print("\nConclusion: both shapes produce identical outcomes here.")
    print("Pydantic adds: a validation step that surfaces bad data before remediation.")
    print("Dicts add: zero overhead, plain JSON, no conversion at the gap-ledger boundary.")
