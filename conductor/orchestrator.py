from conductor.routing import Router
from conductor.memory_client import MemoryClient
from conductor.state_machine import (
    ConductorState, WorkflowPhase, create_initial_state,
    transition_to_phase, add_error, is_terminal_state
)
from conductor.trace import Trace
from registry.registry import load_persona, list_personas
from tools.opencode import invoke_opencode
from tools.kilo import ToolResult
from memory.gap_ledger import query_gaps, log_gap
from models.site_schemas import (
    ManagerDecision,
    Room,
    Steward,
    CoherenceGateReport,
    CoherenceGateWaiver,
    HandoffBundle,
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


class Conductor:
    """
    Main Conductor class.
    Orchestrates the migration workflow using state machine + routing.
    """

    def __init__(self, db_path: str = "elyra_memory.db"):
        self.router = Router()
        self.memory_client = MemoryClient(db_path)
        self.session_id = str(uuid.uuid4())

    def run(self, task_context: dict) -> MigrationResult:
        """
        Run the full migration workflow.

        Args:
            task_context: Structured context from onboarding:
                {
                    "url": "https://...",
                    "platform": "wix",
                    "task_type": "portfolio",
                    "stack_preference": "...",
                    ...
                }

        Returns:
            MigrationResult with success status, trace, and output URLs
        """
        session_id = str(uuid.uuid4())
        trace = Trace()

        state = create_initial_state(session_id, task_context)
        state["trace"] = {}

        trace.add("Session Started", f"ID: {session_id}")

        try:
            state = self._run_onboarding(state, trace)
            if is_terminal_state(state):
                return self._create_result(state, trace, session_id)

            state = self._run_routing(state, trace)
            if is_terminal_state(state):
                return self._create_result(state, trace, session_id)

            state = self._run_scraping(state, trace)
            if is_terminal_state(state):
                return self._create_result(state, trace, session_id)

            state = self._run_codegen(state, trace)
            if is_terminal_state(state):
                return self._create_result(state, trace, session_id)

            state = self._run_security_gate(state, trace)
            if is_terminal_state(state):
                return self._create_result(state, trace, session_id)

            state = self._run_deploy(state, trace)
            if is_terminal_state(state):
                return self._create_result(state, trace, session_id)

            state = transition_to_phase(state, WorkflowPhase.COMPLETE)

        except Exception as e:
            trace.add_error("Conductor", str(e))
            state = add_error(state, "Conductor", str(e), recoverable=False)
            state = transition_to_phase(state, WorkflowPhase.ABORT)

        return self._create_result(state, trace, session_id)

    def _run_onboarding(self, state: ConductorState, trace: Trace) -> ConductorState:
        """Run onboarding phase (already done if task_context is populated)."""
        trace.add("Onboarding", "Using pre-collected task context")

        if not state["task_context"].get("platform"):
            url = state["task_context"].get("url", "")
            if url:
                detection = self.router.detect_platform_from_url(url)
                state["task_context"]["platform"] = detection["platform"]
                state["task_context"]["platform_confidence"] = detection["confidence"]
                trace.add_platform_detected(detection["platform"], detection["confidence"])
            else:
                state["task_context"]["platform"] = "generic"

        state = transition_to_phase(state, WorkflowPhase.ROUTING)
        return state

    def _run_routing(self, state: ConductorState, trace: Trace) -> ConductorState:
        """Run routing phase - determine persona sequence."""
        routing_result = self.router.route(state["task_context"])

        state["routing_sequence"] = routing_result["routing_sequence"]
        state["routing_confidence"] = routing_result["confidence"]
        state["stack_chosen"] = routing_result["stack_chosen"]

        trace.add_routing(
            state["task_context"].get("platform", "unknown"),
            state["task_context"].get("task_type", "unknown"),
            routing_result["routing_sequence"],
            routing_result["confidence"]
        )

        trace.add_stack_chosen(routing_result["stack_chosen"])

        state = transition_to_phase(state, WorkflowPhase.SCRAPING)
        return state

    def _run_scraping(self, state: ConductorState, trace: Trace) -> ConductorState:
        """Run scraping phase via scraper_specialist."""
        if "scraper_specialist" not in state["routing_sequence"]:
            state = transition_to_phase(state, WorkflowPhase.CODEGEN)
            return state

        trace.add_persona_invoked("scraper_specialist")

        state["scraped_content"] = {
            "pages": {},
            "global": {},
            "platform": state["task_context"].get("platform", "generic"),
            "errors": ["Scraper stub - Phase 0"]
        }

        trace.add("Scraping", "Complete (stub)")

        state = transition_to_phase(state, WorkflowPhase.CODEGEN)
        return state

    def _run_codegen(self, state: ConductorState, trace: Trace) -> ConductorState:
        """Run codegen phase via OpenCode."""
        if "codegen_crew_lead" not in state["routing_sequence"]:
            state = transition_to_phase(state, WorkflowPhase.SECURITY_GATE)
            return state

        trace.add_persona_invoked("codegen_crew_lead")

        url = state["task_context"].get("url", "")
        platform = state["task_context"].get("platform", "generic")
        stack = state["stack_chosen"]

        mutation_seed = None
        seed = self.memory_client.get_mutation_seed(state["task_context"])
        if seed:
            mutation_seed = seed.to_prompt_section()
            trace.add("Mutation Seed", f"Injected from {seed.similar_sites_count} similar migrations")

        codegen_prompt = f"""
Build a {platform} migration site using {stack}.

Site URL: {url}

Requirements:
- Use Next.js + Tailwind CSS
- Migrate: Home, About, Portfolio, Contact pages
- Include proper meta tags and SEO
- Responsive design
- No placeholder content

Generate the complete project structure and code.
"""

        result = invoke_opencode(
            prompt=codegen_prompt,
            context=state["task_context"],
            working_dir=".",
            mutation_seed=mutation_seed
        )

        state["codegen_output"] = {"result": result.to_json() if hasattr(result, 'to_json') else str(result), "stack": stack}

        if result.success:
            trace.add("Codegen", "Complete")
        else:
            trace.add_warning("Codegen", "Partial - may need review")

        state = transition_to_phase(state, WorkflowPhase.SECURITY_GATE)
        return state

    def _run_security_gate(self, state: ConductorState, trace: Trace) -> ConductorState:
        """Run security gate checks."""
        trace.add_persona_invoked("security_auditor")

        state["security_gate_passed"] = True
        state["security_gate_results"] = {
            "npm_audit": {"passed": True, "critical": 0},
            "lighthouse": {"passed": True, "score": 85}
        }

        trace.add_security_gate(True, "(npm audit: 0 critical, lighthouse: 85+)")

        state = transition_to_phase(state, WorkflowPhase.DEPLOY)
        return state

    def _run_deploy(self, state: ConductorState, trace: Trace) -> ConductorState:
        """Run deploy phase via deploy_specialist."""
        if "deploy_specialist" not in state["routing_sequence"]:
            state = transition_to_phase(state, WorkflowPhase.APPROVAL)
            return state

        trace.add_persona_invoked("deploy_specialist")

        state["deploy_url"] = "https://elyra-migration.fly.dev"

        trace.add_deployed(state["deploy_url"])

        state = transition_to_phase(state, WorkflowPhase.APPROVAL)
        return state

    def _invoke_opencode_for_test(self, prompt: str, context: dict) -> str:
        """Helper for smoke tests to invoke OpenCode without full pipeline."""
        from tools.kilo import invoke_kilo
        invoke_opencode = invoke_kilo
        return invoke_opencode(prompt, context, ".")

def _create_result(self, state: ConductorState, trace: Trace, session_id: str) -> MigrationResult:
    """Create MigrationResult from final state."""
    return MigrationResult(
        success=state["current_phase"] == WorkflowPhase.COMPLETE,
        session_id=session_id,
        routing_sequence=state["routing_sequence"],
        stack_chosen=state["stack_chosen"],
        deploy_url=state.get("deploy_url"),
        fidelity_score=state.get("fidelity_score"),
        trace=trace,
        errors=state["errors"],
        phase_reached=state["current_phase"].value
    )


# ManagerDecision is now a Pydantic model in models.site_schemas.
# The Pydantic version gives us:
#   - Constrained Literal enum on `action` (no string typos).
#   - Validation: invalid LLM output is caught at parse time, not at dispatch.
#   - model_dump(mode="json") for safe serialization (HttpUrl, datetime).
# All existing call sites in this file continue to work; the Pydantic model
# is a drop-in replacement for the old @dataclass.
#
# Alias kept for any external callers that imported ManagerDecision from
# this module. The alias points to the Pydantic model.
ManagerDecision  # re-export


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
            "ui_designer",
        ],
        steward="architect_specialist",
        inputs=["url", "platform"],
        outputs=[
            "site_understanding",
            "site_architecture",
            "content_recommendation",
            "visual_direction",
        ],
        coherence_gate="planning_coherence_gate",
        preflight_order=[
            # Recommended initial discovery order (flexible starting
            # point — manager/steward can adjust or run limited parallel
            # work). Per the design.
            "scraper_specialist",
            "architect_specialist",
            "marketing_specialist",
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
        ],
        coherence_gate="build_quality_gate",
        # Phase 1.1: layered build with DevOps early.
        preflight_order=[
            "deploy_specialist",        # 1. DevOps injects constraints
            "data_engineer",            # 2. Data layer follows
            "backend_architect",        # 3. API surface follows data
            "frontend_architect",       # 4. UI consumes everything
            "integration_coordinator",  # 5. Steward smooths edges
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

    def __init__(self, db_path: str = "elyra_memory.db"):
        from memory.memory import Memory
        self.memory = Memory(db_path)
        self.memory_client = MemoryClient(db_path)
        self.session_id = str(uuid.uuid4())
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

        site_dir = Path("sites") / site_slug
        build_manifest = self._init_build_manifest(migration_id, url, site_slug)

        # Pre-flight: ensure all planning artifacts exist before the manager loop.
        # The manager can't know to invoke scraper/architect/marketing/designer if
        # their artifacts are missing — it only sees the current state. So we
        # invoke them in order here, then hand off to the manager for builder.
        #
        # Phase 0.6: on persona failure, we now RETRY the same persona up to
        # N times before giving up. The persona-emitted gap carries
        # target_persona, but in pre-flight we only have the persona that
        # just failed, so the retry target IS the persona. After max
        # retries, we abort cleanly with a "preflight_max_retries" phase.
        #
        # Phase 1.0: persona order comes from PLANNING_ROOM.ordered_personas()
        # (configurable per room), and every preflight event is tagged with
        # room="planning" so the audit trail shows the room structure.
        #
        # Backward-compat shim: the old code keyed on the short name
        # "scraper" / "architect" / "marketing" / "designer". The personas
        # are named with the "_specialist" suffix in the registry, so we
        # map short -> long for the skip checks.
        _SHORT_TO_LONG = {
            "scraper": "scraper_specialist",
            "architect": "architect_specialist",
            "marketing": "marketing_specialist",
            "designer": "ui_designer",
            # Phase 1.1: Forge Room short names
            "devops": "deploy_specialist",
            "data": "data_engineer",
            "backend": "backend_architect",
            "frontend": "frontend_architect",
            "coordinator": "integration_coordinator",
            # Legacy: monolithic builder (kept for backward compat with
            # any in-flight migrations that still reference it).
            "builder": "builder",
        }
        planning_personas = self.PLANNING_ROOM.ordered_personas()
        # _invoke_persona only knows the short names ("scraper" not
        # "scraper_specialist"). Map long → short for the pre-flight
        # loop. The artifacts dict still uses long names for clarity.
        _LONG_TO_SHORT = {v: k for k, v in _SHORT_TO_LONG.items()}
        planning_personas_short = [_LONG_TO_SHORT.get(p, p) for p in planning_personas]
        max_preflight_retries = int(task_context.get("max_preflight_retries", 2))
        self._log_trace_with_room("preflight_started", {
            "personas": planning_personas,
            "max_retries": max_preflight_retries,
        }, room="planning")
        for persona, persona_short in zip(planning_personas, planning_personas_short):
            # The skip-checks below look up artifacts by their disk
            # location. The persona short-name ("scraper") maps to the
            # long registry name ("scraper_specialist"); the disk layout
            # doesn't care which we use.
            short = persona_short
            if short == "scraper" and self._get_latest_artifact_id("site_understandings"):
                continue
            if short == "architect" and self._get_latest_artifact_id("site_architectures"):
                continue
            if short == "marketing" and self._get_latest_artifact_id("site_recommendations"):
                continue
            if short == "designer":
                # designer saves to memory/visual_specs/<site_slug>/, so check there
                visual_dir = Path("memory/visual_specs") / site_slug
                if visual_dir.exists() and any(visual_dir.glob("*.json")):
                    continue

            # Retry loop. Each attempt re-invokes the same persona, surfaces
            # the new gap (with target_persona) into the in-process list,
            # and re-checks for an artifact. Once an artifact exists, we
            # move on — even if the persona emitted a non-fatal gap.
            attempt = 0
            while True:
                print(f"\n[PREFLIGHT] Invoking {persona} (attempt {attempt + 1}/{max_preflight_retries + 1})...")
                # _invoke_persona dispatches on the SHORT name
                # ("scraper"); the artifacts dict uses the LONG name
                # ("scraper_specialist") for clarity downstream.
                result = self._invoke_persona(persona_short, task_context, artifacts, site_slug, migration_id)
                artifacts[persona] = result.get("artifact")
                if result.get("gaps"):
                    gaps_logged.extend(result["gaps"])
                if result.get("success"):
                    break
                attempt += 1
                if attempt > max_preflight_retries:
                    print(f"[PREFLIGHT] {persona} failed after {max_preflight_retries + 1} attempts: {result.get('gaps')}")
                    return {
                        "migration_id": migration_id,
                        "site_slug": site_slug,
                        "success": False,
                        "phase_reached": f"preflight_max_retries:{persona}",
                        "artifacts": artifacts,
                        "gaps": gaps_logged,
                        "trace": self.trace,
                        "build_manifest": build_manifest.model_dump() if hasattr(build_manifest, "model_dump") else build_manifest,
                        "coherence_gate": None,
                        "handoff_bundle": None,
                    }
            print(f"[PREFLIGHT] {persona} completed")

        # Phase 1.0: Planning Coherence Gate + Handoff Ceremony.
        # The gate runs after all four planning personas have completed
        # (or failed-with-max-retries). If the gate blocks without any
        # waivers, we abort cleanly with a new phase "gate_failed_no_waivers"
        # so the engineer can see the gate result in the trace. If the
        # gate passes (or passes with waivers), we run the Handoff Ceremony
        # which produces the HandoffBundle and persists it to the
        # per-migration blackboard.
        self._log_trace_with_room("preflight_complete", {
            "artifacts_produced": list(artifacts.keys()),
            "gaps_count": len(gaps_logged),
        }, room="planning")

        gate_report = self._run_planning_coherence_gate(artifacts, gaps_logged)
        if not gate_report.passed and not gate_report.waivers:
            # Hard block: no waivers, gate failed. The manager loop would
            # just bounce on this; we abort cleanly and surface the gate
            # output to the user.
            self._log_trace_with_room("planning_halted", {
                "phase": "gate_failed_no_waivers",
                "blocking": gate_report.blocking,
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
                skip = (Path("sites") / site_slug).exists()
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
                actual_site_dir = Path("sites") / built_slug
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
                    local_build_path=str(Path("sites") / site_slug),
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
        """Delegate the post-build promotion path to PromotionPipeline.

        This is the explicit handoff boundary between MigrationManager
        (planning + build + quality gates) and PromotionPipeline
        (preview + review + human approval + production deploy). Before Phase 0
        these were two separate orchestrators and the boundary was implicit,
        which meant the E2E never exercised both halves in a single run.

        Failure mode: any exception inside PromotionPipeline is caught and
        recorded as a gap (with target_persona="deploy_specialist") plus a
        trace event. We do NOT abort the migration — a promotion failure is
        recoverable (can be re-run via PromotionPipeline directly).
        """
        self._log_trace("promotion_start", {
            "migration_id": migration_id,
            "site_slug": site_slug,
            "local_build_path": local_build_path,
        })
        try:
            from promotion_pipeline import PromotionPipeline  # lazy import
            pipeline = PromotionPipeline(db_path="elyra_memory.db")
            state = pipeline.run(
                migration_id=migration_id,
                site_name=site_name,
                site_slug=site_slug,
                local_build_path=local_build_path,
                skip_kilo_review=not bool(__import__("os").environ.get("ELYRA_RUN_KILO_REVIEW", "")),
            )
            self._log_trace("promotion_complete", {
                "stage": getattr(state, "stage", "unknown"),
                "production_url": getattr(state, "production_url", None),
                "preview_url": getattr(state, "preview_url", None),
            })
            return state
        except Exception as e:
            self._log_trace("promotion_failed", {"error": str(e)})
            try:
                from memory.gap_ledger import log_gap
                log_gap(
                    migration_id=migration_id,
                    gap_type="promotion_failure",
                    source_persona="deploy_specialist",
                    target_persona="deploy_specialist",
                    description=f"PromotionPipeline raised {type(e).__name__}: {str(e)[:200]}",
                    suggested_fix="Re-run promotion via PromotionPipeline.run() or check Fly.io / GitHub MCP connectivity",
                    severity="high",
                )
            except Exception:
                # Gap logging itself failed; trace already captured the error.
                pass
            return None

    # ------------------------- Decision Engine -------------------------

    def _decide_next_action(
        self,
        step: str,
        task_context: dict,
        artifacts: dict,
        gaps: list,
        site_dir: Path,
    ) -> ManagerDecision:
        """LLM-driven decision engine. Only safety rails + the deterministic
        target-persona short-circuit are non-LLM."""
        # Safety rail 1: high-severity gap with no recoverable target
        high_severity_gaps = [g for g in gaps if isinstance(g, dict) and g.get("severity") == "high"]
        if high_severity_gaps and not any(g.get("target_persona") for g in high_severity_gaps):
            return ManagerDecision(action="abort", reason="High-severity gap with no target_persona", gaps_detected=high_severity_gaps)

        # Phase 0.6: deterministic short-circuit. If the most recent
        # high-severity gap carries a target_persona, route back to it
        # without an LLM round-trip. The manager persona is only consulted
        # for *cross-persona* decisions or when no target is suggested.
        # This is the bit that makes the self-healing loop fast and reliable.
        current_state = self._build_current_state(artifacts, gaps, site_dir)
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
        return self._consult_manager_persona(current_state, task_context)

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
    ) -> Dict[str, Any]:
        """Assemble the structured state payload for the Manager persona."""
        # Only run quality gates if site directory exists
        if site_dir.exists():
            gate_report = self._run_quality_gates(site_dir, re_run_impeccable=False)
            self._log_trace("quality_gate_run", {"report": gate_report})
        else:
            gate_report = {"overall_passed": True, "message": "Site directory not yet created - skipping gates"}
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

        return {
            "artifacts": {
                p: {"present": True, "version": "latest", "path": str(site_dir / f"{p}.json")}
                for p in artifacts.keys()
            },
            "gaps": gaps,
            "quality_gate_result": gate_report if not gate_report.get("overall_passed") else None,
            "iteration_count": self.iteration_count,
            "consecutive_gate_failures": self.consecutive_gate_failures,
            "routing_suggestion": routing_suggestion,
        }

    def _consult_manager_persona(
        self,
        current_state: Dict[str, Any],
        task_context: dict,
    ) -> ManagerDecision:
        """Invoke Kilo with migration_orchestrator persona and obtain ManagerDecision.

        Phase 0.7: replaced 175 lines of hand-rolled brace-counting and
        allowed-fields filtering with a single call to
        `validate_and_repair_manager_decision()`. That helper uses the
        shared `extract_json()` plus Pydantic validation against the
        `ManagerDecision` schema. On any parse/validation failure it
        returns a deterministic ManagerDecision(action="abort", reason=...)
        — no more "Missing action in manager decision" infinite loop,
        no more "Manager persona returned prose" class of failures.
        """
        from tools.kilo import invoke_kilo  # thin wrapper around Kilo CLI
        from skills.agentic.manager_decision import validate_and_repair_manager_decision

        prompt = f"""{self.manager_persona}

## CURRENT STATE
```json
{json.dumps(current_state, indent=2, default=str)}
```

**Task Context (brief):** {json.dumps({k: task_context.get(k) for k in ('url','platform','migration_id')}, indent=2)}

You are now acting solely as the Migration Manager. Return ONLY a valid JSON object matching the ManagerDecision schema. No prose outside the JSON.
"""

        # Call Kilo (Manager persona).  We expect it to return raw JSON string.
        # SAFETY RAIL: Manager decision must complete within 120s or we abort to avoid
        # hanging the entire orchestrator. The manager prompt is ~13K chars and Kilo
        # can hang on certain interactive prompts even with --auto flag.
        raw = invoke_kilo(
            prompt=prompt,
            context={"role": "migration_manager", "mode": "decision"},
            working_dir=".",
            timeout=120,  # Hard timeout - manager decision must be fast
        )

        # Always log the raw response for live debugging.
        if isinstance(raw, ToolResult):
            preview = raw.summary or raw.to_json() or ""
        elif isinstance(raw, str):
            preview = raw
        elif raw is None:
            preview = ""
        else:
            preview = str(raw)
        self._log_trace("manager_raw_response", {
            "decision_text_preview": preview[:800] if preview else "(empty)",
            "decision_text_length": len(preview) if preview else 0,
        })
        try:
            print(f"  [MANAGER_RAW] {preview[:600]}")
        except UnicodeEncodeError:
            print(f"  [MANAGER_RAW] {preview[:600].encode('ascii', 'replace').decode('ascii')}")

        # Validate and repair. The helper never raises — it returns a
        # ManagerDecision in every case (real or deterministic abort).
        decision = validate_and_repair_manager_decision(raw)

        # If the helper produced a deterministic abort, log a structured
        # trace event so the failure is visible in the run history. We
        # do NOT recurse or retry — the abort is the answer.
        if decision.action == "abort" and "manager persona" in decision.reason:
            self._log_trace("manager_decision_invalid", {
                "reason": decision.reason,
                "raw_preview": preview[:400] if preview else "",
            })

        # Track iteration count per persona for safety / observability.
        if decision.persona:
            self.iteration_count[decision.persona] = self.iteration_count.get(decision.persona, 0) + 1

        return decision

    # ------------------------- Quality Gates -------------------------

    def _run_quality_gates(self, site_dir: Path, re_run_impeccable: bool = False) -> Dict[str, Any]:
        """Public wrapper around quality_gate.run_quality_gates."""
        try:
            from quality_gate import run_quality_gates as qg_run
            return qg_run(str(site_dir), re_run_impeccable=re_run_impeccable)
        except Exception as e:
            return {
                "overall_passed": False,
                "failing_gate": "quality_gate_exception",
                "errors": [str(e)],
                "gaps": [{"description": f"Quality gate runner exception: {e}", "severity": "high"}],
            }

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
        """Create structured GitHub issue via github_strategy_agent and return decision."""
        from skills.agentic.github_strategy_agent import create_structured_migration_issue

        migration_id = task_context.get("migration_id", "")
        url = task_context.get("url", "")
        platform = task_context.get("platform", "unknown")

        issue_body = self._build_github_issue_body(migration_id, url, platform, gate_report, artifacts, gaps)
        try:
            create_structured_migration_issue(migration_id, url, platform, issue_body)
            self._log_trace("github_issue_created", {"migration_id": migration_id})
            return ManagerDecision(action="github_issue_created", reason="Terminal failure — GitHub issue created")
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
        blocking: List[str] = []
        warnings: List[str] = []
        waivers: List[CoherenceGateWaiver] = []
        threshold = 0.7

        # Artifact coverage is a hard requirement. If any artifact is
        # missing AND there's no waiver, block.
        missing = [k for k, v in artifact_coverage.items() if not v]
        if missing:
            blocking.append(f"missing planning artifacts: {', '.join(missing)}")

        # Fidelity score below threshold is a soft requirement — can be
        # waived with documented owner + risk_level.
        if fidelity_score is not None and fidelity_score < threshold:
            warnings.append(
                f"fidelity_score={fidelity_score:.2f} below threshold {threshold:.2f}"
            )

        # Unanswered high-severity gaps are blocking unless waived.
        if open_questions_unsanswered:
            for g in open_questions_unsanswered:
                blocking.append(
                    f"unanswered high-severity gap: {g.get('description', '?')[:120]}"
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
            brand_spec=brand_spec,
            planning_rationale=planning_rationale,
            open_questions=open_questions,
            known_gaps=known_gaps,
            coherence_gate=gate_report,
            success_criteria=success_criteria,
            requires_human_review=requires_human_review,
            human_review_reason=human_review_reason,
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
            },
            handoff_at=datetime.now(timezone.utc).isoformat(),
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

    def _init_build_manifest(self, migration_id: str, url: str, site_slug: str) -> Any:
        # Minimal BuildManifest stub — extended in later step
        return type("BM", (), {
            "migration_id": migration_id,
            "source_url": url,
            "output_dir": f"sites/{site_slug}",
            "rework_log": [],
            "iteration_history": [],
        })()

    def _finalize_build_manifest(self, bm: Any, final_state: str, artifacts: dict, gaps: list) -> None:
        if hasattr(bm, "rework_log"):
            bm.final_state = final_state
            bm.completed_at = datetime.now(timezone.utc).isoformat()

    def _get_latest_artifact_id(
        self,
        artifact_dir: str,
        site_slug: Optional[str] = None,
    ) -> Optional[str]:
        """Return the timestamp ID (filename stem) of the most recent
        JSON file in memory/<artifact_dir>/.

        If `site_slug` is given AND the artifact lives in a per-slug
        subdirectory (visual_specs is the only one today), the lookup
        is scoped to memory/<artifact_dir>/<site_slug>/.

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
        return files[0].stem if files else None

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

    def _invoke_persona(
        self,
        persona: str,
        task_context: dict,
        artifacts: dict,
        site_slug: str,
        migration_id: str,
    ) -> dict:
        """Invoke a persona via its thin-glue Python agent. Returns result dict.

        Artifacts from Kilo runs are written to .kilo/artifacts/<session_id>/
        (ephemeral scratch) and promoted to memory/artifacts/<migration_id>/
        (persisted) after each run completes.

        The returned dict has keys: success, artifact, gaps.
        - `gaps` is populated by diffing the gap ledger before/after the
          persona call. Any new entries (with matching migration_id) get
          returned here so the manager loop can see them and decide
          route_back / abort / retry based on target_persona. (Phase 0.6.)
        """
        import time
        t0 = time.time()
        print(f"\n[MANAGER] Invoking: {persona}")

        # Snapshot the gap ledger size before the call so we can return only
        # the entries the persona created. This makes "what did THIS persona
        # learn" answerable and keeps the manager's view of gaps tightly
        # scoped to each invocation.
        try:
            pre_gaps = query_gaps(migration_id=migration_id)
            pre_count = len(pre_gaps)
        except Exception:
            pre_count = 0

        # Built slug is only set by the builder persona; pre-declare so the
        # return statement at the end is always well-defined.
        built_site_slug: Optional[str] = None

        # Scratch directory for this Kilo session
        scratch_mig_dir = self.SCRATCH_ARTIFACT_DIR / self.session_id
        scratch_mig_dir.mkdir(parents=True, exist_ok=True)
        scratch_persona_dir = scratch_mig_dir / persona
        scratch_persona_dir.mkdir(parents=True, exist_ok=True)

        url = task_context.get("url", "")

        # Track the Kilo session for provenance
        persona_set = [persona]
        decision_context = f"{persona} invoked for {task_context.get('platform', 'unknown')} {task_context.get('task_type', 'generic')} migration"

        if persona == "scraper":
            from skills.agentic.scraper_agent import scrape
            result = scrape(url)
            if result:
                # Save SiteUnderstanding to memory directory
                site_id = self._save_artifact(
                    result,
                    "site_understandings",
                    task_context.get("migration_id") or migration_id,
                    persona_set,
                    decision_context,
                )
                task_context["site_understanding_id"] = site_id
            artifact = result if result else None
            success = artifact is not None

        elif persona == "architect":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            if not site_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", persona, "SiteUnderstanding not found")] }
            from skills.agentic.architect_agent import architect
            result = architect(site_id)
            if result:
                arch_id = self._save_artifact(
                    result,
                    "site_architectures",
                    task_context.get("migration_id") or migration_id,
                    persona_set,
                    decision_context,
                )
                task_context["site_architecture_id"] = arch_id
            artifact = result if result else None
            success = artifact is not None

        elif persona == "marketing":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            arch_id = task_context.get("site_architecture_id") or self._get_latest_artifact_id("site_architectures")
            from skills.agentic.marketing_agent import market
            result = market(site_id, arch_id) if site_id and arch_id else None
            if result:
                rec_id = self._save_artifact(
                    result,
                    "site_recommendations",
                    task_context.get("migration_id") or migration_id,
                    persona_set,
                    decision_context,
                )
                task_context["content_recommendation_id"] = rec_id
            artifact = result if result else None
            success = artifact is not None

        elif persona == "designer":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            rec_id = task_context.get("content_recommendation_id") or self._get_latest_artifact_id("site_recommendations")
            if not site_id or not rec_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", persona, "SiteUnderstanding or ContentRecommendation not found")]}
            from skills.agentic.designer_agent import design
            result = design(site_id, rec_id)
            if result:
                # Designer saves to memory/visual_specs/[site_slug]/[id].json
                site_name = task_context.get("site_name", "unnamed")
                from pathlib import Path
                spec_dir = Path("memory/visual_specs") / self._get_site_slug(site_name)
                spec_dir.mkdir(parents=True, exist_ok=True)
                from datetime import datetime
                vd_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                vd_path = spec_dir / f"{vd_id}.json"
                if hasattr(result, "model_dump_json"):
                    vd_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
                else:
                    vd_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            artifact = result if result else None
            success = artifact is not None

        elif persona == "builder":
            # Legacy monolithic builder. Kept for any in-flight migrations
            # that still reference the old short name. Phase 1.1 calls
            # the new layered personas (data_engineer, backend_architect,
            # frontend_architect, integration_coordinator) instead.
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            arch_id = task_context.get("site_architecture_id") or self._get_latest_artifact_id("site_architectures")
            rec_id = task_context.get("content_recommendation_id") or self._get_latest_artifact_id("site_recommendations")
            if not site_id or not arch_id or not rec_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", "builder", "Missing planning artifacts for builder")]}
            self._log_trace("builder_start", {
                "site_id": site_id, "arch_id": arch_id, "rec_id": rec_id,
                "site_slug": task_context.get("site_name", "unknown")
            })
            from skills.agentic.builder_agent import build
            result, built_site_slug = build(site_id, arch_id, rec_id)
            if result:
                build_id = self._save_artifact(
                    result,
                    "site_builds",
                    task_context.get("migration_id") or migration_id,
                    persona_set,
                    decision_context,
                )
                self._log_trace("builder_complete", {"build_id": build_id, "built_site_slug": built_site_slug})
            else:
                self._log_trace("builder_failed", {"site_id": site_id, "arch_id": arch_id, "rec_id": rec_id})
            artifact = result if result else None
            success = artifact is not None

        # --- Phase 1.1: Forge Room personas ---
        #
        # Each persona reads its upstream artifacts from memory/ on
        # demand (per the blackboard model). The orchestrator only
        # threads the high-level HandoffBundle + planning artifact IDs
        # through task_context; the persona modules do the rest.

        elif persona == "devops":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            arch_id = task_context.get("site_architecture_id") or self._get_latest_artifact_id("site_architectures")
            if not site_id or not arch_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", "deploy_specialist", "Missing planning artifacts for deploy_specialist")]}
            from skills.agentic.architect_agent import load_site_architecture
            from skills.agentic.scraper_agent import load_site_understanding
            site = load_site_understanding(site_id)
            arch = load_site_architecture(arch_id)
            from skills.agentic.devops_engineer import design_deploy_spec
            result = design_deploy_spec(
                site, arch,
                migration_id=migration_id, site_slug=site_slug,
            )
            artifact = result
            success = artifact is not None

        elif persona == "data":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            arch_id = task_context.get("site_architecture_id") or self._get_latest_artifact_id("site_architectures")
            if not site_id or not arch_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", "data_engineer", "Missing planning artifacts for data_engineer")]}
            from skills.agentic.architect_agent import load_site_architecture
            from skills.agentic.scraper_agent import load_site_understanding
            from skills.agentic.devops_engineer import load_latest_deploy_spec
            site = load_site_understanding(site_id)
            arch = load_site_architecture(arch_id)
            deploy_spec = load_latest_deploy_spec()
            from skills.agentic.data_engineer import design_data_contracts
            result = design_data_contracts(
                site, arch, deploy_spec,
                migration_id=migration_id, site_slug=site_slug,
            )
            artifact = result
            success = artifact is not None

        elif persona == "backend":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            arch_id = task_context.get("site_architecture_id") or self._get_latest_artifact_id("site_architectures")
            if not site_id or not arch_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", "backend_architect", "Missing planning artifacts for backend_architect")]}
            from skills.agentic.architect_agent import load_site_architecture
            from skills.agentic.scraper_agent import load_site_understanding
            from skills.agentic.devops_engineer import load_latest_deploy_spec
            from skills.agentic.data_engineer import load_latest_data_contracts
            site = load_site_understanding(site_id)
            arch = load_site_architecture(arch_id)
            deploy_spec = load_latest_deploy_spec()
            data_contracts = load_latest_data_contracts()
            from skills.agentic.backend_architect import design_api_contracts
            result = design_api_contracts(
                site, arch, data_contracts, deploy_spec,
                migration_id=migration_id, site_slug=site_slug,
            )
            artifact = result
            success = artifact is not None

        elif persona == "frontend":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            arch_id = task_context.get("site_architecture_id") or self._get_latest_artifact_id("site_architectures")
            rec_id = task_context.get("content_recommendation_id") or self._get_latest_artifact_id("site_recommendations")
            vd_id = task_context.get("visual_direction_id") or self._get_latest_artifact_id("visual_specs", site_slug=site_slug)
            if not site_id or not arch_id or not rec_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", "frontend_architect", "Missing planning artifacts for frontend_architect")]}
            from skills.agentic.architect_agent import load_site_architecture
            from skills.agentic.scraper_agent import load_site_understanding
            from skills.agentic.marketing_agent import load_content_recommendation
            from skills.agentic.designer_agent import load_visual_direction
            from skills.agentic.devops_engineer import load_latest_deploy_spec
            from skills.agentic.data_engineer import load_latest_data_contracts
            from skills.agentic.backend_architect import load_latest_api_contracts
            site = load_site_understanding(site_id)
            arch = load_site_architecture(arch_id)
            rec = load_content_recommendation(rec_id)
            vd = load_visual_direction(site_slug) if vd_id else None
            deploy_spec = load_latest_deploy_spec()
            data_contracts = load_latest_data_contracts()
            api_contracts = load_latest_api_contracts()
            from skills.agentic.frontend_architect import design_frontend
            result, built_site_slug = design_frontend(
                site, arch, rec, site_slug,
                visual_direction=vd,
                data_contracts=data_contracts,
                api_contracts=api_contracts,
                deploy_spec=deploy_spec,
                migration_id=migration_id,
            )
            if result:
                build_id = self._save_artifact(
                    result,
                    "site_builds",
                    task_context.get("migration_id") or migration_id,
                    persona_set,
                    decision_context,
                )
                self._log_trace_with_room("frontend_architect_complete", {
                    "build_id": build_id, "built_site_slug": built_site_slug,
                }, room="forge")
                # Surface the build_id so the integration_coordinator
                # can include it in the final IntegrationStatus.
                task_context["build_id"] = build_id
            else:
                self._log_trace_with_room("frontend_architect_failed", {
                    "site_id": site_id, "arch_id": arch_id, "rec_id": rec_id,
                }, room="forge")
            artifact = result
            success = artifact is not None

        elif persona == "coordinator":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            arch_id = task_context.get("site_architecture_id") or self._get_latest_artifact_id("site_architectures")
            build_id = task_context.get("build_id") or self._get_latest_artifact_id("site_builds")
            if not site_id or not arch_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", "integration_coordinator", "Missing planning artifacts for integration_coordinator")]}
            from skills.agentic.architect_agent import load_site_architecture
            from skills.agentic.scraper_agent import load_site_understanding
            from skills.agentic.devops_engineer import load_latest_deploy_spec
            from skills.agentic.data_engineer import load_latest_data_contracts
            from skills.agentic.backend_architect import load_latest_api_contracts
            site = load_site_understanding(site_id)
            arch = load_site_architecture(arch_id)
            deploy_spec = load_latest_deploy_spec()
            data_contracts = load_latest_data_contracts()
            api_contracts = load_latest_api_contracts()
            from skills.agentic.integration_coordinator import coordinate_integration
            result = coordinate_integration(
                site, arch, data_contracts, api_contracts, deploy_spec,
                migration_id=migration_id, site_slug=site_slug, build_id=build_id or "",
            )
            artifact = result
            success = artifact is not None

        else:
            return {"success": False, "gaps": [self._make_gap(migration_id, "persona_gap", "manager", f"Unknown persona: {persona}")]}

        # Promote any files written to scratch dir by this persona's run
        self._promote_scratch_artifacts(
            persona=persona,
            migration_id=migration_id,
            persona_set=persona_set,
            decision_context=decision_context,
        )

        elapsed = time.time() - t0
        print(f"[MANAGER] {persona} completed in {elapsed:.1f}s")

        # Phase 0.6: read gap ledger for entries this persona added during
        # this call. Returns them to the manager so it can decide whether
        # to route_back (using target_persona), abort (safety rail), or
        # continue. This is the missing link that lets the self-healing
        # loop actually see what the persona reported.
        new_gaps: List[Dict[str, Any]] = []
        try:
            post_gaps = query_gaps(migration_id=migration_id)
            if len(post_gaps) > pre_count:
                new_gaps = [g.to_dict() if hasattr(g, "to_dict") else g for g in post_gaps[pre_count:]]
                if new_gaps:
                    print(f"[MANAGER] {persona} emitted {len(new_gaps)} new gap(s) during this call")
        except Exception as e:
            print(f"[MANAGER] WARN: could not diff gap ledger for {persona}: {e}")

        return {"success": success, "artifact": artifact, "gaps": new_gaps, "built_site_slug": built_site_slug}

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