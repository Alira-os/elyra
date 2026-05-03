from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Trace:
    """Clean bullet-pointed trace output for human review."""

    def __init__(self):
        self.steps: list[dict] = []
        self.started_at: datetime = datetime.now()

    def add(self, step: str, detail: str = "", status: str = "ok"):
        self.steps.append({
            "step": step,
            "detail": detail,
            "status": status,
            "timestamp": datetime.now().isoformat()
        })

    def add_routing(self, platform: str, task_type: str, sequence: list[str], confidence: float):
        self.add(
            step="Routing",
            detail=f"{platform} {task_type} -> [{', '.join(sequence)}] (conf={confidence:.2f})",
            status="ok"
        )

    def add_platform_detected(self, platform: str, confidence: float):
        self.add(
            step="Platform Detected",
            detail=f"{platform} (confidence: {confidence:.2f})",
            status="ok"
        )

    def add_stack_chosen(self, stack: str):
        self.add(
            step="Stack Chosen",
            detail=stack,
            status="ok"
        )

    def add_persona_invoked(self, persona: str):
        self.add(
            step=f"Executing",
            detail=persona,
            status="ok"
        )

    def add_security_gate(self, passed: bool, details: str = ""):
        self.add(
            step="Security Gate",
            detail=f"{'PASSED' if passed else 'FAILED'} {details}".strip(),
            status="ok" if passed else "error"
        )

    def add_deployed(self, url: str):
        self.add(
            step="Deployed",
            detail=f"to {url}",
            status="ok"
        )

    def add_error(self, step: str, error: str):
        self.add(
            step=step,
            detail=error,
            status="error"
        )

    def add_warning(self, step: str, warning: str):
        self.add(
            step=step,
            detail=warning,
            status="warning"
        )

    def summary(self) -> str:
        lines = []
        lines.append("=" * 50)
        lines.append("ELYRA MIGRATION TRACE")
        lines.append("=" * 50)

        for step in self.steps:
            icon = {
                "ok": "[OK]",
                "error": "[X]",
                "warning": "[!]",
                "pending": "[>]"
            }.get(step["status"], "[*]")

            line = f"{icon} {step['step']}"
            if step["detail"]:
                line += f": {step['detail']}"
            lines.append(line)

        lines.append("=" * 50)

        errors = [s for s in self.steps if s["status"] == "error"]
        warnings = [s for s in self.steps if s["status"] == "warning"]

        if not errors:
            lines.append("> Migration completed. Awaiting human approval.")
        else:
            lines.append(f"[X] Migration failed with {len(errors)} error(s).")

        lines.append("=" * 50)

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "steps": self.steps,
            "started_at": self.started_at.isoformat(),
            "duration_seconds": (datetime.now() - self.started_at).total_seconds()
        }


if __name__ == "__main__":
    trace = Trace()
    trace.add_routing("wix", "portfolio", ["onboarding", "scraper", "codegen", "deploy"], 0.94)
    trace.add_platform_detected("wix", 0.94)
    trace.add_stack_chosen("Next.js + Tailwind + Contentlayer")
    trace.add_persona_invoked("scraper_specialist")
    trace.add_persona_invoked("codegen_crew_lead")
    trace.add_security_gate(True, "(npm audit: 0 critical, lighthouse: 92)")
    trace.add_deployed("https://staging--michael-portfolio.netlify.app")

    print(trace.summary())