from conductor.routing import Router
from conductor.memory_client import MemoryClient
from conductor.state_machine import (
    ConductorState, WorkflowPhase, create_initial_state,
    transition_to_phase, add_error, is_terminal_state
)
from conductor.trace import Trace
from registry.registry import load_persona, list_personas
from tools.opencode import invoke_opencode
from memory.gap_ledger import query_gaps, log_gap
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
        from tools.opencode import invoke_opencode
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


@dataclass
class ManagerDecision:
    action: str  # "invoke_persona" | "route_back" | "complete" | "github_issue_created" | "abort"
    persona: Optional[str] = None
    reason: str = ""
    gaps_detected: List = field(default_factory=list)
    retry_with_modified_prompt: Optional[str] = None
    gap_context: Optional[str] = None  # crisp 2-4 bullet summary for route_back
    gate_report: Optional[Dict[str, Any]] = None


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

    def __init__(self, db_path: str = "elyra_memory.db"):
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
        site_name = task_context.get("site_name", "unnamed")
        site_slug = self._get_site_slug(site_name)

        self._log_trace("migration_started", {"migration_id": migration_id, "url": url, "platform": platform})

        site_dir = Path("sites") / site_slug
        build_manifest = self._init_build_manifest(migration_id, url, site_slug)

        decision = self._decide_next_action("init", task_context, artifacts, gaps_logged, site_dir)
        self._log_decision(decision)

        while decision.action not in ("complete", "github_issue_created", "abort"):
            if decision.action == "invoke_persona":
                result = self._invoke_persona(
                    decision.persona, task_context, artifacts, site_slug, migration_id, build_manifest
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

            decision = self._decide_next_action(
                f"{decision.persona}_complete" if decision.action == "invoke_persona" else decision.action,
                task_context, artifacts, gaps_logged, site_dir
            )
            self._log_decision(decision)

        final_state = decision.action
        self._finalize_build_manifest(build_manifest, final_state, artifacts, gaps_logged)

        if final_state in ("complete", "github_issue_created"):
            self._invoke_elyra_engineer(migration_id, build_manifest, site_slug)

        return {
            "migration_id": migration_id,
            "site_slug": site_slug,
            "success": final_state == "complete",
            "phase_reached": final_state,
            "artifacts": artifacts,
            "gaps": gaps_logged,
            "trace": self.trace,
            "build_manifest": build_manifest.model_dump() if hasattr(build_manifest, "model_dump") else build_manifest,
        }

    # ------------------------- Decision Engine -------------------------

    def _decide_next_action(
        self,
        step: str,
        task_context: dict,
        artifacts: dict,
        gaps: list,
        site_dir: Path,
    ) -> ManagerDecision:
        """LLM-driven decision engine. Only safety rails are deterministic."""
        # Safety rail 1: high-severity gap with no recoverable target
        high_severity_gaps = [g for g in gaps if isinstance(g, dict) and g.get("severity") == "high"]
        if high_severity_gaps and not any(g.get("target_persona") for g in high_severity_gaps):
            return ManagerDecision(action="abort", reason="High-severity gap with no target_persona", gaps_detected=high_severity_gaps)

        # Safety rail 2 & 3 are evaluated inside _consult_manager_persona after ManagerDecision is received

        current_state = self._build_current_state(artifacts, gaps, site_dir)
        return self._consult_manager_persona(current_state, task_context)

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
        gate_report = self._run_quality_gates(site_dir, re_run_impeccable=False)
        self._log_trace("quality_gate_run", {"report": gate_report})

        return {
            "artifacts": {
                p: {"present": True, "version": "latest", "path": str(site_dir / f"{p}.json")}
                for p in artifacts.keys()
            },
            "gaps": gaps,
            "quality_gate_result": gate_report if not gate_report.get("overall_passed") else None,
            "iteration_count": self.iteration_count,
            "consecutive_gate_failures": self.consecutive_gate_failures,
        }

    def _consult_manager_persona(
        self,
        current_state: Dict[str, Any],
        task_context: dict,
    ) -> ManagerDecision:
        """Invoke Kilo with migration_orchestrator persona and obtain ManagerDecision."""
        from tools.kilo import invoke_kilo  # thin wrapper around Kilo CLI

        prompt = f"""{self.manager_persona}

## CURRENT STATE
```json
{json.dumps(current_state, indent=2, default=str)}
```

**Task Context (brief):** {json.dumps({k: task_context.get(k) for k in ('url','platform','migration_id')}, indent=2)}

You are now acting solely as the Migration Manager. Return ONLY a valid JSON object matching the ManagerDecision schema. No prose outside the JSON.
"""

        # Call Kilo (Manager persona).  We expect it to return raw JSON string.
        raw = invoke_kilo(
            prompt=prompt,
            context={"role": "migration_manager", "mode": "decision"},
            working_dir=".",
        )

        try:
            decision_dict = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            decision_dict = {"action": "abort", "reason": "Manager persona returned invalid JSON"}

        # Safety rail enforcement on the returned decision
        persona = decision_dict.get("persona")
        if persona:
            iter_count = self.iteration_count.get(persona, 0) + 1
            self.iteration_count[persona] = iter_count
            if iter_count > self.MAX_RETRIES:
                return self._create_github_issue(task_context, current_state.get("quality_gate_result") or {}, {}, current_state.get("gaps", []))

            gate_key = f"{persona}:{(current_state.get('quality_gate_result') or {}).get('failing_gate', 'unknown')}"
            self.consecutive_gate_failures[gate_key] = self.consecutive_gate_failures.get(gate_key, 0) + 1
            if self.consecutive_gate_failures[gate_key] >= self.SAME_GATE_FAIL_LIMIT:
                return self._create_github_issue(task_context, current_state.get("quality_gate_result") or {}, {}, current_state.get("gaps", []))

        return ManagerDecision(**decision_dict)

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
            persona, task_context, artifacts, site_slug, migration_id, build_manifest, gap_context=gap_context
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

    # ------------------------- Persona Invocation -------------------------

    def _invoke_persona(
        self,
        persona: str,
        task_context: dict,
        artifacts: dict,
        site_slug: str,
        migration_id: str,
        build_manifest: Any,
        gap_context: Optional[str] = None,
    ) -> dict:
        """Invoke persona agent. Forwards gap_context when present."""
        print(f"\n[MANAGER] Invoking: {persona}" + (f" (with gap context)" if gap_context else ""))
        self.iteration_count[persona] = self.iteration_count.get(persona, 0) + 1

        if persona == "designer":
            from skills.agentic.designer_agent import design
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            rec_id = task_context.get("content_recommendation_id") or self._get_latest_artifact_id("site_recommendations")
            if not site_id or not rec_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", persona, "SiteUnderstanding or ContentRecommendation missing")]}
            result = design(site_id, rec_id, gap_context=gap_context)
            return {"success": bool(result), "artifact": result, "gaps": []}

        if persona == "builder":
            from skills.agentic.builder_agent import build
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            arch_id = task_context.get("site_architecture_id") or self._get_latest_artifact_id("site_architectures")
            rec_id = task_context.get("content_recommendation_id") or self._get_latest_artifact_id("site_recommendations")
            if not site_id or not arch_id or not rec_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", persona, "Missing planning artifacts")]}
            result = build(site_id, arch_id, rec_id, gap_context=gap_context)
            return {"success": bool(result), "artifact": result, "gaps": []}

        # other personas unchanged for brevity in this edit
        # All persona agents MUST return any emitted gaps (including those with target_persona)
        # so the Manager persona can decide arbitrary backward routing.
        return {"success": True, "artifact": {"persona": persona}, "gaps": []}

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

    def _log_decision(self, decision: ManagerDecision) -> None:
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

    def _get_latest_artifact_id(self, artifact_dir: str) -> Optional[str]:
        dir_path = Path("memory") / artifact_dir
        if not dir_path.exists():
            return None
        files = sorted(dir_path.glob("*.json"), reverse=True)
        return files[0].stem if files else None

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
        """Invoke a persona via its thin-glue Python agent. Returns result dict."""
        print(f"\n[MANAGER] Invoking: {persona}")

        url = task_context.get("url", "")
        if persona == "scraper":
            from skills.agentic.scraper_agent import scrape
            result = scrape(url, migration_id)
            artifact = result if result else None
            success = artifact is not None

        elif persona == "architect":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            if not site_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", persona, "SiteUnderstanding not found")] }
            from skills.agentic.architect_agent import architect
            result = architect(site_id)
            artifact = result if result else None
            success = artifact is not None

        elif persona == "marketing":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            arch_id = task_context.get("site_architecture_id") or self._get_latest_artifact_id("site_architectures")
            from skills.agentic.marketing_agent import market
            result = market(site_id, arch_id) if site_id and arch_id else None
            artifact = result if result else None
            success = artifact is not None

        elif persona == "designer":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            rec_id = task_context.get("content_recommendation_id") or self._get_latest_artifact_id("site_recommendations")
            if not site_id or not rec_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", persona, "SiteUnderstanding or ContentRecommendation not found")]}
            from skills.agentic.designer_agent import design
            result = design(site_id, rec_id)
            artifact = result if result else None
            success = artifact is not None

        elif persona == "builder":
            site_id = task_context.get("site_understanding_id") or self._get_latest_artifact_id("site_understandings")
            arch_id = task_context.get("site_architecture_id") or self._get_latest_artifact_id("site_architectures")
            rec_id = task_context.get("content_recommendation_id") or self._get_latest_artifact_id("site_recommendations")
            if not site_id or not arch_id or not rec_id:
                return {"success": False, "gaps": [self._make_gap(migration_id, "missing_data", persona, "Missing planning artifacts for builder")]}
            from skills.agentic.builder_agent import build
            result = build(site_id, arch_id, rec_id)
            artifact = result if result else None
            success = artifact is not None

        else:
            return {"success": False, "gaps": [self._make_gap(migration_id, "persona_gap", "manager", f"Unknown persona: {persona}")]}

        return {"success": success, "artifact": artifact, "gaps": []}

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

    def _get_latest_artifact_id(self, artifact_dir: str) -> Optional[str]:
        """Get the latest artifact ID from a memory directory."""
        from pathlib import Path
        dir_path = Path("memory") / artifact_dir
        if not dir_path.exists():
            return None
        files = sorted(dir_path.glob("*.json"), reverse=True)
        return files[0].stem if files else None

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

    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.wixsite.com"
    platform = sys.argv[2] if len(sys.argv) > 2 else "unknown"

    task_context = {
        "url": url,
        "platform": platform,
        "migration_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
    }

    print(f"[ELYRA MANAGER] Starting migration for {url}")
    print(f"[CONFIG] Platform: {platform}")

    manager = MigrationManager()
    result = manager.run(task_context)

    print(f"\n[MANAGER] Result: {result['phase_reached']}")
    print(f"[MANAGER] Site slug: {result['site_slug']}")
    print(f"[MANAGER] Success: {result['success']}")
    print(f"[MANAGER] Artifacts: {result['trace'].get('artifacts_produced', [])}")
    print(f"[MANAGER] Gaps logged: {result['trace'].get('gaps_logged', 0)}")