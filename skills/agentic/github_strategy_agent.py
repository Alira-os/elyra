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
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

logging.basicConfig(level=logging.INFO, format='[github_strategy] %(message)s')
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
ELYRA_ROOT = SCRIPT_DIR.parent
KILO_CLI = ELYRA_ROOT / "tools" / "kilo.py"
PERSONA_PATH = ELYRA_ROOT / "registry" / "personas" / "deploy_specialist.md"
OUTPUT_DIR = ELYRA_ROOT / "memory" / "github_repos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _run_kilo_persona(prompt: str, persona_path: Path, timeout: int = 120) -> dict:
    """
    Run Kilo CLI with deploy_specialist persona for GitHub operations.

    Kilo has GitHub MCP connected natively. We build structured prompts
    and parse JSON output — Kilo handles the MCP tool invocations.

    Args:
        prompt: Task prompt for the persona
        persona_path: Path to persona markdown
        timeout: Seconds before timeout (default 120)

    Returns:
        Parsed JSON response or {"error": ...}
    """
    args = [
        sys.executable, str(KILO_CLI),
        "run",
        "--persona", str(persona_path),
        "--format", "json",
        "--"
    ]

    try:
        result = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            logger.error(f"Kilo CLI error: {result.stderr}")
            return {"error": result.stderr, "stdout": result.stdout}

        output = result.stdout.strip()

        # Try to parse as JSON
        try:
            return json.loads(output)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}. Raw output: {output[:200]}")
            return {"error": "JSON parse failed", "raw": output}

    except subprocess.TimeoutExpired:
        logger.error("Kilo CLI timed out")
        return {"error": "timeout"}
    except FileNotFoundError:
        logger.error(f"Kilo CLI not found at {KILO_CLI}")
        return {"error": f"Kilo CLI not found at {KILO_CLI}"}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"error": str(e)}


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

    result = _run_kilo_persona(prompt, PERSONA_PATH, timeout=60)
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