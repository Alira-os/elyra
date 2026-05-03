import json
import subprocess
import os


def run_npm_audit(project_dir: str) -> dict:
    """
    Run npm audit on a project directory.

    Args:
        project_dir: Path to the project root (must have package.json)

    Returns:
        {
            "critical": int,
            "high": int,
            "medium": int,
            "low": int,
            "passed": bool,
            "summary": str,
            "blocking": bool,
            "details": list of vulnerability objects
        }
    """
    package_json = os.path.join(project_dir, "package.json")
    if not os.path.exists(package_json):
        return {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "passed": False,
            "summary": f"package.json not found in {project_dir}",
            "blocking": True,
            "details": [],
            "error": "package.json not found"
        }

    try:
        result = subprocess.run(
            ["npm", "audit", "--audit-level=high", "--json"],
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=120
        )
        output = result.stdout
    except FileNotFoundError:
        return {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "passed": False,
            "summary": "npm not found in PATH",
            "blocking": False,
            "details": [],
            "error": "npm not installed"
        }
    except subprocess.TimeoutExpired:
        return {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "passed": False,
            "summary": "npm audit timed out",
            "blocking": False,
            "details": [],
            "error": "timeout"
        }

    try:
        audit_data = json.loads(output) if output.strip().startswith("{") else {}
    except json.JSONDecodeError:
        audit_data = {}

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}

    if "vulnerabilities" in audit_data:
        for vuln in audit_data["vulnerabilities"].values():
            sev = vuln.get("severity", "low").lower()
            if sev in counts:
                counts[sev] += 1

    total_vulns = sum(counts[k] for k in ["critical", "high", "medium", "low"])

    return {
        "critical": counts["critical"],
        "high": counts["high"],
        "medium": counts["medium"],
        "low": counts["low"],
        "passed": counts["critical"] == 0,
        "summary": f"{counts['critical']} critical, {counts['high']} high, {counts['medium']} medium, {counts['low']} low vulnerabilities found",
        "blocking": counts["critical"] > 0,
        "details": _extract_vulnerability_details(audit_data.get("vulnerabilities", {}))
    }


def _extract_vulnerability_details(vulnerabilities: dict) -> list[dict]:
    """Extract key info from vulnerability objects."""
    details = []
    for name, vuln in list(vulnerabilities.items())[:20]:
        details.append({
            "name": name,
            "severity": vuln.get("severity", "unknown"),
            "url": vuln.get("url", ""),
            "title": vuln.get("title", ""),
            "fixable": vuln.get("fixable", False)
        })
    return details


def get_fix_instructions(audit_result: dict) -> str:
    """Generate fix instructions from audit result."""
    if audit_result["passed"]:
        return "No vulnerabilities found. No action needed."

    instructions = []

    if audit_result["critical"] > 0:
        instructions.append(
            f"\n⚠️  {audit_result['critical']} CRITICAL vulnerabilities found. "
            "These must be fixed before deployment.\n"
        )
        instructions.append("Run the following to update vulnerable packages:\n")
        instructions.append("  npm update\n")
        instructions.append("  npm audit fix\n")
    else:
        instructions.append(
            f"\n✓ No critical vulnerabilities found ({audit_result['high']} high, "
            f"{audit_result['medium']} medium, {audit_result['low']} low warnings).\n"
        )
        instructions.append("You may proceed with deployment, but consider fixing high vulnerabilities:\n")
        instructions.append("  npm update\n")
        instructions.append("  npm audit fix\n")

    if audit_result["details"]:
        instructions.append("\nAffected packages:\n")
        for detail in audit_result["details"][:5]:
            instructions.append(f"  - {detail['name']} ({detail['severity']})\n")

    return "".join(instructions)


if __name__ == "__main__":
    import sys
    project_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    result = run_npm_audit(project_dir)
    print(json.dumps(result, indent=2))
    print("\n--- Fix Instructions ---")
    print(get_fix_instructions(result))