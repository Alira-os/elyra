from skills.executable.routing_heuristics import get_routing_sequence as get_heuristic_routing
from skills.executable.platform_detector import detect_platform
from typing import Optional


FAILURE_HANDLING = {
    "scraper_specialist": {"retry": 2, "fallback": "minimal_scrape"},
    "codegen_crew_lead": {"retry": 1, "fallback": "simplified_codegen"},
    "deploy_specialist": {"retry": 3, "fallback": "manual_deploy"},
    "security_auditor": {"retry": 0, "fallback": None},
    "onboarding_specialist": {"retry": 1, "fallback": "minimal_onboarding"},
    "stack_intelligence": {"retry": 0, "fallback": "default_stack"},
    "ui_polish": {"retry": 1, "fallback": "skip"},
    "seo_optimizer": {"retry": 1, "fallback": "skip"},
}


class Router:
    """
    Conductor routing logic.
    Handles heuristic routing + LLM override + backward routing on failure.
    """

    def __init__(self, llm_client: Optional[object] = None):
        self.llm_client = llm_client
        self.confidence_threshold = 0.7

    def route(self, task_context: dict) -> dict:
        """
        Determine routing sequence for a task.

        Args:
            task_context: TaskContext with platform, task_type, url, etc.

        Returns:
            {
                "routing_sequence": list of persona names,
                "confidence": 0.0 - 1.0,
                "requires_override": bool,
                "stack_chosen": str
            }
        """
        platform = task_context.get("platform", "generic")
        task_type = task_context.get("task_type", "generic")
        detection_confidence = task_context.get("platform_confidence", 1.0)

        heuristic_result = get_heuristic_routing(platform, task_type)

        routing_sequence = heuristic_result["routing_sequence"]
        confidence = heuristic_result["confidence"]
        requires_override = heuristic_result["requires_override"]

        if platform == "generic" and detection_confidence < 0.5:
            requires_override = True
            confidence = min(confidence, 0.4)

        if requires_override and confidence < self.confidence_threshold:
            routing_sequence, confidence = self._apply_llm_override(
                platform, task_type, routing_sequence, task_context
            )

        return {
            "routing_sequence": routing_sequence,
            "confidence": confidence,
            "requires_override": requires_override,
            "stack_chosen": heuristic_result.get("stack_chosen", "nextjs+tailwind"),
            "routing_used": routing_sequence
        }

    def _apply_llm_override(self, platform: str, task_type: str,
                           current_routing: list,
                           task_context: dict) -> tuple[list, float]:
        """
        Apply LLM override to routing sequence.

        Phase 0: No LLM override (returns current routing)
        Phase 1+: Will call LLM to modify routing
        """
        if not self.llm_client:
            return current_routing, 0.5

        return current_routing, 0.5

    def handle_persona_failure(self, persona: str, error: str,
                               task_context: dict) -> dict:
        """
        Handle persona failure with retry/fallback logic.

        Args:
            persona: Name of persona that failed
            error: Error message
            task_context: Current task context

        Returns:
            {
                "action": "retry" | "fallback" | "skip" | "abort",
                "fallback_persona": str or None,
                "modified_context": dict
            }
        """
        handling = FAILURE_HANDLING.get(persona, {"retry": 0, "fallback": None})

        retry_count = task_context.get("_retry_counts", {}).get(persona, 0)

        if retry_count < handling["retry"]:
            return {
                "action": "retry",
                "fallback_persona": None,
                "modified_context": {
                    **task_context,
                    "_retry_counts": {
                        **task_context.get("_retry_counts", {}),
                        persona: retry_count + 1
                    }
                }
            }

        fallback = handling["fallback"]
        if fallback == "skip":
            return {
                "action": "skip",
                "fallback_persona": None,
                "modified_context": task_context
            }
        elif fallback is None:
            return {
                "action": "abort",
                "fallback_persona": None,
                "modified_context": task_context
            }
        elif fallback == "minimal_scrape":
            return {
                "action": "fallback",
                "fallback_persona": "scraper_specialist",
                "modified_context": {**task_context, "_minimal_scrape": True}
            }
        elif fallback == "simplified_codegen":
            return {
                "action": "fallback",
                "fallback_persona": "codegen_crew_lead",
                "modified_context": {**task_context, "_simplified_codegen": True}
            }
        else:
            return {
                "action": "skip",
                "fallback_persona": None,
                "modified_context": task_context
            }

    def detect_platform_from_url(self, url: str, html: Optional[str] = None) -> dict:
        """
        Detect platform from URL and optional HTML.

        Args:
            url: Site URL
            html: Optional HTML content

        Returns:
            Platform detection result from platform_detector skill
        """
        return detect_platform(url, html)


if __name__ == "__main__":
    router = Router()

    print("Testing Router...")

    task_context = {
        "url": "https://example.wixsite.com",
        "platform": "wix",
        "task_type": "portfolio"
    }

    result = router.route(task_context)
    print(f"Routing: {result['routing_sequence']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Stack: {result['stack_chosen']}")

    print("\nTesting failure handling:")
    failure_result = router.handle_persona_failure(
        "scraper_specialist",
        "Connection timeout",
        task_context
    )
    print(f"Action: {failure_result['action']}")