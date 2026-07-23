from conductor.routing import Router
from conductor.memory_client import MemoryClient
from conductor.state_machine import (
    ConductorState, WorkflowPhase, create_initial_state,
    transition_to_phase, add_error, is_terminal_state
)
from conductor.trace import Trace
from registry.registry import load_persona, list_personas
from tools.execution import get_backend, BackendInvokeError
from memory.gap_ledger import query_gaps, log_gap
from models.site_schemas import (
    ManagerDecision,
    Room,
    Steward,
    CoherenceGateReport,
    CoherenceGateWaiver,
    GateBlock,
    HandoffBundle,
    SiteUnderstanding,
    SiteArchitecture,
    ContentRecommendation,
    VisualDirection,
    BuildManifest,
    SeoStrategy,
    GeoStrategy,
    GeoBuildArtifacts,
)
import sys
from typing import Optional, List, Dict, Any
import subprocess
import json
import tempfile
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import re


@dataclass
class MigrationResult:
    success: bool
    session_id: str
    routing_sequence: list[str]
    stack_chosen: str
    deploy_url: Optional[str]
    fidelity_score: Optional[float]
    trace: Trace
    errors: list[dict]
    phase_reached: str


class MigrationManager:
    """
    Closed-loop MigrationManager for Elyra.

    Supports:
    - Forward progression per persona iteration_count
    - Backward routing on quality-gate failures or high-severity gaps
    - Automatic versioning of persona artifacts on route_back
    - Crisp gap-context injection via summarize_gaps_for_kilo
    - Terminal escalation via structured GitHub issue created by github_strategy_agent
    - Elyra Engineer invoked automatically on both "complete" and "github_issue_created"
    - Zero human-in-the-loop states.
    """

    MANAGER_PERSONA_PATH = Path("registry/personas/migration_orchestrator.md")
    MAX_RETRIES = 3
    SAME_GATE_FAIL_LIMIT = 3

    # Two-tier artifact paths
    SCRATCH_ARTIFACT_DIR = Path(".kilo/artifacts")
    PERSIST_ARTIFACT_DIR = Path("memory/artifacts")

    # --- Phase D: sites-out-of-repo + per-site git ---
    # Where new site builds are written. Must be absolute and MUST NOT
    # resolve to a path inside the elyra repo. Sites are committed to a
    # per-site git repo on a forge/<migration_id> branch (see
    # conductor/site_repo.py + _setup_site_repo).
    DEFAULT_OUTPUT_ROOT = "C:/Users/micha/DevProjects"
    ELYRA_REPO_ROOT = Path(__file__).resolve().parents[1]

    @staticmethod
    def _resolve_output_root(task_context: dict) -> Path:
        """Validate and resolve the output_root from task_context.

        Rules:
        - must be absolute (no implicit-relative surprises)
        - must NOT be inside the elyra repo (refuse to write sites into
          the agent's own working tree)
        Returns the resolved, validated Path. Raises ValueError on any
        violation.
        """
        raw = task_context.get("output_root", MigrationManager.DEFAULT_OUTPUT_ROOT)
        p = Path(raw).expanduser().resolve()
        if not Path(raw).is_absolute() and not str(raw).startswith(("C:", "D:", "/", "\\\\")):
            raise ValueError(f"output_root must be absolute, got {raw}")
        repo_root = MigrationManager.ELYRA_REPO_ROOT.resolve()
        try:
            p.relative_to(repo_root)
            inside = True
        except ValueError:
            inside = False
        if p == repo_root or inside:
            raise ValueError(
                f"output_root {p} is inside the elyra repo {repo_root}; "
                f"refuse to write sites into the agent's own working tree"
            )
        return p

    # --- Phase 1.0: Rooms, Stewards, and Handoff Ceremony ---
    #
    # These are the structural primitives the Dual-Room design calls for.
    # The PLANNING_ROOM is the discovery + iterative refinement phase
    # (scraper → architect → marketing → designer, with the Architect as
    # steward). The FORGE_ROOM is the implementation phase (builder +
    # quality gates, with the Integration Coordinator as steward). Both
    # are exposed as class-level constants so the manager loop can ask
    # `self.PLANNING_ROOM.ordered_personas()` instead of hard-coding a
    # list of names, and so the trace events can be tagged with the
    # room they happened in.

    PLANNING_ROOM = Room(
        name="planning",
        description=(
            "Discovery + iterative refinement. The Architect acts as "
            "Architecture Owner + Planning Integrator and leads the "
            "Planning Coherence Gate before any handoff is allowed."
        ),
        personas=[
            "scraper_specialist",
            "architect_specialist",
            "marketing_specialist",
            "seo_specialist",        # Phase E: SEO strategy
            "geo_specialist",        # Phase E: GEO-for-LLMs strategy
            "ui_designer",
        ],
        steward="architect_specialist",
        inputs=["url", "platform"],
        outputs=[
            "site_understanding",
            "site_architecture",
            "content_recommendation",
            "visual_direction",
            "seo_strategy",          # Phase E
            "geo_strategy",          # Phase E
        ],
        coherence_gate="planning_coherence_gate",
        preflight_order=[
            # Recommended initial discovery order (flexible starting
            # point — manager/steward can adjust or run limited parallel
            # work). Per the design.
            #
            # Phase E: seo_specialist and geo_specialist slot in AFTER
            # marketing_specialist (so content/copy targets exist) and
            # BEFORE ui_designer (so visual direction can host the
            # planned schema.org types and meta templates).
            "scraper_specialist",
            "architect_specialist",
            "marketing_specialist",
            "seo_specialist",
            "geo_specialist",
            "ui_designer",
        ],
    )

    PLANNING_STEWARD = Steward(
        name="planning_steward",
        room="planning",
        persona_ref="architect_specialist",
        role_description=(
            "Architecture Owner + Planning Integrator. Owns the "
            "evolving architecture artifact throughout the room and "
            "leads the Planning Coherence Gate."
        ),
        capabilities=[
            "rich_bidirectional_pull",
            "cross_artifact_review",
            "coherence_gate",
        ],
    )

    FORGE_ROOM = Room(
        name="forge",
        description=(
            "Implementation — layered build with smoothing. The DevOps "
            "Engineer (Deployment Guardian) participates early to inject "
            "operational constraints. The Integration Coordinator smooths "
            "rough edges across data/backend/frontend at the end."
        ),
        personas=[
            "deploy_specialist",        # Deployment Guardian — early
            "data_engineer",            # Data layer
            "backend_architect",        # API + server-side
            "frontend_architect",       # Components + state + a11y
            "geo_specialist",           # Phase E: produces GEO files
            "integration_coordinator",  # Cross-layer smoothing (steward)
        ],
        steward="integration_coordinator",
        inputs=["handoff_bundle"],
        outputs=[
            "deploy_spec",
            "data_contracts",
            "api_contracts",
            "build_manifest",
            "site_build",
            "integration_status",
            "geo_build_artifacts",    # Phase E
        ],
        coherence_gate="build_quality_gate",
        # Phase 1.1: layered build with DevOps early.
        # Phase E: geo_specialist runs AFTER frontend_architect (so page
        # templates exist for JSON-LD blocks) and BEFORE
        # integration_coordinator (so the steward can verify everything
        # together).
        preflight_order=[
            "deploy_specialist",        # 1. DevOps injects constraints
            "data_engineer",            # 2. Data layer follows
            "backend_architect",        # 3. API surface follows data
            "frontend_architect",       # 4. UI consumes everything
            "geo_specialist",           # 5. GEO files into built site
            "integration_coordinator",  # 6. Steward smooths edges
        ],
    )

    FORGE_STEWARD = Steward(
        name="forge_steward",
        room="forge",
        persona_ref="integration_coordinator",
        role_description=(
            "Integration Coordinator + Smoother of rough edges. Runs "
            "cross-layer checks (api_path_consistent_with_frontend_routes, "
            "design_tokens_applied_everywhere, cms_models_match_frontend_"
            "data_fetchers, deploy_env_vars_match_backend_env, "
            "routes_match_navigation, accessibility_assets_present) and "
            "produces the final IntegrationStatus. Small frictions are "
            "resolved in-place; big ones route_back to the responsible "
            "persona."
        ),
        capabilities=[
            "design_token_consistency",
            "cross_layer_smoothing",
            "deployment_readiness",
            "api_route_reconciliation",
        ],
    )

    # Phase E: Locked AI-crawler allowlist for GEO-for-LLMs.
    #
    # GeoBuildArtifacts.ai_crawler_allowlist must contain every entry
    # here or build_quality_gate fails (see _run_polish_checks). The
    # canonical human-facing source of truth is docs/GEO_FOR_LLMS.md;
    # keep this constant in sync with it.
    LOCKED_AI_CRAWLERS = (
        "GPTBot",
        "ClaudeBot",
        "Claude-User",
        "Google-Extended",
        "PerplexityBot",
        "Applebot-Extended",
        "anthropic-ai",
        "CCBot",
        "cohere-ai",
        "Amazonbot",
        "Bytespider",
    )

    def __init__(
        self,
        db_path: str = "elyra_memory.db",
        backend: Optional["object"] = None,
    ):
        """Construct the MigrationManager.

        Args:
            db_path: SQLite path for the memory subsystem.
            backend: Optional :class:`tools.execution.ExecutionBackend` to use
                for persona invocations. Defaults to ``get_backend()`` when
                ``None``. Phase 1 wiring replaces the legacy
                ``tools.kilo.invoke_kilo`` calls with ``backend.invoke(...)``;
                until that lands, the ``backend`` argument is accepted and
                stored on ``self.backend`` for downstream callers and tests,
                but the Manager's routing loop is unchanged.
        """
        from memory.memory import Memory
        # Lazy import to avoid a hard dependency on the Phase 0 seam module
        # at import time (Phase 1 is the consumer that wires it in).
        if backend is None:
            try:
                from tools.execution import get_backend
                backend = get_backend()
            except Exception:
                backend = None

        self.memory = Memory(db_path)
        self.memory_client = MemoryClient(db_path)
        self.session_id = str(uuid.uuid4())
        self.backend = backend
        self.manager_persona = self.MANAGER_PERSONA_PATH.read_text() if self.MANAGER_PERSONA_PATH.exists() else ""
        self.iteration_count: Dict[str, int] = {}
        self.consecutive_gate_failures: Dict[str, int] = {}
        self.trace: List[Dict[str, Any]] = []
        self.gap_context_cache: Dict[str, str] = {}

    # ------------------------- Public Entry Point -------------------------

    def run(self, task_context: dict) -> dict:
        """Execute the full automated closed-loop migration."""
        url = task_context.get("url", "")
        platform = task_context.get("platform", "unknown")
        migration_id = task_context.get("migration_id") or datetime.now().strftime("%Y%m%d_%H%M%S")

        self.trace = []
        artifacts: Dict[str, Any] = {}
        gaps_logged: List[Dict[str, Any]] = []

        # Phase D: validate output_root once and pin it on task_context so
        # every downstream call sees the resolved absolute path. Failure
        # here is loud — we refuse to silently fall back to sites/.
        output_root = self._resolve_output_root(task_context)
        task_context["output_root"] = str(output_root)

        # Derive site_name from URL if not provided (more reliable slug generation)
        if "site_name" in task_context and task_context["site_name"]:
            site_name = task_context["site_name"]
        elif url:
            # Extract meaningful name from URL (e.g., "my-site-2" from "https://example.wixstudio.com/my-site-2")
            from urllib.parse import urlparse
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.strip("/").split("/") if p]
            site_name = path_parts[-1] if path_parts else "unnamed"
        else:
            site_name = "unnamed"

        site_slug = self._get_site_slug(site_name)

        self._log_trace("migration_started", {"migration_id": migration_id, "url": url, "platform": platform, "site_slug": site_slug})

        site_dir = Path(task_context["output_root"]) / site_slug
        build_manifest = self._init_build_manifest(migration_id, url, site_slug, output_root=output_root)

        # ------------------------------------------------------------------
        # Phase C: Manager-driven planning loop.
        #
        # The procedural preflight (Phases 0–1.0) ran the planning personas
        # in a fixed order, retried failures, then ran the gate once at
        # the end. That made the manager the *second* brain: it only saw
        # a clean artifact set and the gate had to either pass or hard-stop.
        #
        # In Phase C, the Manager persona is the single routing brain. It
        # gets told PLANNING_ROOM.preflight_order on the first turn (a
        # *recommendation*, not a hard-coded sequence) and decides which
        # persona to run, when to route_back, and when planning is
        # complete. After every persona call, we run the Planning
        # Coherence Gate and pass its structured `blocking` (List[GateBlock])
        # back into the manager's next turn so it can dispatch on
        # `persona + gap_id`. The loop terminates when the manager
        # returns action=complete (planning artifacts present + gate
        # passed), abort, or github_issue_created.
        #
        # The Forge Room is unchanged: it still runs its layered
        # preflight (devops → data → backend → frontend → coordinator)
        # once planning emits the HandoffBundle.
        # ------------------------------------------------------------------
        _SHORT_TO_LONG = {
            "scraper": "scraper_specialist",
            "architect": "architect_specialist",
            "marketing": "marketing_specialist",
            "designer": "ui_designer",
            "devops": "deploy_specialist",
            "data": "data_engineer",
            "backend": "backend_architect",
            "frontend": "frontend_architect",
            "coordinator": "integration_coordinator",
            "builder": "builder",
            # Phase E: discoverability specialists
            "seo": "seo_specialist",
            "geo": "geo_specialist",
        }
        _LONG_TO_SHORT = {v: k for k, v in _SHORT_TO_LONG.items()}

        self._log_trace_with_room("manager_loop_started", {
            "preflight_order": self.PLANNING_ROOM.preflight_order,
            "room": "planning",
        }, room="planning")

        # First decision: invoke the first persona in PLANNING_ROOM.
        # preflight_order. We seed this in code rather than asking the
        # LLM, because on turn 1 the manager has no artifacts and no
        # gate to reason over — it would just echo the order back.
        first_persona = (
            self.PLANNING_ROOM.preflight_order[0]
            if self.PLANNING_ROOM.preflight_order
            else self.PLANNING_ROOM.personas[0]
        )
        decision = ManagerDecision(
            action="invoke_persona",
            persona=first_persona,
            reason="Phase C: manager-loop init — first persona from preflight_order.",
        )
        gate_report: Optional[CoherenceGateReport] = None
        handoff_bundle: Optional[HandoffBundle] = None
        max_manager_iterations = int(task_context.get("max_manager_iterations", 25))
        manager_iteration = 0

        while decision.action not in ("complete", "abort", "github_issue_created"):
            manager_iteration += 1
            if manager_iteration > max_manager_iterations:
                self._log_trace_with_room("max_iterations_reached", {
                    "iterations": manager_iteration,
                    "last_action": decision.action,
                    "last_persona": decision.persona,
                    "gaps_logged_count": len(gaps_logged),
                }, room="planning")
                final_state = "max_iterations_reached"
                self._finalize_build_manifest(build_manifest, final_state, artifacts, gaps_logged)
                return {
                    "migration_id": migration_id,
                    "site_slug": site_slug,
                    "success": False,
                    "phase_reached": final_state,
                    "artifacts": artifacts,
                    "gaps": gaps_logged,
                    "trace": self.trace,
                    "build_manifest": build_manifest.model_dump() if hasattr(build_manifest, "model_dump") else build_manifest,
                    "coherence_gate": gate_report.model_dump() if gate_report else None,
                    "handoff_bundle": handoff_bundle.model_dump() if handoff_bundle else None,
                }
            self._log_decision(decision)

            if decision.action == "invoke_persona":
                persona_long = decision.persona or first_persona
                persona_short = _LONG_TO_SHORT.get(persona_long, persona_long)
                # Run the gate *before* the persona to capture the
                # pre-invocation state (useful for fidelity-warnings-on-
                # re-entry). Then run the persona, then re-run the gate
                # so the manager sees the post-invocation state on its
                # next turn.
                gate_report = self._run_planning_coherence_gate(artifacts, gaps_logged)
                print(f"\n[MANAGER_LOOP] Invoking {persona_long} (turn {manager_iteration})...")
                result = self._invoke_persona(
                    persona_short, task_context, artifacts, site_slug, migration_id
                )
                artifacts[persona_long] = result.get("artifact")
                if result.get("gaps"):
                    gaps_logged.extend(result["gaps"])
                # Re-run the gate so the manager sees the updated state.
                gate_report = self._run_planning_coherence_gate(artifacts, gaps_logged)
                if gate_report.suggested_route_back():
                    self._log_trace_with_room("gate_suggests_route_back", {
                        "persona": gate_report.suggested_route_back(),
                        "blocking_personas": [b.persona for b in gate_report.blocking],
                    }, room="planning")
                next_step = f"{persona_long}_complete"

            elif decision.action == "route_back":
                persona_long = decision.persona or "unknown"
                persona_short = _LONG_TO_SHORT.get(persona_long, persona_long)
                # _apply_route_back expects the SHORT name (it dispatches
                # via _invoke_persona which keys on short names). We
                # produce a shallow decision copy with the short persona
                # so the underlying _invoke_persona dispatch works.
                # Phase C: also synthesize a gate_report-shaped dict
                # from the planning gate's structured blocking list so
                # _apply_route_back can summarize gaps_for_kilo.
                decision_for_apply = decision.model_copy(
                    update={"persona": persona_short}
                )
                if decision_for_apply.gate_report is None and gate_report is not None:
                    decision_for_apply = decision_for_apply.model_copy(
                        update={
                            "gate_report": {
                                "gaps": [
                                    {
                                        "id": b.gap_id,
                                        "description": b.reason,
                                        "severity": b.severity,
                                        "source_persona": b.persona,
                                        "target_persona": b.persona,
                                        "suggested_fix": f"Re-invoke {b.persona}",
                                    }
                                    for b in gate_report.blocking
                                ],
                            }
                        }
                    )
                self._apply_route_back(
                    decision_for_apply, task_context, artifacts, site_slug, migration_id, build_manifest
                )
                # artifacts[] was set with the SHORT name; promote to
                # LONG so downstream consumers see the same key shape.
                if persona_short in artifacts and persona_long not in artifacts:
                    artifacts[persona_long] = artifacts[persona_short]
                # Re-run the gate to capture post-route_back state.
                gate_report = self._run_planning_coherence_gate(artifacts, gaps_logged)
                next_step = f"{persona_long}_routed_back"

            else:
                # Manager produced an unexpected action — treat as abort
                # but log the unexpected value for diagnostics.
                self._log_trace_with_room("manager_loop_unexpected_action", {
                    "action": decision.action,
                    "persona": decision.persona,
                    "reason": decision.reason,
                }, room="planning")
                final_state = "abort"
                self._finalize_build_manifest(build_manifest, final_state, artifacts, gaps_logged)
                return {
                    "migration_id": migration_id,
                    "site_slug": site_slug,
                    "success": False,
                    "phase_reached": final_state,
                    "artifacts": artifacts,
                    "gaps": gaps_logged,
                    "trace": self.trace,
                    "build_manifest": build_manifest.model_dump() if hasattr(build_manifest, "model_dump") else build_manifest,
                    "coherence_gate": gate_report.model_dump() if gate_report else None,
                    "handoff_bundle": None,
                }

            decision = self._decide_next_action(
                next_step,
                task_context,
                artifacts,
                gaps_logged,
                site_dir,
                gate_report=gate_report,
            )

        # Manager emitted a terminal action. If `complete`, the gate must
        # have passed (or be waived); otherwise hard-stop with
        # gate_failed_no_waivers.
        final_state = decision.action
        if final_state == "complete":
            if gate_report is None:
                gate_report = self._run_planning_coherence_gate(artifacts, gaps_logged)
            if not gate_report.passed and not gate_report.waivers:
                self._log_trace_with_room("planning_halted", {
                    "phase": "gate_failed_no_waivers",
                    "blocking": [b.persona for b in gate_report.blocking],
                    "warnings": gate_report.warnings,
                }, room="planning")
                return {
                    "migration_id": migration_id,
                    "site_slug": site_slug,
                    "success": False,
                    "phase_reached": "gate_failed_no_waivers",
                    "artifacts": artifacts,
                    "gaps": gaps_logged,
                    "trace": self.trace,
                    "build_manifest": build_manifest.model_dump() if hasattr(build_manifest, "model_dump") else build_manifest,
                    "coherence_gate": gate_report.model_dump(),
                    "handoff_bundle": None,
                }
            handoff_bundle = self._run_handoff_ceremony(
                migration_id=migration_id,
                site_slug=site_slug,
                site_name=site_name,
                artifacts=artifacts,
                gate_report=gate_report,
                gaps_logged=gaps_logged,
                task_context=task_context,
            )
            # Phase D: per-site git repo setup. Runs immediately after
            # the Handoff Ceremony so the Forge persona loop can operate
            # inside a known checkout. Git failures are logged as a
            # medium-severity gap (manager can retry) and DO NOT block
            # the Forge — the orchestrator must remain resilient.
            self._setup_site_repo(site_dir, migration_id, site_slug, task_context, artifacts)
            self._log_trace_with_room("manager_loop_complete", {
                "artifacts_produced": list(artifacts.keys()),
                "gaps_count": len(gaps_logged),
                "gate_passed": gate_report.passed,
            }, room="planning")
        else:
            # abort or github_issue_created — surface the gate report
            # if we have one (useful for the issue body / abort trace).
            self._log_trace_with_room("manager_loop_terminal", {
                "final_state": final_state,
                "reason": decision.reason,
            }, room="planning")
            return {
                "migration_id": migration_id,
                "site_slug": site_slug,
                "success": False,
                "phase_reached": final_state,
                "artifacts": artifacts,
                "gaps": gaps_logged,
                "trace": self.trace,
                "build_manifest": build_manifest.model_dump() if hasattr(build_manifest, "model_dump") else build_manifest,
                "coherence_gate": gate_report.model_dump() if gate_report else None,
                "handoff_bundle": None,
            }

        # Phase 1.1: Forge Room pre-flight. The Planning Room has just
        # emitted the HandoffBundle; now the Forge Room runs its layered
        # build:
        #   1. devops (Deployment Guardian) — emits DeploySpec
        #   2. data_engineer — emits DataContracts
        #   3. backend_architect — emits APIContracts
        #   4. frontend_architect — emits BuildManifest + writes code
        #   5. integration_coordinator — emits IntegrationStatus
        #
        # Each persona can pull from the HandoffBundle (already on disk)
        # and from the artifacts of its predecessors. The orchestrator
        # does NOT pass them as kwargs; the personas read from memory/
        # on demand (per the blackboard model). This keeps the wiring
        # surface small and matches how the planning personas already
        # work.
        max_preflight_retries = int(task_context.get("max_preflight_retries", 2))
        forge_personas_long = self.FORGE_ROOM.ordered_personas()
        forge_personas_short = [_LONG_TO_SHORT.get(p, p) for p in forge_personas_long]
        self._log_trace_with_room("forge_preflight_started", {
            "personas": forge_personas_long,
            "max_retries": max_preflight_retries,
            "handoff_bundle_id": handoff_bundle.bundle_id,
        }, room="forge")
        for persona_long, persona_short in zip(forge_personas_long, forge_personas_short):
            # Skip-checks per persona: the persona is skipped if its
            # output artifact already exists in memory/. This lets
            # resume-from-checkpoint work cleanly.
            skip = False
            if persona_long == "deploy_specialist":
                skip = bool(self._get_latest_in_memory("memory/deploy_specs"))
            elif persona_long == "data_engineer":
                skip = bool(self._get_latest_in_memory("memory/data_contracts"))
            elif persona_long == "backend_architect":
                skip = bool(self._get_latest_in_memory("memory/api_contracts"))
            elif persona_long == "frontend_architect":
                # Frontend architect writes to sites/<slug>/; we treat the
                # directory existence as the skip signal.
                skip = (Path(task_context["output_root"]) / site_slug).exists()
            elif persona_long == "geo_specialist":
                # Phase E: forge-pass geo_specialist writes to sites/<slug>/
                # AND persists to memory/geo_builds/. Either signal is
                # sufficient — the directory existence is the cheaper check.
                skip = bool(self._get_latest_in_memory("memory/geo_builds"))
            elif persona_long == "integration_coordinator":
                skip = bool(self._get_latest_in_memory("memory/integration_status"))
            if skip:
                self._log_trace_with_room("forge_preflight_skipped", {
                    "persona": persona_long,
                    "reason": "artifact already exists",
                }, room="forge")
                continue

            attempt = 0
            while True:
                print(f"\n[FORGE] Invoking {persona_long} (attempt {attempt + 1}/{max_preflight_retries + 1})...")
                result = self._invoke_persona(persona_short, task_context, artifacts, site_slug, migration_id)
                artifacts[persona_long] = result.get("artifact")
                if result.get("gaps"):
                    gaps_logged.extend(result["gaps"])
                if result.get("success"):
                    break
                attempt += 1
                if attempt > max_preflight_retries:
                    print(f"[FORGE] {persona_long} failed after {max_preflight_retries + 1} attempts: {result.get('gaps')}")
                    return {
                        "migration_id": migration_id,
                        "site_slug": site_slug,
                        "success": False,
                        "phase_reached": f"forge_preflight_max_retries:{persona_long}",
                        "artifacts": artifacts,
                        "gaps": gaps_logged,
                        "trace": self.trace,
                        "build_manifest": build_manifest.model_dump() if hasattr(build_manifest, "model_dump") else build_manifest,
                        "coherence_gate": gate_report.model_dump(),
                        "handoff_bundle": handoff_bundle.model_dump(),
                    }
            print(f"[FORGE] {persona_long} completed")
        self._log_trace_with_room("forge_preflight_complete", {
            "artifacts_produced": list(artifacts.keys()),
            "gaps_count": len(gaps_logged),
        }, room="forge")

        decision = self._decide_next_action("init", task_context, artifacts, gaps_logged, site_dir)
        self._log_decision(decision)

        # Phase 0.6: hard cap on the manager loop. Even with the
        # deterministic target_persona short-circuit, a pathological site
        # could theoretically bounce the loop. We bail out cleanly with
        # a "max_iterations_reached" phase after the cap.
        max_manager_iterations = int(task_context.get("max_manager_iterations", 25))
        manager_iteration = 0
        while decision.action not in ("complete", "github_issue_created", "abort"):
            manager_iteration += 1
            if manager_iteration > max_manager_iterations:
                self._log_trace_with_room("max_iterations_reached", {
                    "iterations": manager_iteration,
                    "last_action": decision.action,
                    "last_persona": decision.persona,
                    "gaps_logged_count": len(gaps_logged),
                }, room="forge")
                final_state = "max_iterations_reached"
                self._finalize_build_manifest(build_manifest, final_state, artifacts, gaps_logged)
                return {
                    "migration_id": migration_id,
                    "site_slug": site_slug,
                    "success": False,
                    "phase_reached": final_state,
                    "artifacts": artifacts,
                    "gaps": gaps_logged,
                    "trace": self.trace,
                    "build_manifest": build_manifest.model_dump() if hasattr(build_manifest, "model_dump") else build_manifest,
                    "coherence_gate": gate_report.model_dump(),
                    "handoff_bundle": handoff_bundle.model_dump(),
                }
            if decision.action == "invoke_persona":
                result = self._invoke_persona(
                    decision.persona, task_context, artifacts, site_slug, migration_id
                )
                artifacts[decision.persona] = result.get("artifact")
                if result.get("gaps"):
                    gaps_logged.extend(result["gaps"])

                if not result.get("success"):
                    decision = self._decide_next_action(
                        f"{decision.persona}_failed", task_context, artifacts, gaps_logged, site_dir
                    )
                    self._log_decision(decision)
                    continue

            elif decision.action == "route_back":
                self._apply_route_back(decision, task_context, artifacts, site_slug, migration_id, build_manifest)
                decision = self._decide_next_action(
                    f"{decision.persona}_routed_back", task_context, artifacts, gaps_logged, site_dir
                )
                self._log_decision(decision)
                continue

            # After builder completes, run quality gate deterministically before next decision
            # Use the actual built site directory (may differ from original site_slug if builder renamed)
            if decision.persona == "builder" and decision.action == "invoke_persona":
                built_slug = result.get("built_site_slug") or site_slug
                actual_site_dir = Path(task_context["output_root"]) / built_slug
                self._log_trace_with_room("builder_start", {
                    "site_slug": built_slug,
                    "site_dir": str(actual_site_dir),
                    "handoff_bundle_id": handoff_bundle.bundle_id,
                }, room="forge")
                gate_report = self._run_quality_gates(actual_site_dir, re_run_impeccable=False)
                self._log_trace_with_room("quality_gate_run", {
                    "report": gate_report,
                }, room="forge")
                if not gate_report.get("overall_passed", False):
                    # Gate failed - record gaps but route back to builder for fixes
                    # Do NOT use step="quality_gate_failed" as that triggers abort safety rail
                    # Use step="builder_complete" so manager can route back to builder
                    gate_gaps = gate_report.get("gaps", [])
                    # Mark gaps with target_persona=builder so manager knows to route back
                    for gap in gate_gaps:
                        if "target_persona" not in gap or not gap["target_persona"]:
                            gap["target_persona"] = "builder"
                    gaps_logged.extend(gate_gaps)
                    self._log_trace_with_room("quality_gate_failed_recorded", {
                        "gates": gate_gaps,
                    }, room="forge")
                    # Call with builder_complete step so manager routes back to builder
                    decision = self._decide_next_action(
                        "builder_complete",
                        task_context, artifacts, gaps_logged, site_dir
                    )
                    self._log_decision(decision)
                    continue
                else:
                    self._log_trace_with_room("quality_gate_passed", {}, room="forge")

            decision = self._decide_next_action(
                f"{decision.persona}_complete" if decision.action == "invoke_persona" else decision.action,
                task_context, artifacts, gaps_logged, site_dir
            )
            self._log_decision(decision)

        final_state = decision.action
        self._finalize_build_manifest(build_manifest, final_state, artifacts, gaps_logged)

        promotion_state = None
        if final_state in ("complete", "github_issue_created"):
            self._invoke_elyra_engineer(migration_id, build_manifest, site_slug)
            # Phase 0: hand off to PromotionPipeline so the build → preview →
            # human-approval → production path is part of the same E2E run.
            # This is opt-in via task_context["run_promotion"] (default False
            # to preserve existing test behavior) and never aborts the
            # migration — a promotion failure is recorded but does not flip
            # `success` to False.
            if task_context.get("run_promotion", False):
                promotion_state = self.run_promotion(
                    migration_id=migration_id,
                    site_name=site_name,
                    site_slug=site_slug,
                    local_build_path=str(Path(task_context["output_root"]) / site_slug),
                )

        result = {
            "migration_id": migration_id,
            "site_slug": site_slug,
            "success": final_state == "complete",
            "phase_reached": final_state,
            "artifacts": artifacts,
            "gaps": gaps_logged,
            "trace": self.trace,
            "build_manifest": build_manifest.model_dump() if hasattr(build_manifest, "model_dump") else build_manifest,
            "coherence_gate": gate_report.model_dump(),
            "handoff_bundle": handoff_bundle.model_dump(),
        }
        if promotion_state is not None:
            result["promotion_state"] = (
                promotion_state.model_dump() if hasattr(promotion_state, "model_dump") else str(promotion_state)
            )
        return result

    # ------------------------- Promotion Boundary (Phase 0) -------------------------

    def run_promotion(
        self,
        migration_id: str,
        site_name: str,
        site_slug: str,
        local_build_path: str,
    ):
        """Post-build promotion handoff.

        Phase A cleanup: the legacy PromotionPipeline is gone. The
        promotion stage is now driven entirely by the HandoffBundle
        contract — when ``requires_human_review`` is true on the final
        HandoffBundle, the Manager emits a github_issue_created action
        (wired in Phase C) and pauses for human approval before the
        production deploy.

        This method is a no-op stub that records the boundary so trace
        consumers can still see it fired. Production deploy wiring is
        Phase C work; see docs/NORTH_STAR.md.
        """
        self._log_trace("promotion_start", {
            "migration_id": migration_id,
            "site_slug": site_slug,
            "local_build_path": local_build_path,
        })
        self._log_trace("promotion_delegated_to_handoff", {
            "note": "legacy PromotionPipeline removed in Phase A; "
                    "promotion now flows through HandoffBundle.requires_human_review",
        })
        return None

    # ------------------------- Decision Engine -------------------------

    def _decide_next_action(
        self,
        step: str,
        task_context: dict,
        artifacts: dict,
        gaps: list,
        site_dir: Path,
        gate_report: Optional[CoherenceGateReport] = None,
    ) -> ManagerDecision:
        """LLM-driven decision engine. Only safety rails + the deterministic
        target-persona short-circuit are non-LLM.

        Phase C: `gate_report` is the planning coherence gate's report
        (a CoherenceGateReport with structured `blocking: List[GateBlock]`).
        We surface it to the manager so it can dispatch on
        `block.persona` instead of re-deriving routing from raw gaps.
        """
        # Safety rail 1: high-severity gap with no recoverable target
        high_severity_gaps = [g for g in gaps if isinstance(g, dict) and g.get("severity") == "high"]
        if high_severity_gaps and not any(g.get("target_persona") for g in high_severity_gaps):
            return ManagerDecision(action="abort", reason="High-severity gap with no target_persona", gaps_detected=high_severity_gaps)

        # Phase 0.6: deterministic short-circuit. If the most recent
        # high-severity gap carries a target_persona, route back to it
        # without an LLM round-trip. The manager persona is only consulted
        # for *cross-persona* decisions or when no target is suggested.
        # This is the bit that makes the self-healing loop fast and reliable.
        current_state = self._build_current_state(artifacts, gaps, site_dir, gate_report=gate_report)
        suggestion = current_state.get("routing_suggestion")
        if (
            suggestion
            and suggestion.get("preferred_persona")
            and step.endswith(("_failed", "_routed_back", "builder_complete"))
        ):
            preferred = suggestion["preferred_persona"]
            # Guard against runaway loops: if we've already retried the
            # same target persona N times, fall through to the LLM (or the
            # next step) so we don't spin forever.
            if not self._is_looping_on_persona(preferred):
                self._log_trace("routing_suggestion_used", {
                    "preferred_persona": preferred,
                    "gap_id": suggestion.get("gap_id"),
                    "from_step": step,
                })
                return ManagerDecision(
                    action="route_back",
                    persona=preferred,
                    reason=f"Deterministic: target_persona from gap {suggestion.get('gap_id')} suggests routing to {preferred}.",
                    gap_context=suggestion.get("reason"),
                    gaps_detected=high_severity_gaps,
                )

        # Safety rail 2 & 3 are evaluated inside _consult_manager_persona after ManagerDecision is received
        return self._consult_manager_persona(current_state, task_context, gate_report=gate_report)

    def _is_looping_on_persona(self, persona: str, max_consecutive: int = 3) -> bool:
        """Return True if the last N decisions all targeted the same persona.

        Used to break self-healing loops. The threshold is intentionally
        small — a real recovery takes 1-2 retries, and anything beyond that
        usually means the persona is the wrong target or the input data is
        unrecoverable.

        Requires at least `max_consecutive` decisions in history before
        declaring a loop — otherwise a single initial invocation would
        trivially register as "looping on itself."
        """
        if not hasattr(self, "_recent_decisions"):
            self._recent_decisions = []
        if len(self._recent_decisions) < max_consecutive:
            return False
        recent = self._recent_decisions[-max_consecutive:]
        return all(
            (d.get("persona") == persona and d.get("action") in ("route_back", "invoke_persona"))
            for d in recent
        )

    def _map_gate_failure_to_persona(self, gate_report: Dict[str, Any]) -> str:
        failing_gate = gate_report.get("failing_gate", "")
        if failing_gate in ("npm_build", "impeccable_audit"):
            return "builder"
        if failing_gate == "token_fidelity":
            return "designer"
        if failing_gate == "accessibility":
            return "designer"
        return "builder"

    # ------------------------- LLM-Driven Decision Engine (NEW) -------------------------

    def _build_current_state(
        self,
        artifacts: dict,
        gaps: list,
        site_dir: Path,
        gate_report: Optional[CoherenceGateReport] = None,
    ) -> Dict[str, Any]:
        """Assemble the structured state payload for the Manager persona.

        Phase C: if a planning coherence gate_report was supplied (the
        manager loop runs the gate after every persona), we surface it
        under `planning_gate_report` so the LLM can dispatch on
        `blocking[].persona`. We still run the FORGE quality gate here
        for backward compat with the legacy forge-room manager loop
        that uses this payload — but for the planning manager loop the
        gate_report argument is the more useful signal.
        """
        # Only run FORGE quality gates if site directory exists.
        if site_dir.exists():
            forge_gate_report = self._run_quality_gates(site_dir, re_run_impeccable=False)
            self._log_trace("quality_gate_run", {"report": forge_gate_report})
        else:
            forge_gate_report = {"overall_passed": True, "message": "Site directory not yet created - skipping gates"}
            self._log_trace("quality_gate_skip", {"reason": "Site directory not yet created", "site_dir": str(site_dir)})

        # Phase 0.6: surface a deterministic routing_suggestion derived from
        # the most-recent high-severity gap that carries a target_persona.
        # The manager persona can still override, but this gives the LLM a
        # strong prior instead of asking it to re-derive routing from raw gaps.
        routing_suggestion: Optional[Dict[str, Any]] = None
        recent_target_gaps = [
            g for g in (gaps or [])
            if isinstance(g, dict)
            and g.get("severity") == "high"
            and g.get("target_persona")
        ]
        if recent_target_gaps:
            # Use the most recent one (gaps_logged is append-ordered).
            top = recent_target_gaps[-1]
            routing_suggestion = {
                "preferred_persona": top.get("target_persona"),
                "reason": top.get("description", "")[:200],
                "gap_id": top.get("gap_id"),
                "source_persona": top.get("source_persona"),
            }

        payload: Dict[str, Any] = {
            "artifacts": {
                p: {"present": True, "version": "latest", "path": str(site_dir / f"{p}.json")}
                for p in artifacts.keys()
            },
            "gaps": gaps,
            "quality_gate_result": forge_gate_report if not forge_gate_report.get("overall_passed") else None,
            "iteration_count": self.iteration_count,
            "consecutive_gate_failures": self.consecutive_gate_failures,
            "routing_suggestion": routing_suggestion,
        }
        # Phase C: planning gate report — only attach when a gate has
        # actually run. We serialize the blocking list as a list of
        # dicts so the LLM can read it cleanly.
        if gate_report is not None:
            payload["planning_gate_report"] = {
                "gate_name": gate_report.gate_name,
                "passed": gate_report.passed,
                "blocking": [b.model_dump(mode="json") for b in gate_report.blocking],
                "warnings": gate_report.warnings,
                "suggested_route_back": gate_report.suggested_route_back(),
                "fidelity_score": gate_report.fidelity_score,
                "fidelity_threshold": gate_report.fidelity_threshold,
            }
        # Phase C: on the first turn (empty artifacts), surface the
        # recommended initial order so the manager knows what to invoke.
        if not artifacts and self.PLANNING_ROOM.preflight_order:
            payload["preflight_order"] = list(self.PLANNING_ROOM.preflight_order)
        return payload

    def _consult_manager_persona(
        self,
        current_state: Dict[str, Any],
        task_context: dict,
        gate_report: Optional[CoherenceGateReport] = None,
    ) -> ManagerDecision:
        """Invoke the migration_orchestrator persona and obtain ManagerDecision.

        Phase 1: routes through ``backend.invoke(persona, prompt,
        output_model=ManagerDecision)`` — the seam from PLAN.md. The
        backend handles invocation + JSON extraction + Pydantic validation
        against the schema. On backend failure we fall through to the
        same deterministic abort path as a malformed LLM response, so
        the manager never infinite-loops on "Missing action".

        Phase C: when a planning gate_report was supplied, its structured
        `blocking` list is already inside current_state["planning_gate_report"]
        so the manager can dispatch on `block.persona` directly.
        """
        from skills.agentic.manager_decision import validate_and_repair_manager_decision

        prompt = f"""{self.manager_persona}

## CURRENT STATE
```json
{json.dumps(current_state, indent=2, default=str)}
```

**Task Context (brief):** {json.dumps({k: task_context.get(k) for k in ('url','platform','migration_id')}, indent=2)}

You are now acting solely as the Migration Manager. Return ONLY a valid JSON object matching the ManagerDecision schema. No prose outside the JSON.
"""

        # Route through backend.invoke — same JSON-extraction + validation
        # path every persona uses.
        persona_path = Path("registry/personas/migration_orchestrator.md")
        try:
            backend = get_backend()
            decision = backend.invoke(
                persona=persona_path,
                prompt=prompt,
                output_model=ManagerDecision,
            )
            preview = decision.model_dump_json() if decision is not None else ""
        except BackendInvokeError as e:
            # Backend failed (subprocess error, JSON missing, schema
            # mismatch). Treat as a malformed manager response — the
            # helper below produces a deterministic abort ManagerDecision
            # and never raises, so the manager loop never spins on this.
            preview = f"[BACKEND_INVOKE_ERROR] {e}"
            decision = validate_and_repair_manager_decision(preview)

        # Always log the raw response for live debugging.
        self._log_trace("manager_raw_response", {
            "decision_text_preview": preview[:800] if preview else "(empty)",
            "decision_text_length": len(preview) if preview else 0,
        })
        try:
            print(f"  [MANAGER_RAW] {preview[:600]}")
        except UnicodeEncodeError:
            print(f"  [MANAGER_RAW] {preview[:600].encode('ascii', 'replace').decode('ascii')}")

        # If the helper produced a deterministic abort, log a structured
        # trace event so the failure is visible in the run history. We
        # do NOT recurse or retry — the abort is the answer.
        if decision.action == "abort" and "manager persona" in decision.reason:
            self._log_trace("manager_decision_invalid", {
                "reason": decision.reason,
                "raw_preview": preview[:400] if preview else "",
            })
            # Phase C: also write a real gap-ledger entry so the
            # failure is visible to downstream consumers (the elyra
            # engineer, gap-frequency analysis, etc.). Without this
            # the parse failure was only in the trace; now it's a
            # first-class gap.
            try:
                log_gap(
                    migration_id=task_context.get("migration_id", ""),
                    gap_type="manager_parse_failure",
                    source_persona="manager",
                    description=decision.reason[:300],
                    suggested_fix="Inspect manager prompt; likely JSON shape drift or prose output.",
                    severity="high",
                )
            except Exception as _e:
                # Never let gap-ledger failures mask the original abort.
                pass

        # Track iteration count per persona for safety / observability.
        if decision.persona:
            self.iteration_count[decision.persona] = self.iteration_count.get(decision.persona, 0) + 1

        return decision

    # ------------------------- Quality Gates -------------------------

    def _run_quality_gates(self, site_dir: Path, re_run_impeccable: bool = False) -> Dict[str, Any]:
        """Public wrapper around quality_gate.run_quality_gates.

        Phase E: after the existing checks run, invoke
        `_run_polish_checks(site_dir)` to add the four discoverability
        checks (llms.txt present, meta descriptions match SEO targets,
        AI crawler allowlist covers the locked set, JSON-LD parses).
        Failures land in the same `gaps` array so the existing
        route_back machinery dispatches on `target_persona`.
        """
        try:
            from quality_gate import run_quality_gates as qg_run
            report = qg_run(str(site_dir), re_run_impeccable=re_run_impeccable)
        except Exception as e:
            report = {
                "overall_passed": False,
                "failing_gate": "quality_gate_exception",
                "errors": [str(e)],
                "gaps": [{"description": f"Quality gate runner exception: {e}", "severity": "high"}],
            }

        # Phase E polish checks — best-effort. If the polish runner
        # itself throws (e.g. malformed GeoBuildArtifacts on disk), we
        # log and continue rather than masking the original gate result.
        try:
            polish_gaps = self._run_polish_checks(site_dir)
            if polish_gaps:
                existing_gaps = list(report.get("gaps") or [])
                existing_gaps.extend(polish_gaps)
                report = {**report, "gaps": existing_gaps}
                # Polish failures are blocking.
                report = {**report, "overall_passed": False}
                failing = report.get("failing_gate") or "polish_checks"
                report = {**report, "failing_gate": failing}
        except Exception as e:
            existing_gaps = list(report.get("gaps") or [])
            existing_gaps.append({
                "description": f"Polish checks runner exception: {e}",
                "severity": "high",
                "target_persona": "manager",
            })
            report = {**report, "gaps": existing_gaps}

        return report

    @staticmethod
    def _run_polish_checks(site_dir: Path) -> List[Dict[str, Any]]:
        """Phase E: four discoverability polish checks.

        Each failure produces a gap dict with a stable `gap_id` and a
        `target_persona` so the existing route_back dispatch sends the
        manager to the responsible persona. We deliberately do NOT use
        the `CoherenceGateReport`/`GateBlock` machinery — those are for
        the planning room's coherence gate. The forge-side quality gate
        speaks in dict-shaped gaps.

        Checks:
          1. `sites/<slug>/llms.txt` exists and is non-empty
          2. meta descriptions in rendered HTML >= SeoStrategy.target_routes count
          3. GeoBuildArtifacts.ai_crawler_allowlist covers LOCKED_AI_CRAWLERS
          4. at least one JSON-LD block parses (sample one route from
             json_ld_blocks_by_route)
        """
        gaps: List[Dict[str, Any]] = []

        # Resolve site_slug from site_dir (last path component).
        try:
            site_slug = site_dir.name
        except Exception:
            site_slug = ""

        # --- Check 1: llms.txt present and non-empty ---
        llms_path = site_dir / "llms.txt"
        llms_ok = llms_path.exists()
        llms_content = ""
        if llms_ok:
            try:
                llms_content = llms_path.read_text(encoding="utf-8")
                if not llms_content.strip():
                    llms_ok = False
            except Exception:
                llms_ok = False
        if not llms_ok:
            gaps.append({
                "gap_id": "polish.llms_txt_missing",
                "description": (
                    f"llms.txt missing or empty at {llms_path}. "
                    "geo_specialist's forge pass must produce this file."
                ),
                "suggested_fix": (
                    "Re-invoke geo_specialist in the Forge to produce "
                    "llms.txt, robots.txt AI stanza, sitemap.xml extras, "
                    "and JSON-LD blocks."
                ),
                "severity": "high",
                "target_persona": "geo_specialist",
            })

        # --- Check 2: meta description coverage vs SeoStrategy.target_routes ---
        seo_strategy: Optional[Any] = None
        try:
            seo_dir = Path("memory/seo_strategies")
            if seo_dir.exists():
                seo_files = sorted(seo_dir.glob("*.json"), reverse=True)
                if seo_files:
                    import json as _json
                    data = _json.loads(seo_files[0].read_text(encoding="utf-8"))
                    from models.site_schemas import SeoStrategy
                    seo_strategy = SeoStrategy(**data)
        except Exception:
            seo_strategy = None

        target_routes: List[str] = []
        if seo_strategy is not None:
            target_routes = list(getattr(seo_strategy, "target_routes", []) or [])

        # Count meta_description tags in rendered HTML files.
        meta_count = 0
        try:
            html_files = list(site_dir.rglob("*.html"))
        except Exception:
            html_files = []
        for html_file in html_files:
            try:
                content = html_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            meta_count += content.lower().count('name="description"')

        if target_routes and meta_count < len(target_routes):
            gaps.append({
                "gap_id": "polish.meta_descriptions_short",
                "description": (
                    f"meta_description count={meta_count} is below "
                    f"SeoStrategy.target_routes count={len(target_routes)}. "
                    "frontend_architect must apply the SEO meta templates "
                    "to every targeted route."
                ),
                "suggested_fix": (
                    "Re-invoke frontend_architect with the SeoStrategy's "
                    "meta_description_templates and title_templates; "
                    "ensure every route in target_routes emits a "
                    "<meta name=\"description\" ...> tag."
                ),
                "severity": "high",
                "target_persona": "frontend_architect",
            })

        # --- Check 3: AI crawler allowlist covers LOCKED_AI_CRAWLERS ---
        geo_build: Optional[Any] = None
        try:
            geo_dir = Path("memory/geo_builds")
            if geo_dir.exists():
                geo_files = sorted(geo_dir.glob("*.json"), reverse=True)
                if geo_files:
                    import json as _json
                    data = _json.loads(geo_files[0].read_text(encoding="utf-8"))
                    from models.site_schemas import GeoBuildArtifacts
                    geo_build = GeoBuildArtifacts(**data)
        except Exception:
            geo_build = None

        allowlist: List[str] = []
        if geo_build is not None:
            allowlist = list(getattr(geo_build, "ai_crawler_allowlist", []) or [])
        missing_crawlers = [c for c in MigrationManager.LOCKED_AI_CRAWLERS if c not in allowlist]
        if missing_crawlers:
            gaps.append({
                "gap_id": "polish.ai_crawler_allowlist_incomplete",
                "description": (
                    f"GeoBuildArtifacts.ai_crawler_allowlist is missing "
                    f"{len(missing_crawlers)} locked crawlers: "
                    f"{missing_crawlers[:6]}{'...' if len(missing_crawlers) > 6 else ''}. "
                    f"Canonical allowlist: docs/GEO_FOR_LLMS.md."
                ),
                "suggested_fix": (
                    "Re-invoke geo_specialist in the Forge and ensure "
                    "ai_crawler_allowlist covers every entry in "
                    "MigrationManager.LOCKED_AI_CRAWLERS."
                ),
                "severity": "high",
                "target_persona": "geo_specialist",
            })

        # --- Check 4: at least one JSON-LD block parses ---
        if geo_build is not None:
            blocks_by_route = dict(getattr(geo_build, "json_ld_blocks_by_route", {}) or {})
            sample_route: Optional[str] = None
            sample_block: Optional[Dict[str, Any]] = None
            for route, blocks in blocks_by_route.items():
                if blocks:
                    sample_route = route
                    sample_block = blocks[0] if isinstance(blocks[0], dict) else None
                    break
            if sample_block is None:
                gaps.append({
                    "gap_id": "polish.json_ld_blocks_missing",
                    "description": (
                        "GeoBuildArtifacts.json_ld_blocks_by_route is empty. "
                        "geo_specialist's forge pass must produce at least "
                        "one valid JSON-LD block."
                    ),
                    "suggested_fix": (
                        "Re-invoke geo_specialist in the Forge and ensure "
                        "json_ld_blocks_by_route is populated for at least "
                        "the routes in GeoStrategy.target_first_class_routes."
                    ),
                    "severity": "high",
                    "target_persona": "geo_specialist",
                })
            else:
                # Validate the sample block parses as JSON-shaped data.
                try:
                    import json as _json
                    _json.dumps(sample_block)
                except Exception as e:
                    gaps.append({
                        "gap_id": "polish.json_ld_block_unparseable",
                        "description": (
                            f"JSON-LD block on route {sample_route!r} "
                            f"failed to serialize as JSON: {e}"
                        ),
                        "suggested_fix": (
                            "Re-invoke geo_specialist in the Forge; every "
                            "JSON-LD block must be a JSON-serializable dict."
                        ),
                        "severity": "high",
                        "target_persona": "geo_specialist",
                    })

        return gaps

    # ------------------------- Backward Routing -------------------------

    def _apply_route_back(
        self,
        decision: ManagerDecision,
        task_context: dict,
        artifacts: dict,
        site_slug: str,
        migration_id: str,
        build_manifest: Any,
    ) -> None:
        """Route back to responsible persona with versioned artifact + crisp gap context."""
        persona = decision.persona
        gap_context = decision.gap_context or self.summarize_gaps_for_kilo(
            decision.gate_report.get("gaps", []) if decision.gate_report else []
        )

        # Produce next versioned artifact path
        base_path = self._get_base_artifact_path(persona, site_slug)
        next_version_path = self._get_next_version_path(base_path)
        self._log_trace("route_back", {"persona": persona, "version_path": str(next_version_path), "gap_context": gap_context})

        # Invoke persona with gap_context
        result = self._invoke_persona(
            persona, task_context, artifacts, site_slug, migration_id
        )

        # Record in rework_log
        if hasattr(build_manifest, "rework_log"):
            build_manifest.rework_log.append({
                "persona": persona,
                "iteration": self.iteration_count.get(persona, 0),
                "artifact_path": str(next_version_path),
                "gap_ids": [g.get("id", "") for g in (decision.gate_report or {}).get("gaps", [])],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "gap_context": gap_context,
            })

        artifacts[persona] = result.get("artifact")

    def summarize_gaps_for_kilo(self, gaps: List[Dict[str, Any]]) -> str:
        """Return 2–4 crisp bullets + exact requested change for Kilo injection."""
        if not gaps:
            return "No gaps detected."
        bullets = []
        for g in gaps[:4]:
            desc = g.get("description", "unknown issue")
            fix = g.get("suggested_fix", "address the violation")
            bullets.append(f"• {desc} — {fix}")
        return "\n".join(bullets)

    def _get_next_version_path(self, base_path: Path) -> Path:
        """Return next versioned path: visual_direction_v2.json, etc."""
        if not base_path.exists():
            return base_path
        stem = base_path.stem
        suffix = base_path.suffix
        parent = base_path.parent
        matches = list(parent.glob(f"{stem}_v*{suffix}"))
        if not matches:
            return parent / f"{stem}_v2{suffix}"
        versions = []
        for m in matches:
            m_stem = m.stem
            try:
                v = int(m_stem.rsplit("_v", 1)[1])
                versions.append(v)
            except Exception:
                pass
        next_v = max(versions) + 1 if versions else 2
        return parent / f"{stem}_v{next_v}{suffix}"

    def _get_base_artifact_path(self, persona: str, site_slug: str) -> Path:
        if persona == "designer":
            return Path("memory/visual_specs") / site_slug / "visual_direction.json"
        if persona == "builder":
            return Path("sites") / site_slug / "app" / "page.tsx"  # representative artifact
        return Path("memory") / f"{persona}_artifacts" / site_slug / f"{persona}.json"

    # ------------------------- GitHub Escalation -------------------------

    def _create_github_issue(
        self,
        task_context: dict,
        gate_report: Dict[str, Any],
        artifacts: dict,
        gaps: list,
    ) -> ManagerDecision:
        """Create a structured GitHub issue via the deploy_specialist persona.

        Phase 1: routes through ``backend.invoke(...)`` directly with a
        Pydantic-shaped dict contract — no thin-glue
        ``github_strategy_agent`` wrapper. The deploy_specialist persona
        uses GitHub MCP to create the issue.
        """
        from registry.prompts import build_github_issue_prompt
        from pydantic import BaseModel

        class _GitHubIssueResult(BaseModel):
            success: bool = False
            issue_url: str = ""
            issue_number: int = 0
            message: str = ""

        migration_id = task_context.get("migration_id", "")
        url = task_context.get("url", "")
        platform = task_context.get("platform", "unknown")

        issue_body = self._build_github_issue_body(migration_id, url, platform, gate_report, artifacts, gaps)
        persona_path = Path("registry/personas/deploy_specialist.md")
        persona_text = persona_path.read_text(encoding="utf-8") if persona_path.exists() else ""
        prompt = build_github_issue_prompt(migration_id, url, platform, issue_body, persona_text)

        try:
            backend = get_backend()
            result = backend.invoke(
                persona=persona_path,
                prompt=prompt,
                output_model=_GitHubIssueResult,
            )
            if result.success:
                self._log_trace("github_issue_created", {"migration_id": migration_id, "issue_url": result.issue_url})
                return ManagerDecision(action="github_issue_created", reason="Terminal failure — GitHub issue created")
            self._log_trace("github_issue_failed", {"error": result.message or "unknown"})
            return ManagerDecision(action="abort", reason=f"GitHub issue creation returned success=False: {result.message}")
        except Exception as e:
            self._log_trace("github_issue_failed", {"error": str(e)})
            return ManagerDecision(action="abort", reason=f"GitHub issue creation failed: {e}")

    def _build_github_issue_body(
        self, migration_id: str, url: str, platform: str, gate_report: Dict[str, Any],
        artifacts: dict, gaps: list
    ) -> str:
        top_gaps = gaps[:10] if gaps else gate_report.get("gaps", [])[:10]
        iter_summary = "\n".join([f"- {p}: {c}" for p, c in self.iteration_count.items()])
        reproduce_cmd = f"python -m conductor.orchestrator {url} {platform}"

        return f"""# Migration Failure — {migration_id}

**Source:** {url} ({platform})  
**Migration ID:** {migration_id}  
**Iteration Counts:**  
{iter_summary}

**Last Quality Gate Report:**
```json
{json.dumps(gate_report, indent=2)[:2000]}
```

**Top Gaps:**
{chr(10).join([f"- {g.get('description', str(g))}" for g in top_gaps])}

**Full Trace Summary:** (see attached trace JSON)

**Reproduce Locally:**
```
{reproduce_cmd}
```

**Action Required:** Automated escalation — investigate root cause and persona improvements.
"""

    # ------------------------- Elyra Engineer -------------------------

    def _invoke_elyra_engineer(self, migration_id: str, build_manifest: Any, site_slug: str) -> None:
        """Non-blocking invocation of Elyra Engineer post-migration or on escalation."""
        try:
            from elyra_engineer import ElyraEngineer
            engineer = ElyraEngineer()
            engineer.analyze_and_propose(
                migration_id=migration_id,
                build_manifest=build_manifest,
                iteration_counts=self.iteration_count,
                gap_ledger=query_gaps(migration_id=migration_id),
                rework_log=getattr(build_manifest, "rework_log", []),
            )
            self._log_trace("elyra_engineer_invoked", {"migration_id": migration_id})
        except Exception as e:
            self._log_trace("elyra_engineer_failed", {"error": str(e)})

    # ------------------------- Helpers -------------------------

    def _log_trace(self, event: str, payload: Dict[str, Any]) -> None:
        self.trace.append({"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, "payload": payload})

    def _log_trace_with_room(
        self,
        event: str,
        payload: Dict[str, Any],
        room: str,
    ) -> None:
        """Log a trace event with the room it happened in.

        Phase 1.0: every trace event in the planning or forge room
        carries `room` so the audit trail makes the dual-room structure
        visible. Events that aren't room-scoped (e.g., migration_started)
        can still use _log_trace directly.
        """
        enriched = dict(payload or {})
        enriched["room"] = room
        self._log_trace(event, enriched)

    # ------------------------- Phase 1.0: Coherence Gate + Handoff Ceremony -------------------------

    def _run_planning_coherence_gate(
        self,
        artifacts: Dict[str, Any],
        gaps_logged: List[Dict[str, Any]],
    ) -> CoherenceGateReport:
        """Run the Planning Coherence Gate after designer completes.

        The gate's 5 inputs (per the design):
          1. artifact_coverage — are the four planning artifacts present?
          2. fidelity_score — did the Architect score the plan >= threshold?
          3. planner_rationale — is there a non-empty rationale?
          4. open_questions — are they all answered (or waived)?
          5. bidirectional_pull_count — has the steward pulled from peers?

        The gate's 5 outputs:
          1. passed (bool) — whether the room may proceed
          2. blocking (list[str]) — hard failures (no waiver possible)
          3. warnings (list[str]) — soft issues (logged, doesn't block)
          4. waivers (list[CoherenceGateWaiver]) — documented exceptions
          5. fidelity_score (float) — the actual score, or None
        """
        # Input 1: artifact coverage. Look up by both short and long
        # persona names because the pre-flight loop may have stored
        # with either convention (Phase 1.0 uses long names from
        # PLANNING_ROOM.ordered_personas()).
        su = artifacts.get("scraper") or artifacts.get("scraper_specialist")
        arch = artifacts.get("architect") or artifacts.get("architect_specialist")
        rec = artifacts.get("marketing") or artifacts.get("marketing_specialist")
        vd = artifacts.get("designer") or artifacts.get("ui_designer")
        artifact_coverage = {
            "site_understanding": su is not None,
            "site_architecture": arch is not None,
            "content_recommendation": rec is not None,
            "visual_direction": vd is not None,
        }
        # Input 2: fidelity score. The real SiteArchitecture schema
        # doesn't have a dedicated fidelity_score field; we use the
        # architect's `confidence` (0.0-1.0) as the closest proxy. If
        # it's missing or zero, fall back to the site understanding's
        # `estimated_fidelity`.
        fidelity_score: Optional[float] = None
        try:
            if arch is not None and hasattr(arch, "confidence"):
                v = float(getattr(arch, "confidence") or 0.0)
                if v > 0.0:
                    fidelity_score = v
        except Exception:
            fidelity_score = None
        if fidelity_score is None and su is not None and hasattr(su, "estimated_fidelity"):
            try:
                v = float(getattr(su, "estimated_fidelity") or 0.0)
                if v > 0.0:
                    fidelity_score = v
            except Exception:
                fidelity_score = None

        # Input 3: planner rationale — pull from the architect's
        # reasoning_trace (last entry, if any) or the site understanding's
        # reasoning_trace. We treat it as present if either has content.
        planner_rationale_present = bool(
            (arch is not None
             and hasattr(arch, "reasoning_trace")
             and getattr(arch, "reasoning_trace", None))
            or (su is not None
                and hasattr(su, "reasoning_trace")
                and getattr(su, "reasoning_trace", None))
        )

        # Input 4: open questions — derive from the gap ledger. Any
        # high-severity gap without a target_persona in planning_room is
        # considered an unanswered question.
        open_questions_unsanswered = [
            g for g in gaps_logged
            if isinstance(g, dict)
            and g.get("severity") == "high"
            and not g.get("target_persona")
        ]

        # Input 5: bidirectional pull count — derive from the trace.
        # Count trace events that look like steward pull events. For now
        # we treat any "rich_bidirectional_pull" or "steward_pull" event
        # as a pull.
        bidirectional_pull_count = sum(
            1 for e in self.trace
            if isinstance(e, dict)
            and e.get("event", "").startswith("steward_pull")
        )

        # 5 outputs.
        blocking: List[GateBlock] = []
        warnings: List[str] = []
        waivers: List[CoherenceGateWaiver] = []
        threshold = 0.7

        # Artifact coverage is a hard requirement. If any artifact is
        # missing AND there's no waiver, block. Phase C: each missing
        # artifact becomes a GateBlock whose persona is the persona that
        # produces it. The manager dispatches on `persona` to fix.
        _ARTIFACT_TO_PERSONA = {
            "site_understanding": "scraper_specialist",
            "site_architecture": "architect_specialist",
            "content_recommendation": "marketing_specialist",
            "visual_direction": "ui_designer",
        }
        missing = [k for k, v in artifact_coverage.items() if not v]
        if missing:
            for artifact in missing:
                persona_for_fix = _ARTIFACT_TO_PERSONA.get(artifact, "manager")
                blocking.append(
                    GateBlock(
                        persona=persona_for_fix,
                        reason=f"missing planning artifacts: {artifact}",
                        severity="high",
                    )
                )

        # Fidelity score below threshold is a soft requirement — emits
        # a warning, NOT a GateBlock, per the gate's 5-output contract.
        # The manager can choose to address it by route_back to the
        # architect (because the architect emits the fidelity signal)
        # OR proceed with a waiver; both are valid.
        if fidelity_score is not None and fidelity_score < threshold:
            warnings.append(
                f"fidelity_score={fidelity_score:.2f} below threshold {threshold:.2f}"
            )

        # Unanswered high-severity gaps are blocking unless waived.
        if open_questions_unsanswered:
            for g in open_questions_unsanswered:
                blocking.append(
                    GateBlock(
                        persona=g.get("source_persona") or "manager",
                        reason=f"unanswered high-severity gap: {g.get('description', '?')[:120]}",
                        gap_id=g.get("gap_id"),
                        severity="high",
                    )
                )

        # Bidirectional pull — emit a warning if zero. Not blocking;
        # the steward can still proceed with explicit acknowledgement.
        if bidirectional_pull_count == 0:
            warnings.append(
                "planning steward never bidirectionally pulled from peer artifacts"
            )

        if not planner_rationale_present and arch is not None:
            warnings.append("architect artifact has empty rationale")

        passed = len(blocking) == 0

        report = CoherenceGateReport(
            gate_name="planning_coherence_gate",
            passed=passed,
            blocking=blocking,
            warnings=warnings,
            waivers=waivers,
            artifact_coverage=artifact_coverage,
            fidelity_score=fidelity_score,
            fidelity_threshold=threshold,
            signals={
                "open_questions_unsanswered_count": len(open_questions_unsanswered),
                "bidirectional_pull_count": bidirectional_pull_count,
                "planner_rationale_present": planner_rationale_present,
            },
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

        self._log_trace_with_room("coherence_gate_evaluated", {
            "gate_name": "planning_coherence_gate",
            "passed": passed,
            "blocking_count": len(blocking),
            "warnings_count": len(warnings),
            "artifact_coverage": artifact_coverage,
            "fidelity_score": fidelity_score,
            "summary": report.summarize(),
        }, room="planning")

        return report

    def _run_handoff_ceremony(
        self,
        migration_id: str,
        site_slug: str,
        site_name: str,
        artifacts: Dict[str, Any],
        gate_report: CoherenceGateReport,
        gaps_logged: List[Dict[str, Any]],
        task_context: Dict[str, Any],
    ) -> HandoffBundle:
        """Run the Handoff Ceremony: package the planning bundle + gate
        report + known gaps, persist to memory, and return the bundle.

        Per the design: "Structured bundle passed from Planning Room →
        Forge Room: All planning artifacts + rationales + open questions,
        Known gaps with suggested target_persona, Design tokens + content
        map ready for implementation, Migration success criteria (from
        onboarding + memory), Coherence Gate result + any waivers."
        """
        # Resolve artifact IDs by looking up the latest in-memory file
        # for each artifact type. The bundle is *referential* — it
        # points at the artifacts by ID so the Forge Room can re-load
        # them on demand.
        su_id = self._get_latest_artifact_id("site_understandings")
        arch_id = self._get_latest_artifact_id("site_architectures")
        rec_id = self._get_latest_artifact_id("site_recommendations")
        # Phase E: discoverability strategies live in memory/seo_strategies
        # and memory/geo_strategies. Both default to None when the
        # corresponding personas were skipped (e.g. on a resume that
        # bypassed the planning manager loop).
        seo_strategy_id = self._get_latest_artifact_id("seo_strategies")
        geo_strategy_id = self._get_latest_artifact_id("geo_strategies")
        # Visual specs live in a per-slug subdir, so look there directly.
        vd_id: Optional[str] = None
        vd_dir = Path("memory/visual_specs") / site_slug
        if vd_dir.exists():
            files = sorted(vd_dir.glob("*.json"), reverse=True)
            if files:
                vd_id = files[0].stem

        # Brand spec is small and used everywhere — inline it.
        brand_spec: Optional[Dict[str, Any]] = None
        rec = artifacts.get("marketing") or artifacts.get("marketing_specialist")
        if rec is not None and hasattr(rec, "brand_spec") and rec.brand_spec:
            try:
                brand_spec = rec.brand_spec.model_dump(mode="json")
            except Exception:
                brand_spec = None

        # Planner rationale — pull the last entry of the architect's
        # reasoning_trace, or the site understanding's, as a single
        # crisp line. (SiteArchitecture's `reasoning_trace` is the
        # closest thing to a "rationale" field.)
        planning_rationale: List[str] = []
        arch = artifacts.get("architect") or artifacts.get("architect_specialist")
        if arch is not None and hasattr(arch, "reasoning_trace"):
            trace = list(getattr(arch, "reasoning_trace", []) or [])
            if trace:
                planning_rationale.append(str(trace[-1])[:300])
        if not planning_rationale:
            su = artifacts.get("scraper") or artifacts.get("scraper_specialist")
            if su is not None and hasattr(su, "reasoning_trace"):
                trace = list(getattr(su, "reasoning_trace", []) or [])
                if trace:
                    planning_rationale.append(str(trace[-1])[:300])

        # Open questions — derive from unanswered high-severity gaps
        # without a target_persona. These are the questions the Forge
        # Room should be aware of even if it proceeds.
        open_questions: List[Dict[str, Any]] = []
        for g in gaps_logged:
            if not isinstance(g, dict):
                continue
            if g.get("severity") != "high":
                continue
            open_questions.append({
                "question": g.get("description", "")[:200],
                "owner": g.get("source_persona", "unknown"),
                "eta": "n/a",
                "severity": "high",
                "gap_id": g.get("gap_id"),
            })

        # Known gaps to forward to the Forge Room. Pydantic GapEntry
        # conversion is loose by design (per Phase 0.7 experiment) —
        # we ship the dicts as-is.
        known_gaps: List[Dict[str, Any]] = []
        for g in gaps_logged:
            if not isinstance(g, dict):
                continue
            # Only forward high + medium severity gaps. Low severity
            # are noise; the manager can re-check the ledger if curious.
            if g.get("severity") not in ("high", "medium"):
                continue
            known_gaps.append({
                "gap_id": g.get("gap_id"),
                "severity": g.get("severity"),
                "source_persona": g.get("source_persona"),
                "target_persona": g.get("target_persona"),
                "description": g.get("description", "")[:300],
                "suggested_fix": g.get("suggested_fix"),
            })

        # Success criteria — pull from task_context if present, else
        # default to a small set of design-level criteria.
        success_criteria = task_context.get("success_criteria") or [
            "Build manifest schema valid",
            "All planned routes generated",
            "Quality gates pass (or waived)",
            "Build site is loadable (npm build, dev server up)",
        ]

        # Risk: should this migration require human review? Phase 1
        # #2 said: "manager can optionally trigger lightweight human
        # review if risk/novelty is high." Today we use a simple heuristic:
        # any blocking gap that was waived (i.e. an owner took
        # responsibility for a known risk) is a human-review signal.
        requires_human_review = len(gate_report.waivers) > 0
        human_review_reason: Optional[str] = None
        if requires_human_review:
            human_review_reason = (
                f"Coherence Gate passed with {len(gate_report.waivers)} "
                f"waiver(s) — engineering should review after build."
            )

        bundle = HandoffBundle(
            bundle_id=f"handoff-{migration_id}",
            migration_id=migration_id,
            site_slug=site_slug,
            from_room="planning",
            to_room="forge",
            site_understanding_id=su_id,
            site_architecture_id=arch_id,
            content_recommendation_id=rec_id,
            visual_direction_id=vd_id,
            seo_strategy_id=seo_strategy_id,
            geo_strategy_id=geo_strategy_id,
            brand_spec=brand_spec,
            planning_rationale=planning_rationale,
            open_questions=open_questions,
            known_gaps=known_gaps,
            coherence_gate=gate_report,
            success_criteria=success_criteria,
            requires_human_review=requires_human_review,
            human_review_reason=human_review_reason,
            # Phase D: pin the build target so the Forge Room always
            # knows where to write and which branch to commit to.
            output_root=task_context.get("output_root", self.DEFAULT_OUTPUT_ROOT),
            git_branch=f"forge/{migration_id}",
            artifact_provenance={
                "site_understanding": {
                    "persona": "scraper_specialist",
                    "version": su_id or "unknown",
                },
                "site_architecture": {
                    "persona": "architect_specialist",
                    "version": arch_id or "unknown",
                },
                "content_recommendation": {
                    "persona": "marketing_specialist",
                    "version": rec_id or "unknown",
                },
                "visual_direction": {
                    "persona": "ui_designer",
                    "version": vd_id or "unknown",
                },
                "seo_strategy": {
                    "persona": "seo_specialist",
                    "version": seo_strategy_id or "unknown",
                },
                "geo_strategy": {
                    "persona": "geo_specialist",
                    "version": geo_strategy_id or "unknown",
                },
            },
            handoff_at=datetime.now(timezone.utc).isoformat(),
        )
        # Phase D: refuse to persist a bundle without build target.
        # The D.1/D.2 work runs before this point, so by here both
        # output_root and git_branch must be populated.
        if not bundle.output_root or not bundle.git_branch:
            raise RuntimeError(
                f"HandoffBundle missing output_root/git_branch: output_root={bundle.output_root!r} git_branch={bundle.git_branch!r}"
            )

        # Persist to the per-migration blackboard.
        bundle_path = Path(bundle.to_memory_path())
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        with open(bundle_path, "w", encoding="utf-8") as f:
            f.write(bundle.model_dump_json(indent=2))

        self._log_trace_with_room("handoff_ceremony_complete", {
            "bundle_id": bundle.bundle_id,
            "bundle_path": str(bundle_path),
            "passed_gate": gate_report.passed,
            "known_gaps_count": len(known_gaps),
            "open_questions_count": len(open_questions),
            "requires_human_review": requires_human_review,
        }, room="planning")

        return bundle

    def _log_decision(self, decision: ManagerDecision) -> None:
        print(f"[MANAGER] Decision: action={decision.action} persona={decision.persona} reason={decision.reason[:80] if decision.reason else None}")
        # Phase 0.6: record this decision for the loop detector.
        if not hasattr(self, "_recent_decisions"):
            self._recent_decisions = []
        self._recent_decisions.append({
            "action": decision.action,
            "persona": decision.persona,
            "reason": decision.reason,
        })
        # Cap the history at the last 10 decisions.
        if len(self._recent_decisions) > 10:
            self._recent_decisions = self._recent_decisions[-10:]
        self._log_trace("decision", {
            "action": decision.action,
            "persona": decision.persona,
            "reason": decision.reason,
            "gap_context": decision.gap_context,
        })

    def _init_build_manifest(self, migration_id: str, url: str, site_slug: str, *, output_root: Optional[Path] = None) -> Any:
        # Minimal BuildManifest stub — extended in later step.
        # Phase D: output_dir uses output_root (validated absolute path)
        # so the build site lives outside the elyra repo.
        root = str(output_root) if output_root is not None else self.DEFAULT_OUTPUT_ROOT
        return type("BM", (), {
            "migration_id": migration_id,
            "source_url": url,
            "output_dir": f"{root.rstrip('/')}/{site_slug}",
            "rework_log": [],
            "iteration_history": [],
        })()

    def _setup_site_repo(
        self,
        site_dir: Path,
        migration_id: str,
        site_slug: str,
        task_context: Dict[str, Any],
        artifacts: Dict[str, Any],
    ) -> None:
        """Phase D: ensure site_dir is a git repo on forge/<migration_id>.

        Mechanical, no LLM reasoning — runs in the orchestrator. Git
        failures are logged as a medium-severity gap (manager can
        retry or fall back to writing without git) and never raise.
        """
        from conductor.site_repo import ensure_site_repo
        source_url = task_context.get("url", "")
        arch = artifacts.get("architect") or artifacts.get("architect_specialist")
        target_stack = getattr(arch, "target_stack", "unknown") if arch is not None else "unknown"
        extras = {
            "source_url": source_url,
            "target_stack": target_stack,
        }
        try:
            result = ensure_site_repo(
                site_dir=site_dir,
                site_slug=site_slug,
                migration_id=migration_id,
                site_readme_extras=extras,
            )
            self._log_trace_with_room("site_repo_initialized", {
                "site_dir": result["site_dir"],
                "branch": result["branch"],
                "init_steps": result["init_steps"],
            }, room="forge")
        except subprocess.CalledProcessError as e:
            log_gap(
                migration_id=migration_id,
                gap_type="git_setup_failed",
                source_persona="manager",
                target_persona="manager",
                description=f"Git setup failed for {site_dir}: {e.stderr or e}",
                suggested_fix="Inspect git availability and perms on output_root; manager may retry",
                severity="medium",
            )
            self._log_trace_with_room("site_repo_failed", {
                "site_dir": str(site_dir),
                "error": str(e),
            }, room="forge")
        except Exception as e:
            # Catch-all so a setup hiccup never blocks the Forge.
            log_gap(
                migration_id=migration_id,
                gap_type="git_setup_failed",
                source_persona="manager",
                target_persona="manager",
                description=f"Unexpected git setup error for {site_dir}: {e}",
                suggested_fix="Inspect output_root state; manager may retry",
                severity="medium",
            )
            self._log_trace_with_room("site_repo_failed", {
                "site_dir": str(site_dir),
                "error": str(e),
            }, room="forge")

    def _finalize_build_manifest(self, bm: Any, final_state: str, artifacts: dict, gaps: list) -> None:
        if hasattr(bm, "rework_log"):
            bm.final_state = final_state
            bm.completed_at = datetime.now(timezone.utc).isoformat()

    def _get_latest_artifact_id(
        self,
        artifact_dir: str,
        site_slug: Optional[str] = None,
        url: Optional[str] = None,
    ) -> Optional[str]:
        """Return the timestamp ID (filename stem) of the most recent
        JSON file in memory/<artifact_dir>/.

        If `site_slug` is given AND the artifact lives in a per-slug
        subdirectory (visual_specs is the only one today), the lookup
        is scoped to memory/<artifact_dir>/<site_slug>/.

        If `url` is given (Phase B), the directory is walked in
        reverse-time order and the most recent file whose parsed
        `url` field matches the requested URL is returned. If no file
        matches, falls through to the most recent file (preserves
        the legacy behavior on first run for a new URL).

        The orchestrator's two duplicate definitions are consolidated
        here in Phase 1.1.
        """
        if artifact_dir == "visual_specs" and site_slug:
            dir_path = Path("memory/visual_specs") / site_slug
        else:
            dir_path = Path("memory") / artifact_dir
        if not dir_path.exists():
            return None
        files = sorted(dir_path.glob("*.json"), reverse=True)
        if not files:
            return None
        if not url:
            return files[0].stem
        # Walk in reverse-time order. Return the latest whose parsed
        # `url` field equals the requested URL.
        import json
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                # Skip files that fail to parse (e.g. unfixed drift).
                # Don't crash the orchestrator over a bad file.
                continue
            if isinstance(data, dict) and data.get("url") == url:
                return f.stem
        # No URL match — fall through to the latest file (legacy behavior).
        return files[0].stem

    def _get_latest_in_memory(self, dir_path: str) -> Optional[Path]:
        """Return the path of the latest .json in a directory (e.g.
        'memory/deploy_specs'), or None if the dir is empty/missing.
        Accepts a relative or absolute path; doesn't prepend memory/."""
        p = Path(dir_path)
        if not p.exists():
            return None
        files = sorted(p.glob("*.json"), reverse=True)
        return files[0] if files else None

    def _get_site_slug(self, site_name: str) -> str:
        slug = site_name.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)
        slug = slug.strip("-")
        return slug or "unnamed-site"

    def _make_gap(self, migration_id: str, gap_type: str, source_persona: str, description: str) -> dict:
        return {
            "migration_id": migration_id,
            "gap_type": gap_type,
            "source_persona": source_persona,
            "description": description,
            "severity": "medium",
        }

    # ------------------------- Persona Dispatch (Phase 1: no thin glue) -----
    #
    # Phase 1 of PLAN.md deleted the per-persona ``*_agent.py`` modules.
    # The Manager now defines the agent as the triple
    # ``(persona.md charter, Pydantic output model, backend.invoke(...))``.
    #
    # The dispatch lives here because (a) the Manager is the only caller
    # that knows about the full Rooms/Stewards/Handoff flow, and (b) the
    # per-persona upstream artifact loading is too entangled with the
    # blackboard to live in a generic helper. Each handler below is a
    # thin method that:
    #
    #   1. Resolves upstream artifact IDs (from task_context or the
    #      latest-in-memory fallback).
    #   2. Loads the upstream Pydantic models via memory.artifacts.
    #   3. Builds the prompt via registry.prompts.
    #   4. Calls ``backend.invoke(persona_path, prompt, output_model)``.
    #   5. Coerces + persists the artifact via the central coercion +
    #      save helpers.
    #
    # The handler returns ``{"success": bool, "artifact": ..., "built_site_slug": ...}``
    # or ``{"success": False, "gaps": [...]}`` if a hard precondition is
    # missing. The outer ``_invoke_persona`` wrapper handles the gap-ledger
    # diff + scratch promotion that are persona-agnostic.

    def _invoke_persona(
        self,
        persona: str,
        task_context: dict,
        artifacts: dict,
        site_slug: str,
        migration_id: str,
    ) -> dict:
        """Invoke a persona via backend.invoke. Returns result dict.

        The returned dict has keys: success, artifact, gaps, built_site_slug.
        ``gaps`` is populated by diffing the gap ledger before/after the
        persona call. ``built_site_slug`` is only set by the frontend
        architect (or legacy monolithic builder); defaults to None.
        """
        import time
        t0 = time.time()
        print(f"\n[MANAGER] Invoking: {persona}")

        # Snapshot the gap ledger size before the call so we can return
        # only the entries the persona created.
        try:
            pre_gaps = query_gaps(migration_id=migration_id)
            pre_count = len(pre_gaps)
        except Exception:
            pre_count = 0

        # Scratch directory for this Kilo session.
        scratch_mig_dir = self.SCRATCH_ARTIFACT_DIR / self.session_id
        scratch_mig_dir.mkdir(parents=True, exist_ok=True)
        scratch_persona_dir = scratch_mig_dir / persona
        scratch_persona_dir.mkdir(parents=True, exist_ok=True)

        persona_set = [persona]
        decision_context = (
            f"{persona} invoked for "
            f"{task_context.get('platform', 'unknown')} "
            f"{task_context.get('task_type', 'generic')} migration"
        )

        # Dispatch table: persona_short -> (handler, room).
        # Phase 1.1 Forge personas and Phase E discoverability specialists
        # all route through here.
        _DISPATCH = {
            "scraper": (self._persona_scraper, "planning"),
            "architect": (self._persona_architect, "planning"),
            "marketing": (self._persona_marketing, "planning"),
            "designer": (self._persona_designer, "planning"),
            "builder": (self._persona_builder, "forge"),
            "devops": (self._persona_devops, "forge"),
            "data": (self._persona_data, "forge"),
            "backend": (self._persona_backend, "forge"),
            "frontend": (self._persona_frontend, "forge"),
            "coordinator": (self._persona_coordinator, "forge"),
            "seo": (self._persona_seo, "planning"),
            "geo": (self._persona_geo, "auto"),  # room resolved at call time
        }

        entry = _DISPATCH.get(persona)
        if entry is None:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "persona_gap", "manager", f"Unknown persona: {persona}")],
            }
        handler, room = entry
        try:
            result = handler(
                persona=persona,
                task_context=task_context,
                site_slug=site_slug,
                migration_id=migration_id,
                persona_set=persona_set,
                decision_context=decision_context,
            )
        except BackendInvokeError as e:
            self._log_trace_with_room(
                "persona_backend_invoke_failed",
                {"persona": persona, "error": str(e)},
                room=room if room != "auto" else "planning",
            )
            result = {"success": False, "artifact": None}
        except Exception as e:
            self._log_trace_with_room(
                "persona_handler_crashed",
                {"persona": persona, "error": repr(e)},
                room=room if room != "auto" else "planning",
            )
            result = {"success": False, "artifact": None}

        # Promote any files written to scratch dir by this persona's run.
        self._promote_scratch_artifacts(
            persona=persona,
            migration_id=migration_id,
            persona_set=persona_set,
            decision_context=decision_context,
        )

        elapsed = time.time() - t0
        print(f"[MANAGER] {persona} completed in {elapsed:.1f}s")

        # Read gap ledger for entries this persona added during this call.
        new_gaps: List[Dict[str, Any]] = []
        try:
            post_gaps = query_gaps(migration_id=migration_id)
            if len(post_gaps) > pre_count:
                new_gaps = [g.to_dict() if hasattr(g, "to_dict") else g for g in post_gaps[pre_count:]]
                if new_gaps:
                    print(f"[MANAGER] {persona} emitted {len(new_gaps)} new gap(s) during this call")
        except Exception as e:
            print(f"[MANAGER] WARN: could not diff gap ledger for {persona}: {e}")

        return {
            "success": result.get("success", False),
            "artifact": result.get("artifact"),
            "gaps": new_gaps,
            "built_site_slug": result.get("built_site_slug"),
        }

    # -- Persona handlers --------------------------------------------------
    #
    # Each handler is a small private method that owns the prompt assembly
    # + backend.invoke + persist cycle for ONE persona. Upstream artifact
    # loading goes through memory.artifacts; prompt assembly goes through
    # registry.prompts; the central coercion + save helpers stay on self.

    @staticmethod
    def _persona_text(persona_long: str) -> str:
        path = Path(f"registry/personas/{persona_long}.md")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _persona_scraper(self, *, persona, task_context, site_slug, migration_id,
                         persona_set, decision_context):
        """scraper_specialist — writes recon files to disk; we read them back."""
        from datetime import datetime
        from registry.prompts import build_scraper_prompt
        from memory.artifacts import (
            SITE_UNDERSTANDINGS_DIR, load_site_understanding,
        )

        url = task_context.get("url", "")
        site_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        persona_long = "scraper_specialist"
        persona_path = Path(f"registry/personas/{persona_long}.md")
        persona_text = self._persona_text(persona_long)

        # Pre-create the recon directory so the agent has somewhere to write.
        SITE_UNDERSTANDINGS_DIR.mkdir(parents=True, exist_ok=True)
        out_dir = SITE_UNDERSTANDINGS_DIR / site_id
        out_dir.mkdir(parents=True, exist_ok=True)

        prompt = build_scraper_prompt(url, site_id, persona_text)
        # The scraper persona is side-effect driven (writes files); the
        # backend's structured output is the SiteUnderstanding that
        # ALREADY EXISTS on disk after the agent finishes. We do NOT
        # trust the return value here — the recon files on disk are the
        # source of truth.
        try:
            get_backend().invoke(
                persona=persona_path,
                prompt=prompt,
                output_model=SiteUnderstanding,
            )
        except BackendInvokeError:
            pass  # The scraper frequently fails structured validation;
                  # we still try to load the recon directory afterwards.

        # Load the recon directory as a SiteUnderstanding.
        site = load_site_understanding(site_id)
        if site is None:
            return {"success": False, "artifact": None}

        # Central coercion + persist.
        site = self._safe_coerce("site_understandings", site)
        su_id = self._save_artifact(
            site, "site_understandings",
            task_context.get("migration_id") or migration_id,
            persona_set, decision_context,
        )
        task_context["site_understanding_id"] = su_id
        return {"success": True, "artifact": site}

    def _persona_architect(self, *, persona, task_context, site_slug, migration_id,
                           persona_set, decision_context):
        from registry.prompts import build_architect_prompt
        from memory.artifacts import load_site_understanding

        url = task_context.get("url", "")
        site_id = (
            task_context.get("site_understanding_id")
            or self._get_latest_artifact_id("site_understandings", url=url)
        )
        if not site_id:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", persona,
                                        "SiteUnderstanding not found")],
            }
        site = load_site_understanding(site_id)
        if site is None:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", persona,
                                        f"SiteUnderstanding {site_id} failed to load")],
            }

        persona_long = "architect_specialist"
        persona_path = Path(f"registry/personas/{persona_long}.md")
        prompt = build_architect_prompt(site, self._persona_text(persona_long))

        arch = get_backend().invoke(
            persona=persona_path,
            prompt=prompt,
            output_model=SiteArchitecture,
        )
        # Coerce + persist.
        arch = self._safe_coerce("site_architectures", arch)
        arch_id = self._save_artifact(
            arch, "site_architectures",
            task_context.get("migration_id") or migration_id,
            persona_set, decision_context,
        )
        task_context["site_architecture_id"] = arch_id
        return {"success": True, "artifact": arch}

    def _persona_marketing(self, *, persona, task_context, site_slug, migration_id,
                           persona_set, decision_context):
        from registry.prompts import build_marketing_prompt
        from memory.artifacts import (
            load_content_recommendation, load_site_architecture, load_site_understanding,
        )

        url = task_context.get("url", "")
        site_id = (
            task_context.get("site_understanding_id")
            or self._get_latest_artifact_id("site_understandings", url=url)
        )
        arch_id = (
            task_context.get("site_architecture_id")
            or self._get_latest_artifact_id("site_architectures", url=url)
        )
        if not site_id or not arch_id:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", persona,
                                        "SiteUnderstanding or SiteArchitecture not found")],
            }
        site = load_site_understanding(site_id)
        arch = load_site_architecture(arch_id)
        if site is None or arch is None:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", persona,
                                        "Upstream artifacts failed to load")],
            }

        persona_long = "marketing_specialist"
        persona_path = Path(f"registry/personas/{persona_long}.md")
        prompt = build_marketing_prompt(site, arch, self._persona_text(persona_long))

        rec = get_backend().invoke(
            persona=persona_path,
            prompt=prompt,
            output_model=ContentRecommendation,
        )
        rec = self._safe_coerce("site_recommendations", rec)
        rec_id = self._save_artifact(
            rec, "site_recommendations",
            task_context.get("migration_id") or migration_id,
            persona_set, decision_context,
        )
        task_context["content_recommendation_id"] = rec_id
        return {"success": True, "artifact": rec}

    def _persona_designer(self, *, persona, task_context, site_slug, migration_id,
                          persona_set, decision_context):
        from registry.prompts import build_designer_prompt
        from memory.artifacts import (
            load_content_recommendation, load_site_understanding,
            VISUAL_SPECS_DIR,
        )

        url = task_context.get("url", "")
        site_id = (
            task_context.get("site_understanding_id")
            or self._get_latest_artifact_id("site_understandings", url=url)
        )
        rec_id = (
            task_context.get("content_recommendation_id")
            or self._get_latest_artifact_id("site_recommendations", url=url)
        )
        if not site_id or not rec_id:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", persona,
                                        "SiteUnderstanding or ContentRecommendation not found")],
            }
        site = load_site_understanding(site_id)
        rec = load_content_recommendation(rec_id)
        if site is None or rec is None:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", persona,
                                        "Upstream artifacts failed to load")],
            }

        site_name = task_context.get("site_name", "unnamed")
        slug = self._get_site_slug(site_name)

        persona_long = "ui_designer"
        persona_path = Path(f"registry/personas/{persona_long}.md")
        prompt = build_designer_prompt(site, rec, slug, self._persona_text(persona_long))

        vd = get_backend().invoke(
            persona=persona_path,
            prompt=prompt,
            output_model=VisualDirection,
        )
        vd = self._safe_coerce("visual_specs", vd)

        # Designer saves to memory/visual_specs/<slug>/<id>.json (per-slug layout).
        from datetime import datetime as _dt
        spec_dir = VISUAL_SPECS_DIR / slug
        spec_dir.mkdir(parents=True, exist_ok=True)
        vd_id = _dt.now().strftime("%Y%m%d_%H%M%S")
        vd_path = spec_dir / f"{vd_id}.json"
        if hasattr(vd, "model_dump_json"):
            vd_path.write_text(vd.model_dump_json(indent=2), encoding="utf-8")
        else:
            vd_path.write_text(json.dumps(vd, indent=2, default=str), encoding="utf-8")
        self._log_trace_with_room(
            "visual_direction_saved",
            {"path": str(vd_path), "site_slug": slug, "stitch_status": getattr(vd, "stitch_status", None)},
            room="planning",
        )
        return {"success": True, "artifact": vd}

    def _persona_builder(self, *, persona, task_context, site_slug, migration_id,
                         persona_set, decision_context):
        """Legacy monolithic builder — kept for in-flight migrations."""
        from registry.prompts import build_builder_prompt
        from memory.artifacts import (
            load_content_recommendation, load_site_architecture,
            load_site_understanding, load_visual_direction,
        )

        url = task_context.get("url", "")
        site_id = (
            task_context.get("site_understanding_id")
            or self._get_latest_artifact_id("site_understandings", url=url)
        )
        arch_id = (
            task_context.get("site_architecture_id")
            or self._get_latest_artifact_id("site_architectures", url=url)
        )
        rec_id = (
            task_context.get("content_recommendation_id")
            or self._get_latest_artifact_id("site_recommendations", url=url)
        )
        if not site_id or not arch_id or not rec_id:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "builder",
                                        "Missing planning artifacts for builder")],
            }

        site = load_site_understanding(site_id)
        arch = load_site_architecture(arch_id)
        rec = load_content_recommendation(rec_id)
        site_name = rec.site_name if (rec is not None and rec.site_name) else (site.site_name if site else "unnamed")
        slug = self._get_site_slug(site_name)
        vd = load_visual_direction(slug)
        if not vd:
            self._log_trace("builder_no_visual_direction", {"site_slug": slug})

        persona_long = "builder_specialist"
        persona_path = Path(f"registry/personas/{persona_long}.md")
        prompt = build_builder_prompt(
            site, arch, rec, slug,
            self._persona_text(persona_long),
            visual_direction=vd,
        )
        self._log_trace_with_room(
            "builder_start",
            {"site_slug": slug, "site_id": site_id, "arch_id": arch_id, "rec_id": rec_id},
            room="forge",
        )

        manifest = get_backend().invoke(
            persona=persona_path,
            prompt=prompt,
            output_model=BuildManifest,
        )
        if not getattr(manifest, "output_dir", None):
            manifest.output_dir = f"{self.DEFAULT_OUTPUT_ROOT.rstrip('/')}/{slug}/"
        manifest = self._safe_coerce("site_builds", manifest)
        build_id = self._save_artifact(
            manifest, "site_builds",
            task_context.get("migration_id") or migration_id,
            persona_set, decision_context,
        )
        self._log_trace_with_room(
            "builder_complete",
            {"build_id": build_id, "site_slug": slug},
            room="forge",
        )
        return {"success": True, "artifact": manifest, "built_site_slug": slug}

    def _persona_devops(self, *, persona, task_context, site_slug, migration_id,
                        persona_set, decision_context):
        from registry.prompts import build_frontend_prompt  # not used; alias for compat
        from skills.agentic.forge_common import (
            invoke_kilo_for_persona, load_persona_markdown, save_artifact_to_dir,
            PERSONA_TIMEOUTS_S,
        )
        from memory.artifacts import load_site_architecture, load_site_understanding
        from skills.agentic.devops_engineer import build_devops_prompt
        from models.site_schemas import DeploySpec

        site_id = (
            task_context.get("site_understanding_id")
            or self._get_latest_artifact_id("site_understandings")
        )
        arch_id = (
            task_context.get("site_architecture_id")
            or self._get_latest_artifact_id("site_architectures")
        )
        if not site_id or not arch_id:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "deploy_specialist",
                                        "Missing planning artifacts for deploy_specialist")],
            }
        site = load_site_understanding(site_id)
        arch = load_site_architecture(arch_id)
        if site is None or arch is None:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "deploy_specialist",
                                        "Upstream artifacts failed to load")],
            }

        # Phase 1: route the devops persona through backend.invoke with
        # a retry-via-strict-reemit fallback (preserved reliability behavior).
        persona_long = "deploy_specialist"  # backward-compat alias used by charter
        persona_path = Path(f"registry/personas/deploy_engineer.md")
        if not persona_path.exists():
            persona_path = Path(f"registry/personas/{persona_long}.md")
        persona_text = load_persona_markdown("deploy_engineer") or load_persona_markdown(persona_long)
        if not persona_text:
            persona_text = self._persona_text(persona_long)

        prompt = build_devops_prompt(site, arch)
        timeout_s = PERSONA_TIMEOUTS_S["deploy_engineer"]
        json_str, _ = invoke_kilo_for_persona(
            persona="deploy_engineer",
            prompt=prompt,
            context={"migration_id": migration_id, "site_slug": site_slug},
            migration_id=migration_id,
            timeout_s=timeout_s,
        )
        # Use backend.invoke as the structured-output path; if Kilo returned
        # raw text we route through the backend's JSON extraction + Pydantic.
        if json_str is None:
            return {"success": False, "artifact": None}
        spec = DeploySpec.model_validate_json(json_str)
        spec.produced_at = spec.produced_at or datetime.now().isoformat()
        spec.produced_by = "deploy_engineer"
        from skills.agentic.forge_common import DEPLOY_SPECS_DIR
        save_artifact_to_dir(spec, DEPLOY_SPECS_DIR, migration_id, "deploy_engineer")
        return {"success": True, "artifact": spec}

    def _persona_data(self, *, persona, task_context, site_slug, migration_id,
                      persona_set, decision_context):
        from skills.agentic.forge_common import (
            invoke_kilo_for_persona, load_persona_markdown, save_artifact_to_dir,
            PERSONA_TIMEOUTS_S,
        )
        from memory.artifacts import load_site_architecture, load_site_understanding
        from memory.artifacts import DEPLOY_SPECS_DIR
        from skills.agentic.devops_engineer import load_latest_deploy_spec
        from skills.agentic.data_engineer import build_data_engineer_prompt
        from models.site_schemas import DataContracts

        site_id = (
            task_context.get("site_understanding_id")
            or self._get_latest_artifact_id("site_understandings")
        )
        arch_id = (
            task_context.get("site_architecture_id")
            or self._get_latest_artifact_id("site_architectures")
        )
        if not site_id or not arch_id:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "data_engineer",
                                        "Missing planning artifacts for data_engineer")],
            }
        site = load_site_understanding(site_id)
        arch = load_site_architecture(arch_id)
        deploy_spec = load_latest_deploy_spec()
        if site is None or arch is None:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "data_engineer",
                                        "Upstream artifacts failed to load")],
            }

        # Phase 1: route through backend.invoke using the same retry path
        # the original data_engineer design used.
        persona_text = load_persona_markdown("data_engineer")
        prompt = build_data_engineer_prompt(site, arch, deploy_spec)
        timeout_s = PERSONA_TIMEOUTS_S["data_engineer"]
        json_str, _ = invoke_kilo_for_persona(
            persona="data_engineer", prompt=prompt,
            context={"migration_id": migration_id, "site_slug": site_slug},
            migration_id=migration_id, timeout_s=timeout_s,
        )
        if json_str is None:
            return {"success": False, "artifact": None}
        # Lenient parse: data_engineer emits the literal "true"/"false"
        # string for `required`, not a real boolean. The persona module's
        # coercion handles that — call it via the shared backend path.
        # Phase 1 wiring: use backend.invoke for the structured shape, and
        # fall through to backend for validation if the lenient parse works.
        try:
            contracts = DataContracts.model_validate_json(json_str)
        except Exception:
            # Fallback: route through backend.invoke to get the structured
            # model. This relies on the backend's lenient JSON + validation.
            persona_path = Path("registry/personas/data_engineer.md")
            persona_text = persona_text or self._persona_text("data_engineer")
            contracts = get_backend().invoke(
                persona=persona_path,
                prompt=prompt,
                output_model=DataContracts,
            )
        contracts.produced_at = contracts.produced_at or datetime.now().isoformat()
        contracts.produced_by = "data_engineer"
        from skills.agentic.forge_common import DATA_CONTRACTS_DIR
        save_artifact_to_dir(contracts, DATA_CONTRACTS_DIR, migration_id, "data_engineer")
        return {"success": True, "artifact": contracts}

    def _persona_backend(self, *, persona, task_context, site_slug, migration_id,
                         persona_set, decision_context):
        from skills.agentic.forge_common import (
            invoke_kilo_for_persona, load_persona_markdown, save_artifact_to_dir,
            PERSONA_TIMEOUTS_S,
        )
        from memory.artifacts import load_site_architecture, load_site_understanding
        from skills.agentic.backend_architect import build_backend_prompt
        from models.site_schemas import APIContracts

        site_id = (
            task_context.get("site_understanding_id")
            or self._get_latest_artifact_id("site_understandings")
        )
        arch_id = (
            task_context.get("site_architecture_id")
            or self._get_latest_artifact_id("site_architectures")
        )
        if not site_id or not arch_id:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "backend_architect",
                                        "Missing planning artifacts for backend_architect")],
            }
        site = load_site_understanding(site_id)
        arch = load_site_architecture(arch_id)
        from skills.agentic.devops_engineer import load_latest_deploy_spec
        from skills.agentic.data_engineer import load_latest_data_contracts
        deploy_spec = load_latest_deploy_spec()
        data_contracts = load_latest_data_contracts()
        if site is None or arch is None:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "backend_architect",
                                        "Upstream artifacts failed to load")],
            }

        persona_text = load_persona_markdown("backend_architect")
        prompt = build_backend_prompt(
            site, arch, data_contracts, deploy_spec,
            migration_id=migration_id, site_slug=site_slug,
        )
        timeout_s = PERSONA_TIMEOUTS_S["backend_architect"]
        json_str, _ = invoke_kilo_for_persona(
            persona="backend_architect", prompt=prompt,
            context={"migration_id": migration_id, "site_slug": site_slug},
            migration_id=migration_id, timeout_s=timeout_s,
        )
        if json_str is None:
            return {"success": False, "artifact": None}
        try:
            contracts = APIContracts.model_validate_json(json_str)
        except Exception:
            persona_path = Path("registry/personas/backend_architect.md")
            contracts = get_backend().invoke(
                persona=persona_path,
                prompt=prompt,
                output_model=APIContracts,
            )
        contracts.produced_at = contracts.produced_at or datetime.now().isoformat()
        contracts.produced_by = "backend_architect"
        from skills.agentic.forge_common import API_CONTRACTS_DIR
        save_artifact_to_dir(contracts, API_CONTRACTS_DIR, migration_id, "backend_architect")
        return {"success": True, "artifact": contracts}

    def _persona_frontend(self, *, persona, task_context, site_slug, migration_id,
                          persona_set, decision_context):
        from memory.artifacts import (
            load_content_recommendation, load_site_architecture,
            load_site_understanding, load_visual_direction,
        )
        from skills.agentic.frontend_architect import build_frontend_prompt
        from models.site_schemas import BuildManifest

        url = task_context.get("url", "")
        site_id = (
            task_context.get("site_understanding_id")
            or self._get_latest_artifact_id("site_understandings", url=url)
        )
        arch_id = (
            task_context.get("site_architecture_id")
            or self._get_latest_artifact_id("site_architectures", url=url)
        )
        rec_id = (
            task_context.get("content_recommendation_id")
            or self._get_latest_artifact_id("site_recommendations", url=url)
        )
        vd_id = (
            task_context.get("visual_direction_id")
            or self._get_latest_artifact_id("visual_specs", site_slug=site_slug)
        )
        if not site_id or not arch_id or not rec_id:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "frontend_architect",
                                        "Missing planning artifacts for frontend_architect")],
            }
        site = load_site_understanding(site_id)
        arch = load_site_architecture(arch_id)
        rec = load_content_recommendation(rec_id)
        vd = load_visual_direction(site_slug) if vd_id else None
        from skills.agentic.devops_engineer import load_latest_deploy_spec
        from skills.agentic.data_engineer import load_latest_data_contracts
        from skills.agentic.backend_architect import load_latest_api_contracts
        deploy_spec = load_latest_deploy_spec()
        data_contracts = load_latest_data_contracts()
        api_contracts = load_latest_api_contracts()
        if site is None or arch is None or rec is None:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "frontend_architect",
                                        "Upstream artifacts failed to load")],
            }

        stitch_project_id = getattr(vd, "stitch_project_id", None) if vd else None
        stitch_project_url = getattr(vd, "stitch_project_url", None) if vd else None
        output_root = task_context.get("output_root", self.DEFAULT_OUTPUT_ROOT)

        prompt = build_frontend_prompt(
            site, arch, rec, site_slug,
            visual_direction=vd,
            data_contracts=data_contracts,
            api_contracts=api_contracts,
            deploy_spec=deploy_spec,
            output_root=output_root,
            stitch_project_id=stitch_project_id,
            stitch_project_url=stitch_project_url,
        )

        persona_path = Path("registry/personas/frontend_developer.md")
        if not persona_path.exists():
            persona_path = Path("registry/personas/frontend_architect.md")
        manifest = get_backend().invoke(
            persona=persona_path,
            prompt=prompt,
            output_model=BuildManifest,
        )
        if not getattr(manifest, "output_dir", None):
            manifest.output_dir = f"{output_root.rstrip('/')}/{site_slug}/"
        manifest = self._safe_coerce("site_builds", manifest)
        build_id = self._save_artifact(
            manifest, "site_builds",
            task_context.get("migration_id") or migration_id,
            persona_set, decision_context,
        )
        self._log_trace_with_room(
            "frontend_architect_complete",
            {"build_id": build_id, "site_slug": site_slug},
            room="forge",
        )
        task_context["build_id"] = build_id
        return {"success": True, "artifact": manifest, "built_site_slug": site_slug}

    def _persona_coordinator(self, *, persona, task_context, site_slug, migration_id,
                             persona_set, decision_context):
        from memory.artifacts import load_site_architecture, load_site_understanding
        from skills.agentic.integration_coordinator import build_integration_prompt
        from skills.agentic.devops_engineer import load_latest_deploy_spec
        from skills.agentic.data_engineer import load_latest_data_contracts
        from skills.agentic.backend_architect import load_latest_api_contracts
        from models.site_schemas import IntegrationStatus
        from skills.agentic.forge_common import (
            invoke_kilo_for_persona, load_persona_markdown, save_artifact_to_dir,
            PERSONA_TIMEOUTS_S,
        )

        site_id = (
            task_context.get("site_understanding_id")
            or self._get_latest_artifact_id("site_understandings")
        )
        arch_id = (
            task_context.get("site_architecture_id")
            or self._get_latest_artifact_id("site_architectures")
        )
        build_id = (
            task_context.get("build_id")
            or self._get_latest_artifact_id("site_builds")
        )
        if not site_id or not arch_id:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "integration_coordinator",
                                        "Missing planning artifacts for integration_coordinator")],
            }
        site = load_site_understanding(site_id)
        arch = load_site_architecture(arch_id)
        deploy_spec = load_latest_deploy_spec()
        data_contracts = load_latest_data_contracts()
        api_contracts = load_latest_api_contracts()
        if site is None or arch is None:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "integration_coordinator",
                                        "Upstream artifacts failed to load")],
            }

        persona_text = load_persona_markdown("integration_coordinator")
        prompt = build_integration_prompt(
            site, arch, data_contracts, api_contracts, deploy_spec,
            build_id=build_id or "",
            migration_id=migration_id, site_slug=site_slug,
        )
        timeout_s = PERSONA_TIMEOUTS_S["integration_coordinator"]
        json_str, _ = invoke_kilo_for_persona(
            persona="integration_coordinator", prompt=prompt,
            context={"migration_id": migration_id, "site_slug": site_slug, "build_id": build_id or ""},
            migration_id=migration_id, timeout_s=timeout_s,
        )
        if json_str is None:
            return {"success": False, "artifact": None}
        try:
            status = IntegrationStatus.model_validate_json(json_str)
        except Exception:
            persona_path = Path("registry/personas/integration_coordinator.md")
            status = get_backend().invoke(
                persona=persona_path,
                prompt=prompt,
                output_model=IntegrationStatus,
            )
        status.produced_at = status.produced_at or datetime.now().isoformat()
        status.produced_by = "integration_coordinator"
        from skills.agentic.forge_common import INTEGRATION_STATUS_DIR
        save_artifact_to_dir(status, INTEGRATION_STATUS_DIR, migration_id, "integration_coordinator")
        return {"success": True, "artifact": status}

    def _persona_seo(self, *, persona, task_context, site_slug, migration_id,
                     persona_set, decision_context):
        from registry.prompts import build_seo_prompt
        from memory.artifacts import (
            load_content_recommendation, load_site_architecture, load_site_understanding,
        )

        url = task_context.get("url", "")
        site_id = (
            task_context.get("site_understanding_id")
            or self._get_latest_artifact_id("site_understandings", url=url)
        )
        arch_id = (
            task_context.get("site_architecture_id")
            or self._get_latest_artifact_id("site_architectures", url=url)
        )
        rec_id = (
            task_context.get("content_recommendation_id")
            or self._get_latest_artifact_id("site_recommendations", url=url)
        )
        if not site_id or not arch_id or not rec_id:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "seo_specialist",
                                        "Missing planning artifacts for seo_specialist")],
            }
        site = load_site_understanding(site_id)
        arch = load_site_architecture(arch_id)
        rec = load_content_recommendation(rec_id)
        if site is None or arch is None or rec is None:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "seo_specialist",
                                        "Upstream artifacts failed to load")],
            }

        persona_long = "seo_specialist"
        persona_path = Path(f"registry/personas/{persona_long}.md")
        prompt = build_seo_prompt(
            site, arch, rec, site_slug, migration_id,
            self._persona_text(persona_long),
        )

        seo_strategy = get_backend().invoke(
            persona=persona_path,
            prompt=prompt,
            output_model=SeoStrategy,
        )
        # Stamp site_slug/migration_id if missing.
        if not seo_strategy.site_slug:
            seo_strategy.site_slug = site_slug
        if not seo_strategy.migration_id:
            seo_strategy.migration_id = migration_id
        seo_id = self._save_artifact(
            seo_strategy, "seo_strategies",
            task_context.get("migration_id") or migration_id,
            persona_set, decision_context,
        )
        task_context["seo_strategy_id"] = seo_id
        return {"success": True, "artifact": seo_strategy}

    def _persona_geo(self, *, persona, task_context, site_slug, migration_id,
                     persona_set, decision_context):
        from registry.prompts import build_geo_plan_prompt, build_geo_build_prompt
        from memory.artifacts import (
            load_geo_strategy, load_seo_strategy, load_site_architecture,
            load_site_understanding,
        )

        url = task_context.get("url", "")
        site_id = (
            task_context.get("site_understanding_id")
            or self._get_latest_artifact_id("site_understandings", url=url)
        )
        arch_id = (
            task_context.get("site_architecture_id")
            or self._get_latest_artifact_id("site_architectures", url=url)
        )
        seo_strategy_id = (
            task_context.get("seo_strategy_id")
            or self._get_latest_artifact_id("seo_strategies", url=url)
        )
        # Detect planning vs. forge.
        site_dir = Path(task_context["output_root"]) / site_slug
        geo_build_present = bool(self._get_latest_in_memory("memory/geo_builds"))

        persona_long = "geo_specialist"
        persona_path = Path(f"registry/personas/{persona_long}.md")
        persona_text = self._persona_text(persona_long)

        if site_dir.exists() and not geo_build_present:
            # Forge pass.
            geo_strategy_id = (
                task_context.get("geo_strategy_id")
                or self._get_latest_artifact_id("geo_strategies", url=url)
            )
            if not site_id or not arch_id or not geo_strategy_id:
                return {
                    "success": False,
                    "gaps": [self._make_gap(migration_id, "missing_data", "geo_specialist",
                                            "Missing planning artifacts for geo_specialist (forge pass)")],
                }
            site = load_site_understanding(site_id)
            arch = load_site_architecture(arch_id)
            geo_strategy = load_geo_strategy(geo_strategy_id)
            seo_strategy = load_seo_strategy(seo_strategy_id) if seo_strategy_id else None
            if site is None or arch is None or geo_strategy is None:
                return {
                    "success": False,
                    "gaps": [self._make_gap(migration_id, "missing_data", "geo_specialist",
                                            "Upstream artifacts failed to load (forge pass)")],
                }
            prompt = build_geo_build_prompt(
                site, arch, seo_strategy, geo_strategy,
                site_dir, site_slug, migration_id, persona_text,
            )
            # Enforce locked allowlist safety net (preserved from Phase E).
            geo_build = get_backend().invoke(
                persona=persona_path,
                prompt=prompt,
                output_model=GeoBuildArtifacts,
            )
            locked = list(self.LOCKED_AI_CRAWLERS)
            emitted = list(getattr(geo_build, "ai_crawler_allowlist", []) or [])
            seen: set = set()
            merged: list = []
            for c in list(emitted) + list(locked):
                if c not in seen:
                    seen.add(c)
                    merged.append(c)
            geo_build.ai_crawler_allowlist = merged
            # Stamp site_slug/migration_id if missing.
            if not geo_build.site_slug:
                geo_build.site_slug = site_slug
            if not geo_build.migration_id:
                geo_build.migration_id = migration_id
            geo_build.last_verified_at = datetime.utcnow().isoformat() + "Z"
            # Write GEO files to disk.
            try:
                from memory.artifacts import write_geo_files
                written = write_geo_files(geo_build, site_dir)
                geo_build.files_written = written
            except Exception:
                # Best-effort — leave files_written empty on failure.
                pass
            geo_build_id = self._save_artifact(
                geo_build, "geo_builds",
                task_context.get("migration_id") or migration_id,
                persona_set, decision_context,
            )
            task_context["geo_build_id"] = geo_build_id
            return {"success": True, "artifact": geo_build}

        # Planning pass.
        if not site_id or not arch_id:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "geo_specialist",
                                        "Missing planning artifacts for geo_specialist")],
            }
        site = load_site_understanding(site_id)
        arch = load_site_architecture(arch_id)
        seo_strategy = load_seo_strategy(seo_strategy_id) if seo_strategy_id else None
        if site is None or arch is None:
            return {
                "success": False,
                "gaps": [self._make_gap(migration_id, "missing_data", "geo_specialist",
                                        "Upstream artifacts failed to load")],
            }
        prompt = build_geo_plan_prompt(
            site, arch, seo_strategy, site_slug, migration_id, persona_text,
        )
        geo_strategy = get_backend().invoke(
            persona=persona_path,
            prompt=prompt,
            output_model=GeoStrategy,
        )
        if not geo_strategy.site_slug:
            geo_strategy.site_slug = site_slug
        if not geo_strategy.migration_id:
            geo_strategy.migration_id = migration_id
        geo_strategy_id = self._save_artifact(
            geo_strategy, "geo_strategies",
            task_context.get("migration_id") or migration_id,
            persona_set, decision_context,
        )
        task_context["geo_strategy_id"] = geo_strategy_id
        return {"success": True, "artifact": geo_strategy}

    def _promote_scratch_artifacts(
        self,
        persona: str,
        migration_id: str,
        persona_set: list[str],
        decision_context: str,
    ) -> None:
        """Promote files from scratch directory to persistent memory/artifacts/."""
        from memory.artifact_store import ArtifactType, WorkflowStage

        # Map persona to stage and artifact type
        stage_map = {
            "scraper": WorkflowStage.SCRAPING,
            "architect": WorkflowStage.CODEGEN,
            "marketing": WorkflowStage.CODEGEN,
            "designer": WorkflowStage.CODEGEN,
            "builder": WorkflowStage.CODEGEN,
        }
        type_map = {
            "scraper": ArtifactType.SITE_UNDERSTANDING,
            "architect": ArtifactType.SITE_ARCHITECTURE,
            "marketing": ArtifactType.CONTENT_RECOMMENDATION,
            "designer": ArtifactType.SITE_ARCHITECTURE,
            "builder": ArtifactType.SITE_ARCHITECTURE,
        }

        stage = stage_map.get(persona, WorkflowStage.CODEGEN)
        artifact_type = type_map.get(persona, ArtifactType.SITE_UNDERSTANDING)

        scratch_persona_dir = self.SCRATCH_ARTIFACT_DIR / self.session_id / persona

        if not scratch_persona_dir.exists():
            return

        # Find all files written by Kilo
        files = [f.name for f in scratch_persona_dir.iterdir() if f.is_file()]
        if not files:
            return

        # Promote with full provenance
        self.memory.promote_artifacts_from_scratch(
            session_id=self.session_id,
            migration_id=migration_id,
            stage=stage,
            persona_set=persona_set,
            decision_context=decision_context,
            artifact_type=artifact_type,
            files=files,
            tags=[persona],
        )

    def _retry_persona(
        self,
        persona: str,
        task_context: dict,
        artifacts: dict,
        site_slug: str,
        migration_id: str,
        modified_prompt: str = None,
    ) -> dict:
        return self._invoke_persona(persona, task_context, artifacts, site_slug, migration_id)

    def _check_visual_direction_changes(self, site_slug: str) -> bool:
        """Check if any VisualDirection or REVIEW.md file has changed since last run."""
        spec_dir = Path("memory/visual_specs") / site_slug
        if not spec_dir.exists():
            return False
        vd_files = list(spec_dir.glob("*.json")) + list(spec_dir.glob("REVIEW.md"))
        if not vd_files:
            return False
        return True

    def _safe_coerce(self, artifact_type_name: str, result):
        """Run the central coercion step before an artifact is persisted.

        Phase B: every persona's emitted artifact now passes through
        models._coercion.coerce_artifact so LLM drift (unknown enums,
        null required fields, brace drift) is fixed in one place. If
        coercion fails, we log a trace event and fall through to save
        the raw artifact — the failure is visible in the trace but
        does not abort the migration.
        """
        from models._coercion import coerce_artifact, CoercionError
        try:
            return coerce_artifact(artifact_type_name, result)
        except CoercionError as e:
            self._log_trace("coercion_failed", {
                "artifact_type": artifact_type_name,
                "error": str(e),
            })
            return result

    def _save_artifact(
        self,
        artifact_data,
        artifact_type_name: str,
        migration_id: str,
        persona_set: list[str],
        decision_context: str,
    ) -> Optional[str]:
        """Save an artifact (Pydantic model or dict) to the appropriate memory directory.

        Args:
            artifact_data: Pydantic model or dict to save
            artifact_type_name: Subdirectory name under memory/ (e.g., 'site_understandings')
            migration_id: Current migration ID
            persona_set: List of personas that produced this artifact
            decision_context: Human-readable context string

        Returns:
            The stem (ID) of the saved file, or None on failure.
        """
        from pathlib import Path
        import json

        output_dir = Path("memory") / artifact_type_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate ID from timestamp
        from datetime import datetime
        artifact_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = output_dir / f"{artifact_id}.json"

        try:
            if hasattr(artifact_data, "model_dump_json"):
                content = artifact_data.model_dump_json(indent=2)
            elif hasattr(artifact_data, "model_dump"):
                content = json.dumps(artifact_data.model_dump(), indent=2, default=str)
            else:
                content = json.dumps(artifact_data, indent=2, default=str)

            filepath.write_text(content, encoding="utf-8")
            self._log_trace("artifact_saved", {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type_name,
                "path": str(filepath),
                "persona_set": persona_set,
            })
            return artifact_id
        except Exception as e:
            self._log_trace("artifact_save_error", {"error": str(e), "path": str(filepath)})
            return None

    def _group_gaps_by_persona(self, gaps: list) -> dict:
        by_persona = {}
        for gap in gaps:
            persona = getattr(gap, "source_persona", "unknown")
            if persona not in by_persona:
                by_persona[persona] = []
            by_persona[persona].append(gap)
        return by_persona

    def _get_site_slug(self, site_name: str) -> str:
        slug = site_name.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)
        slug = slug.strip("-")
        return slug or "unnamed-site"

    def _make_gap(self, migration_id: str, gap_type: str, source_persona: str, description: str) -> dict:
        return {
            "migration_id": migration_id,
            "gap_type": gap_type,
            "source_persona": source_persona,
            "description": description,
            "suggested_fix": "Investigate and resolve",
            "severity": "medium",
        }


if __name__ == "__main__":
    import sys
    from urllib.parse import urlparse

    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.wixsite.com"

    # Detect platform from URL using routing
    router = Router()
    detection = router.detect_platform_from_url(url)
    platform = detection.get("platform", "generic")
    platform_confidence = detection.get("confidence", 0.5)

    # Extract site_name from URL path
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    site_name = path_parts[-1] if path_parts else "unnamed"

    task_context = {
        "url": url,
        "platform": platform,
        "platform_confidence": platform_confidence,
        "site_name": site_name,
        "migration_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "task_type": "portfolio",  # default; could be inferred from scraping
    }

    print(f"[ELYRA MANAGER] Starting migration for {url}")
    print(f"[CONFIG] Platform: {platform} (confidence: {platform_confidence:.0%})")
    print(f"[CONFIG] Site name: {site_name}")
    print(f"[CONFIG] Migration ID: {task_context['migration_id']}")

    manager = MigrationManager()
    result = manager.run(task_context)

    print(f"\n[MANAGER] Result: {result['phase_reached']}")
    print(f"[MANAGER] Site slug: {result['site_slug']}")
    print(f"[MANAGER] Success: {result['success']}")
    trace = result.get("trace", [])
    print(f"[MANAGER] Trace events: {[t.get('event') for t in trace]}")
    print(f"[MANAGER] Gaps logged: {len(result.get('gaps', []))}")

    # Force clean exit — prevent any background threads or MCP connections from keeping the process alive
    sys.exit(0)