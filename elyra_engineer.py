"""
elyra_engineer.py — Elyra Engineer Agent (Kilo CLI as execution engine)

Architecture:
- Python: thin glue — loads Gap Ledger + BuildManifest artifacts, builds prompt,
          calls kilo run, produces Elyra Engineer Report
- Kilo CLI: handles all LLM reasoning (analysis, pattern detection, PR drafting)
- GitHub MCP: creates PR for persona charter changes
- No LangGraph, no LangChain, no custom agent loops

Kilo CLI handles:
  - Loading the persona (embedded in prompt)
  - LLM analysis over Gap Ledger + BuildManifest patterns
  - Producing Elyra Engineer Report JSON
  - Drafting GitHub PR for persona improvements

Usage:
    from elyra_engineer import analyze
    report = analyze("20260520_132936")
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from memory.gap_ledger import export_for_elyra_engineer, query_gaps, get_aggregate_stats
from github_official_push_files import push_files
from github_official_create_pull_request import create_pull_request

MEMORY_DIR = Path("memory/site_understandings")
ARCHITECTURE_DIR = Path("memory/site_architectures")
RECOMMENDATION_DIR = Path("memory/site_recommendations")
BUILD_DIR = Path("memory/site_builds")
GAP_LEDGER_FILE = Path("memory/gap_ledger/gaps.jsonl")
PERSONA_DIR = Path("registry/personas")
PERSONA_PATH = Path("registry/personas/elyra_engineer.md")
REPORT_DIR = Path("memory/elyra_engineer_reports")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

GITHUB_OWNER = "Alira-os"
GITHUB_REPO = "elyra"
GITHUB_BRANCH = "main"


def load_build_manifests(migration_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load all BuildManifest files from memory."""
    manifests = []
    if not BUILD_DIR.exists():
        return manifests

    for file in BUILD_DIR.glob("*.json"):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            if migration_id is None or data.get("migration_id") == migration_id:
                manifests.append(data)
        except Exception:
            continue

    return manifests


def load_gap_data(migration_id: str) -> Dict[str, Any]:
    """Load gap data for a specific migration."""
    return export_for_elyra_engineer(migration_id)


def build_engineer_prompt(
    gap_data: Dict[str, Any],
    manifests: List[Dict[str, Any]],
    migration_id: str,
) -> str:
    """Build the prompt that Kilo CLI will execute."""
    persona = PERSONA_PATH.read_text() if PERSONA_PATH.exists() else ""

    return f"""{persona}

## Task
Analyze post-run migration data for a specific migration run and produce an Elyra Engineer Report.

## Migration ID
{migration_id}

## Gap Ledger Data
{json.dumps(gap_data, indent=2)}

## BuildManifest Files ({len(manifests)} total)
{json.dumps(manifests[:5], indent=2)}

## Analysis Guidance
- Identify systematic issues: gaps appearing in ≥50% of runs or ≥3 occurrences
- Focus on data extraction gaps + visual/implementation gaps ONLY (v1 scope)
- Do NOT propose strategic/routing changes in v1
- Calculate quality score trends across all manifests
- Identify token fidelity violations from quality gate results
- Match issues to specific persona charter sections that need improvement
- Propose concrete, actionable fixes with rationale

## Output
Your final response must include:
1. A complete Elyra Engineer Report JSON (use the schema in the persona above)

Begin analysis now."""


def extract_json_from_output(stdout: str) -> tuple[Optional[str], Optional[str]]:
    """Extract JSON object from Kilo CLI --format json output.

    Kilo outputs NDJSON events. Find the last text event and extract JSON from it.
    Returns (json_str, last_text) for debugging.
    """
    stdout = stdout.strip()

    try:
        json.loads(stdout)
        return stdout, None
    except json.JSONDecodeError:
        pass

    last_text = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                last_text = event["part"].get("text", "")
        except json.JSONDecodeError:
            continue

    if last_text:
        last_text = last_text.strip()
        try:
            json.loads(last_text)
            return last_text, last_text
        except json.JSONDecodeError:
            pass

        first_brace = last_text.find("{")
        last_brace = last_text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace >= first_brace:
            json_str = last_text[first_brace : last_brace + 1]
            try:
                json.loads(json_str)
                return json_str, last_text
            except json.JSONDecodeError:
                pass

    first_brace = stdout.find("{")
    last_brace = stdout.rfind("}")
    if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
        return None, None

    json_str = stdout[first_brace : last_brace + 1]
    try:
        json.loads(json_str)
        return json_str, None
    except json.JSONDecodeError:
        return None, None


def parse_report(raw_json: str) -> Optional[Dict[str, Any]]:
    """Parse and validate JSON report."""
    try:
        data = json.loads(raw_json)
        return data
    except Exception as e:
        print(f"[WARN] JSON parse error: {e}")
        return None


def save_report(report: Dict[str, Any], migration_id: str) -> Path:
    """Save Elyra Engineer Report to memory directory."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{migration_id}_{timestamp}.json"
    filepath = REPORT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return filepath


def create_pr(report: Dict[str, Any]) -> Optional[str]:
    """Create a GitHub PR for systematic persona improvements.

    Returns the PR URL on success, None on failure.
    """
    candidates = report.get("persona_improvement_candidates", [])
    if not candidates:
        print("[INFO] No persona improvement candidates — skipping PR")
        return None

    branch_name = f"elyra-engineer/improve-personas-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    pr_body_lines = [
        f"## Elyra Engineer Report — {report.get('migration_id', 'unknown')}",
        "",
        f"**Generated:** {report.get('report_timestamp', datetime.now(timezone.utc).isoformat())}",
        "",
        "## Gap Summary",
    ]

    gap_summary = report.get("gap_summary", {})
    pr_body_lines.append(f"- Total gaps: {gap_summary.get('total_gaps', 0)}")

    systematic = report.get("systematic_issues", [])
    if systematic:
        pr_body_lines.append("")
        pr_body_lines.append("## Systematic Issues")
        pr_body_lines.append("")
        pr_body_lines.append("| Persona | Gap Type | Description | Severity |")
        pr_body_lines.append("|---------|----------|-------------|----------|")
        for issue in systematic:
            pr_body_lines.append(
                f"| {issue.get('persona', '')} "
                f"| {issue.get('gap_type', '')} "
                f"| {issue.get('description', '')[:60]} "
                f"| {issue.get('severity', '')} |"
            )

    pr_body_lines.append("")
    pr_body_lines.append("## Recommended Actions")
    pr_body_lines.append("")
    for i, action in enumerate(report.get("recommended_actions", []), 1):
        pr_body_lines.append(f"{i}. **{action.get('priority', 'medium').upper()}** — {action.get('description', '')}")

    pr_body_lines.append("")
    pr_body_lines.append("---")
    pr_body_lines.append("*This PR was auto-generated by Elyra Engineer. Human review required before merge.*")

    pr_body = "\n".join(pr_body_lines)

    title_parts = []
    for candidate in candidates[:2]:
        persona = candidate.get("persona", "unknown")
        title_parts.append(persona)
    title = f"[Elyra Engineer] Improve {', '.join(title_parts)}" if title_parts else "[Elyra Engineer] Persona improvements"

    files = []
    for candidate in candidates:
        persona = candidate.get("persona", "")
        current = candidate.get("current_behavior", "")
        improved = candidate.get("improved_behavior", "")
        rationale = candidate.get("rationale", "")

        if not persona or not improved:
            continue

        content_lines = [
            f"# Proposed Improvement: {persona}",
            "",
            f"## Rationale",
            rationale,
            "",
            f"## Current Behavior",
            current or "Not documented",
            "",
            f"## Proposed Behavior",
            improved,
            "",
            f"## Migration ID",
            report.get("migration_id", "unknown"),
        ]

        content = "\n".join(content_lines)
        path = f"memory/elyra_engineer_reports/improvement_{persona}_{report.get('migration_id', 'unknown')}.md"
        files.append({"path": path, "content": content})

    if not files:
        print("[INFO] No files to push — all candidates were empty")
        return None

    try:
        push_files(
            branch=branch_name,
            files=files,
            message=f"[Elyra Engineer] Propose persona improvements",
            owner=GITHUB_OWNER,
            repo=GITHUB_REPO,
        )
        print(f"[GITHUB] Branch created: {branch_name}")
    except Exception as e:
        print(f"[WARN] Could not push files to GitHub: {e}")
        return None

    try:
        pr = create_pull_request(
            base=GITHUB_BRANCH,
            body=pr_body,
            draft=True,
            head=branch_name,
            owner=GITHUB_OWNER,
            repo=GITHUB_REPO,
            title=title,
        )
        pr_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/pull/{pr.get('number', '?')}"
        print(f"[GITHUB] PR created: {pr_url}")
        return pr_url
    except Exception as e:
        print(f"[WARN] Could not create GitHub PR: {e}")
        return None


def get_migration_ids() -> List[str]:
    """Get all unique migration IDs from gap ledger."""
    entries = query_gaps()
    ids = set()
    for entry in entries:
        if entry.migration_id:
            ids.add(entry.migration_id)
    return sorted(ids)


def analyze(migration_id: str) -> Optional[Dict[str, Any]]:
    """
    Main entry point: load gap data + manifests -> build prompt -> call kilo run ->
    produce Elyra Engineer Report.

    Args:
        migration_id: ID of the migration to analyze

    Returns:
        Elyra Engineer Report dict or None on failure
    """
    print(f"\n[ENGINEER] Analyzing migration: {migration_id}")
    print("=" * 60)

    gap_data = load_gap_data(migration_id)
    manifests = load_build_manifests(migration_id)

    print(f"[GAP] {gap_data.get('gap_count', 0)} gaps logged")
    print(f"[BUILD] {len(manifests)} BuildManifest files found")

    if gap_data.get("gap_count", 0) == 0 and len(manifests) == 0:
        print("[WARN] No data available for analysis")
        return None

    prompt = build_engineer_prompt(gap_data, manifests, migration_id)

    try:
        import platform
        if platform.system() == "Windows":
            node_exe = (
                "C:\\Program Files\\nodejs\\node.exe"
                if Path("C:\\Program Files\\nodejs\\node.exe").exists()
                else "node"
            )
            kilo_bin_fallback = Path(
                "C:\\Users\\micha\\AppData\\Roaming\\npm\\node_modules\\@kilocode\\cli\\bin\\kilo"
            )
            kilo_bin = kilo_bin_fallback

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(prompt)
                prompt_file = f.name

            try:
                result = subprocess.run(
                    [node_exe, str(kilo_bin), "run", "--format", "json", "--auto", "--", f"@{prompt_file}"],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=600,
                )
            finally:
                try:
                    os.unlink(prompt_file)
                except Exception:
                    pass
        else:
            result = subprocess.run(
                ["kilo", "run", "--format", "json", "--auto", "--", prompt],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
    except subprocess.TimeoutExpired:
        print("[ERROR] Kilo CLI timed out after 10 minutes")
        return None
    except FileNotFoundError:
        print("[ERROR] 'kilo' command not found. Is Kilo CLI installed and in PATH?")
        return None

    if result.returncode != 0:
        print(f"[ERROR] Kilo CLI exited with code {result.returncode}")
        print(f"[STDERR] {result.stderr[:500] if result.stderr else ''}")
        return None

    stdout = result.stdout or ""

    print(f"[KILO] Output received ({len(stdout)} chars)")

    json_str, last_text = extract_json_from_output(stdout)
    if not json_str:
        print("[ERROR] Could not extract JSON from Kilo output")
        return None

    report = parse_report(json_str)
    if report:
        filepath = save_report(report, migration_id)
        print(f"  [OK] Elyra Engineer Report created")
        print(f"  [OUTPUT] {filepath}")

        systematic = report.get("persona_improvement_candidates", [])
        if systematic:
            print(f"  [ISSUES] {len(systematic)} systematic issues identified")
            for issue in systematic[:3]:
                print(f"    - {issue.get('persona')}: {issue.get('proposed_fix', '')[:80]}")

            pr_url = create_pr(report)
            if pr_url:
                print(f"  [GITHUB] PR: {pr_url}")
        else:
            print(f"  [OK] No systematic issues found — pipeline healthy")
    else:
        print("[ERROR] JSON parsed but failed validation")

    return report


if __name__ == "__main__":
    import sys

    migration_id = sys.argv[1] if len(sys.argv) > 1 else None

    if not migration_id:
        ids = get_migration_ids()
        if ids:
            migration_id = ids[-1]
            print(f"[AUTO] Analyzing most recent migration: {migration_id}")
        else:
            print("Usage: python elyra_engineer.py <migration_id>")
            print("Available migration IDs:", ids or "none")
            sys.exit(1)

    result = analyze(migration_id)
    if result:
        print("\n" + json.dumps(result, indent=2)[:2000])
    else:
        print("Analysis failed.")
        sys.exit(1)