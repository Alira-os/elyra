"""
GitHub Strategy Agent for Elyra.

Thin Kilo CLI glue that handles GitHub repo creation under Alira-os org.
Repos are created ONLY after local build is complete and migration is ready for deploy.

**Architecture:**
All GitHub operations go through Kilo with deploy_specialist persona.
Kilo has GitHub MCP connected — no direct `gh` CLI wrapper needed.
The Python layer handles orchestration, state management, and pipeline glue.

Pattern: Kilo CLI + persona + Pydantic validation + save to memory.
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory.gap_ledger import log_gap
from skills.agentic.json_extract import extract_json, JSONExtractionError
from skills.agentic.kilo_callbacks import make_timeout_callback
from tools.kilo import invoke_kilo_safe

logging.basicConfig(level=logging.INFO, format='[github_strategy] %(message)s')
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
# skills/agentic/ -> skills/ -> elyra/
ELYRA_ROOT = SCRIPT_DIR.parent.parent
# (KILO_CLI constant removed in Phase 0.5 — _run_kilo_persona now calls
# invoke_kilo_safe() in-process instead of spawning a Python subprocess.)
PERSONA_PATH = ELYRA_ROOT / "registry" / "personas" / "deploy_specialist.md"
OUTPUT_DIR = ELYRA_ROOT / "memory" / "github_repos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _extract_json_from_text(text: str) -> Optional[str]:
    """Deprecated shim — kept only for one in-file caller.

    Use extract_json() from skills.agentic.json_extract.
    """
    try:
        return json.dumps(extract_json(text))
    except JSONExtractionError:
        return None


def _run_kilo_persona(prompt: str, persona_path: Path, timeout: int = 120, migration_id: str = "") -> dict:
    """
    Run Kilo CLI with deploy_specialist persona for GitHub operations.

    Kilo has GitHub MCP connected natively. We build structured prompts
    and parse JSON output — Kilo handles the MCP tool invocations.

    Phase 0.5: now uses invoke_kilo_safe() in-process rather than
    spawning a Python subprocess. This is faster, surfaces prompt-size
    and timeout guard-rails uniformly, and attributes timeouts to the
    gap ledger with the same schema as the other personas.

    Args:
        prompt: Task prompt for the persona
        persona_path: Path to persona markdown (embedded into the prompt)
        timeout: Seconds before timeout (default 120)
        migration_id: Migration ID for gap attribution (may be empty)

    Returns:
        Parsed JSON response or {"error": ...}
    """
    # Embed the persona into the prompt (matches the pattern used by the
    # other personas: scraper, architect, marketing, designer, builder).
    persona_md = persona_path.read_text() if persona_path.exists() else ""
    full_prompt = f"{persona_md}\n\n{prompt}"

    result = invoke_kilo_safe(
        prompt=full_prompt,
        context={"persona_path": str(persona_path), "migration_id": migration_id},
        working_dir=str(ELYRA_ROOT),
        persona="deploy_specialist",
        timeout=timeout,
        on_timeout=make_timeout_callback(
            persona="deploy_specialist",
            migration_id_fn=lambda: migration_id,
            default_timeout_s=timeout,
        ),
    )

    if not result.success:
        return {"error": result.errors[0] if result.errors else "kilo_invocation_failed"}

    output = result.summary or ""
    try:
        parsed = extract_json(output)
    except JSONExtractionError as e:
        logger.warning(f"JSONExtractionError: {e.reason}")
        return {"error": f"JSON parse failed: {e.reason}", "raw": output[:200]}

    if not isinstance(parsed, dict):
        return {"error": "extracted value is not a dict", "raw": output[:200]}

    # Legacy: if the parsed result is a ToolResult-shaped success wrapper
    # with a summary containing a nested action, unwrap it (parity with
    # the old behavior that did this manually).
    if parsed.get("success") is True and "action" not in parsed:
        summary = parsed.get("summary", "")
        if isinstance(summary, str):
            try:
                inner = extract_json(summary)
                if isinstance(inner, dict) and "action" in inner:
                    return inner
            except JSONExtractionError:
                pass

    return parsed


def create_github_repo(
    site_name: str,
    site_slug: str,
    description: str = "Migrated site via Elyra AI",
    org: str = "Alira-os",
    local_build_path: Optional[str] = None
) -> dict:
    """
    Create a GitHub repo under Alira-os org and optionally push local build.

    Uses Kilo with deploy_specialist persona — Kilo invokes GitHub MCP natively.
    The prompt describes what we need; Kilo handles the MCP tool calls.

    Args:
        site_name: Human-readable site name (e.g., "Saint Joseph the Worker Academy")
        site_slug: URL-safe slug (e.g., "saint-joseph-the-worker-academy")
        description: Repo description
        org: GitHub org (default: Alira-os)
        local_build_path: Optional path to locally-built site to push

    Returns:
        dict with repo_url, full_name, success, message
    """
    logger.info(f"Creating GitHub repo via Kilo + deploy_specialist: {org}/{site_slug}")

    prompt = f"""You are the GitHub Strategy specialist for Elyra.

Create a GitHub repository under the Alira-os organization with the following specs:

**Site Name:** {site_name}
**Repo Slug:** {site_slug}
**Organization:** {org}
**Description:** {description}

**Steps to perform using GitHub MCP tools:**
1. Create repo `{org}/{site_slug}` with description and private=true
2. If local_build_path exists and contains a built site:
   - Initialize git in that directory
   - Add remote to the new GitHub repo
   - Push main branch
   - Create a preview branch for review
3. Set up basic branch protection (require PR reviews)
4. Report the repo URL

**Output format (JSON only, no markdown):**
{{
  "success": true/false,
  "repo_url": "https://github.com/{org}/{site_slug}",
  "full_name": "{org}/{site_slug}",
  "default_branch": "main",
  "pushed_branches": ["main"] or [],
  "message": "What was done or what error occurred"
}}

Return ONLY valid JSON. No markdown code blocks, no explanation outside the JSON."""

    result = _run_kilo_persona(prompt, PERSONA_PATH, timeout=180)

    if "error" in result:
        logger.error(f"Kilo GitHub operation failed: {result['error']}")
        return {"success": False, "error": result["error"], "message": "Kilo CLI failed"}

    return result


def setup_github_actions(
    repo_full_name: str,
    branch: str = "main"
) -> dict:
    """
    Set up GitHub Actions workflows for a client site repo.

    Copies workflow files from Elyra's .github/workflows/ directory
    to the target repo using Kilo with deploy_specialist persona.
    Kilo invokes GitHub MCP to create the files.

    Creates:
    - .github/workflows/ci.yml (lint, test, build)
    - .github/workflows/deploy-preview.yml (Fly.io preview deploy)
    - .github/workflows/kilo-review.yml (Kilo code review on PRs)

    Production hardening:
    - Reads workflow files from disk (not embedded YAML strings)
    - Preserves existing workflow structure with caching
    - Kilo handles GitHub MCP file creation
    """
    workflows_dir = ELYRA_ROOT / ".github" / "workflows"
    created = []

    workflow_files = {
        "ci.yml": "Elyra CI",
        "deploy-preview.yml": "Deploy Preview",
        "kilo-review.yml": "Kilo Code Review"
    }

    for filename, workflow_name in workflow_files.items():
        local_path = workflows_dir / filename
        if not local_path.exists():
            logger.warning(f"Workflow file not found: {local_path}, skipping")
            continue

        content = local_path.read_text(encoding="utf-8")

        # Use Kilo to create the file via GitHub MCP
        success = _create_workflow_file_via_kilo(repo_full_name, filename, content)
        if success:
            created.append(filename)
            logger.info(f"Created workflow {filename} in {repo_full_name}")
        else:
            logger.warning(f"Failed to create workflow {filename} in {repo_full_name}")

    return {
        "workflows": created,
        "message": f"Workflows created: {', '.join(created) if created else 'none'}"
    }


def _create_workflow_file_via_kilo(repo_full_name: str, filename: str, content: str) -> bool:
    """
    Create a workflow file in the target repo via Kilo + GitHub MCP.

    Kilo has GitHub MCP connected — we prompt it to create the file
    using the GitHub API via MCP tools.
    """
    prompt = f"""Create a file in the GitHub repository `{repo_full_name}`.

**File path:** `.github/workflows/{filename}`
**Content:** (base64 encoded YAML)

The file content is:
```yaml
{content}
```

**Steps:**
1. Use GitHub MCP `create_or_update_file` or similar tool to create this file
2. Commit message: "Add {filename} workflow"

Return JSON:
{{
  "success": true/false,
  "file_path": ".github/workflows/{filename}",
  "message": "What happened"
}}"""

    result = _run_kilo_persona(prompt, PERSONA_PATH, timeout=180)  # Phase 1.2: lifted from 60
    return result.get("success", False)


def save_repo_spec(migration_id: str, spec: dict, output_path: Optional[Path] = None) -> Path:
    """Save GitHub repo spec to memory for audit trail."""
    output_path = output_path or OUTPUT_DIR
    output_path.mkdir(parents=True, exist_ok=True)
    path = output_path / f"{migration_id}_github_repo.json"
    spec["saved_at"] = datetime.now().isoformat()
    spec["migration_id"] = migration_id
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    logger.info(f"Saved repo spec to {path}")
    return path


def create_structured_migration_issue(
    migration_id: str,
    url: str,
    platform: str,
    issue_body: str
) -> dict:
    """
    Create a GitHub issue for a failed migration.

    Uses Kilo with deploy_specialist persona to create the issue via GitHub MCP.

    Args:
        migration_id: Unique migration identifier
        url: Source site URL
        platform: Platform (wix, wordpress, etc.)
        issue_body: Pre-formatted issue body text

    Returns:
        dict with success, issue_url, issue_number
    """
    logger.info(f"Creating GitHub issue for migration {migration_id}")

    prompt = f"""You are the GitHub Strategy specialist for Elyra.

Create a GitHub issue in the Alira-os/elyra repository to track a failed migration.

**Migration ID:** {migration_id}
**Source URL:** {url}
**Platform:** {platform}

**Issue Body:**
{issue_body}

**Steps to perform using GitHub MCP tools:**
1. Create a new issue in Alira-os/elyra with the provided title and body
2. Use appropriate labels: "migration-failure", "automated"
3. Set the issue title to: "[Migration Failed] {migration_id} - {platform}"

**Output format (JSON only, no markdown):**
{{
  "success": true/false,
  "issue_url": "https://github.com/Alira-os/elyra/issues/XXX",
  "issue_number": 123,
  "message": "What was done or what error occurred"
}}

Return ONLY valid JSON. No markdown code blocks, no explanation outside the JSON."""

    result = _run_kilo_persona(prompt, PERSONA_PATH, timeout=300)  # Phase 1.2: lifted from 120

    if "error" in result:
        logger.error(f"Kilo GitHub issue creation failed: {result['error']}")
        return {"success": False, "error": result["error"], "message": "Kilo CLI failed to create issue"}

    return result


def load_repo_spec(migration_id: str, output_path: Optional[Path] = None) -> Optional[dict]:
    """Load a previously saved GitHub repo spec."""
    output_path = output_path or OUTPUT_DIR
    path = output_path / f"{migration_id}_github_repo.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python github_strategy_agent.py <site_slug> [site_name] [local_build_path]")
        print("Example: python github_strategy_agent.py saint-joseph-the-worker-academy 'Saint Joseph the Worker Academy' ./build")
        sys.exit(1)

    site_slug = sys.argv[1]
    site_name = sys.argv[2] if len(sys.argv) > 2 else site_slug
    local_build = sys.argv[3] if len(sys.argv) > 3 else None

    print(f"Creating GitHub repo via Kilo + deploy_specialist: Alira-os/{site_slug}")
    result = create_github_repo(site_name, site_slug, local_build_path=local_build)
    print(json.dumps(result, indent=2))

    if result.get("success"):
        print(f"\nRepo URL: {result.get('repo_url')}")