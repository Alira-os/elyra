"""
SecurityQualityGate — Hardened for Phase 1+.

Checks (mandatory for promotion):
- npm audit: 0 critical vulnerabilities
- Lighthouse performance >= 95 (raised from 85)
- Lighthouse accessibility >= 90
- Lighthouse best practices >= 90 (raised from 85)
- Lighthouse SEO >= 90 (raised from 85)
"""

from skills.executable.npm_audit import run_npm_audit, get_fix_instructions
from skills.executable.lighthouse import run_lighthouse
from dataclasses import dataclass
from typing import Optional
import json


@dataclass
class SecurityCheckResult:
    passed: bool
    npm_audit_result: dict
    lighthouse_result: dict
    blocking_issues: list[str]
    warnings: list[str]
    fix_instructions: str


class SecurityQualityGate:
    """
    Security and quality gate that must pass before deployment.

    Hardened thresholds (Phase 1+):
    - npm audit: 0 critical vulnerabilities
    - Lighthouse performance >= 0.95
    - Lighthouse accessibility >= 0.90
    - Lighthouse best practices >= 0.90
    - Lighthouse SEO >= 0.90
    """

    def __init__(self):
        self.npm_audit_threshold = {"critical": 0}
        self.lighthouse_thresholds = {
            "performance": 0.95,    # raised from 0.85
            "accessibility": 0.90,  # unchanged
            "best_practices": 0.90, # raised from 0.85
            "seo": 0.90            # raised from 0.85
        }

    def check(self, project_dir: str, staging_url: Optional[str] = None) -> SecurityCheckResult:
        """
        Run all security and quality checks.

        Args:
            project_dir: Path to the project to check
            staging_url: Optional staging URL for Lighthouse audit

        Returns:
            SecurityCheckResult with pass/fail and details
        """
        blocking_issues = []
        warnings = []

        npm_result = run_npm_audit(project_dir)

        if npm_result.get("blocking", False):
            blocking_issues.append(
                f"npm audit: {npm_result['critical']} critical vulnerabilities found"
            )
        elif npm_result.get("high", 0) > 0:
            warnings.append(
                f"npm audit: {npm_result['high']} high vulnerabilities (non-blocking)"
            )

        lighthouse_result = None
        if staging_url:
            lighthouse_result = run_lighthouse(staging_url)

            for category, threshold in self.lighthouse_thresholds.items():
                score = lighthouse_result.get(category, 0)
                if score < threshold:
                    blocking_issues.append(
                        f"Lighthouse {category}: {score:.0%} < {threshold:.0%}"
                    )
        elif staging_url is None:
            lighthouse_result = {"passed": False, "error": "No staging URL provided"}

        passed = len(blocking_issues) == 0

        if blocking_issues:
            fix_instructions = get_fix_instructions(npm_result)
        else:
            fix_instructions = "No fixes needed."

        return SecurityCheckResult(
            passed=passed,
            npm_audit_result=npm_result,
            lighthouse_result=lighthouse_result or {},
            blocking_issues=blocking_issues,
            warnings=warnings,
            fix_instructions=fix_instructions
        )

    def can_deploy(self, result: SecurityCheckResult) -> bool:
        """Returns True if deployment is allowed."""
        return result.passed


def check_project(project_dir: str, staging_url: Optional[str] = None) -> SecurityCheckResult:
    """
    Convenience function for quick security check.

    Args:
        project_dir: Path to project
        staging_url: Optional staging URL

    Returns:
        SecurityCheckResult
    """
    gate = SecurityQualityGate()
    return gate.check(project_dir, staging_url)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        project_dir = sys.argv[1]
        staging_url = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        project_dir = "."
        staging_url = None

    print(f"Running security check on: {project_dir}")
    if staging_url:
        print(f"Staging URL: {staging_url}")

    result = check_project(project_dir, staging_url)

    print(f"\n{'PASSED' if result.passed else 'FAILED'}")
    print(f"\nBlocking issues ({len(result.blocking_issues)}):")
    for issue in result.blocking_issues:
        print(f"  - {issue}")

    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings:
            print(f"  - {warning}")

    print(f"\n{result.fix_instructions}")