from typing import TypedDict, Annotated
from typing_extensions import TypedDict
from enum import Enum
import operator


class WorkflowPhase(str, Enum):
    ONBOARDING = "onboarding"
    ROUTING = "routing"
    SCRAPING = "scraping"
    CODEGEN = "codegen"
    SECURITY_GATE = "security_gate"
    DEPLOY = "deploy"
    APPROVAL = "approval"
    DEBATE = "debate"
    COMPLETE = "complete"
    ABORT = "abort"


class ConductorState(TypedDict):
    session_id: str
    current_phase: WorkflowPhase
    completed_steps: Annotated[list[str], operator.add]
    errors: Annotated[list[dict], operator.add]
    task_context: dict
    routing_sequence: list[str]
    routing_confidence: float
    stack_chosen: str
    scraped_content: dict | None
    codegen_output: dict | None
    security_gate_passed: bool | None
    security_gate_results: dict | None
    deploy_url: str | None
    approval_status: str | None
    fidelity_score: float | None
    trace: dict | None


def create_initial_state(session_id: str, task_context: dict) -> ConductorState:
    return ConductorState(
        session_id=session_id,
        current_phase=WorkflowPhase.ONBOARDING,
        completed_steps=[],
        errors=[],
        task_context=task_context,
        routing_sequence=[],
        routing_confidence=0.0,
        stack_chosen="nextjs+tailwind",
        scraped_content=None,
        codegen_output=None,
        security_gate_passed=None,
        security_gate_results=None,
        deploy_url=None,
        approval_status=None,
        fidelity_score=None,
        trace=None
    )


def transition_to_phase(state: ConductorState, phase: WorkflowPhase) -> ConductorState:
    state["current_phase"] = phase
    state["completed_steps"].append(phase.value)
    return state


def add_error(state: ConductorState, step: str, error: str, recoverable: bool = True) -> ConductorState:
    state["errors"].append({
        "step": step,
        "error": error,
        "recoverable": recoverable
    })
    return state


def is_terminal_state(state: ConductorState) -> bool:
    return state["current_phase"] in {
        WorkflowPhase.COMPLETE,
        WorkflowPhase.ABORT
    }


def is_retryable_error(state: ConductorState) -> bool:
    return all(e.get("recoverable", True) for e in state["errors"])


def get_state_summary(state: ConductorState) -> dict:
    return {
        "session_id": state["session_id"],
        "current_phase": state["current_phase"].value,
        "completed_steps": state["completed_steps"],
        "errors_count": len(state["errors"]),
        "routing_sequence": state["routing_sequence"],
        "security_gate_passed": state["security_gate_passed"],
        "deploy_url": state["deploy_url"],
        "fidelity_score": state["fidelity_score"]
    }


if __name__ == "__main__":
    state = create_initial_state(
        session_id="test-123",
        task_context={"url": "https://example.wixsite.com", "platform": "wix", "task_type": "portfolio"}
    )

    print("Initial state:")
    print(f"  Phase: {state['current_phase']}")
    print(f"  Completed: {state['completed_steps']}")
    print(f"  Errors: {state['errors']}")

    state = transition_to_phase(state, WorkflowPhase.ROUTING)
    print("\nAfter routing transition:")
    print(f"  Phase: {state['current_phase']}")
    print(f"  Completed: {state['completed_steps']}")