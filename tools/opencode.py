"""
OpenCode Tool Interface

**Phase 0 Status:** SUBPROCESS-BASED — Calls opencode CLI via subprocess.
**Phase 1+ Target:** Consider wrapping as MCP tool or using official OpenCode SDK.

Purpose:
    Heavy codegen execution — OpenCode is the "hands" that builds the site.

Phase 0 Behavior:
    Uses subprocess.run() to invoke opencode CLI.
    Passes prompt + context as JSON to OpenCode.
    Returns stdout or error JSON.

Phase 1+ Options:
    1. Keep subprocess approach (simple, works)
    2. Wrap OpenCode as MCP tool so Conductor can invoke via tool protocol
    3. Use official OpenCode SDK if/when available

The OpenCode interface (function signature) should remain stable.
Only the implementation (subprocess vs MCP vs SDK) may change.
"""

import subprocess
import json
from typing import Optional


def invoke_opencode(
    prompt: str,
    context: dict,
    working_dir: str,
    timeout: int = 300
) -> str:
    """
    Invoke OpenCode as a tool for heavy codegen execution.

    Args:
        prompt: The main task prompt for OpenCode to execute
        context: Additional context to pass (site metadata, stack choice, etc.)
        working_dir: Directory where OpenCode should operate
        timeout: Timeout in seconds (default: 300 = 5 minutes)

    Returns:
        stdout from OpenCode, or error message

    Example:
        result = invoke_opencode(
            prompt="Build a portfolio site with Next.js + Tailwind",
            context={
                "site_name": "My Portfolio",
                "pages": ["home", "about", "contact"],
                "stack": "nextjs+tailwind"
            },
            working_dir="/path/to/output"
        )
    """
    context_summary = json.dumps(context, indent=2)

    full_prompt = f"""
{prompt}

## Context
{context_summary}

## Instructions
Execute the task as specified. Return a summary of what was done, including:
- Files created/modified
- Any errors encountered
- Commands run

Return your response as JSON:
{{
    "success": true/false,
    "files_created": ["file1", "file2"],
    "files_modified": ["file3"],
    "errors": [],
    "summary": "What was accomplished"
}}
"""

    try:
        result = subprocess.run(
            ["opencode", "--prompt", full_prompt],
            capture_output=True,
            text=True,
            cwd=working_dir,
            timeout=timeout
        )

        if result.returncode == 0:
            return result.stdout
        else:
            return json.dumps({
                "success": False,
                "errors": [result.stderr] if result.stderr else ["Unknown error"],
                "summary": "OpenCode execution failed"
            })

    except FileNotFoundError:
        return json.dumps({
            "success": False,
            "errors": ["OpenCode not found in PATH. Install from https://opencode.ai"],
            "summary": "OpenCode not available"
        })
    except subprocess.TimeoutExpired:
        return json.dumps({
            "success": False,
            "errors": [f"OpenCode execution timed out after {timeout}s"],
            "summary": "Timeout"
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "errors": [str(e)],
            "summary": "Unexpected error"
        })


def invoke_opencode_simple(
    prompt: str,
    working_dir: str = "."
) -> str:
    """
    Simplified OpenCode invocation without context.

    Args:
        prompt: The task prompt
        working_dir: Working directory

    Returns:
        stdout from OpenCode
    """
    return invoke_opencode(prompt, {}, working_dir)


if __name__ == "__main__":
    result = invoke_opencode(
        prompt="Create a simple hello world HTML file",
        context={"test": True},
        working_dir="."
    )
    print(result)