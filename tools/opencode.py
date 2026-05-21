"""
OpenCode Tool Interface

**Phase 1 Status:** LANGGRAPH-READY — Structured output, error handling, retry support.
**Phase 0 Behavior:** Subprocess-based with basic JSON output.

Purpose:
    Heavy codegen execution — OpenCode is the "hands" that builds the site.

Interface (stable):
    invoke_opencode(prompt, context, working_dir, timeout) -> ToolResult

The implementation may evolve but the interface remains stable.
"""

import subprocess
import json
import shutil
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolResult:
    """Structured result from OpenCode tool execution."""
    success: bool
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    summary: str = ""
    recovery_suggestion: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps({
            "success": self.success,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "errors": self.errors,
            "summary": self.summary,
            "recovery_suggestion": self.recovery_suggestion
        }, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "ToolResult":
        try:
            data = json.loads(json_str)
            return cls(
                success=data.get("success", False),
                files_created=data.get("files_created", []),
                files_modified=data.get("files_modified", []),
                errors=data.get("errors", []),
                summary=data.get("summary", ""),
                recovery_suggestion=data.get("recovery_suggestion")
            )
        except json.JSONDecodeError:
            return cls(
                success=False,
                errors=[f"Failed to parse JSON: {json_str[:200]}"],
                summary="Parse error"
            )

    @classmethod
    def from_text(cls, text: str, partial: bool = False) -> "ToolResult":
        """Parse OpenCode text output into ToolResult."""
        files_created = []
        files_modified = []

        created_match = re.search(r'Created?[`"\'](.+?)[`"\'\s]', text, re.IGNORECASE)
        if created_match:
            files_created.append(created_match.group(1))

        modified_match = re.search(r'Modified?[`"\'](.+?)[`"\'\s]', text, re.IGNORECASE)
        if modified_match:
            files_modified.append(modified_match.group(1))

        json_match = re.search(r'\{[^{]*"success"[^{]*\}', text)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return cls(
                    success=data.get("success", False),
                    files_created=data.get("files_created", files_created),
                    files_modified=data.get("files_modified", files_modified),
                    errors=data.get("errors", []),
                    summary=data.get("summary", text[:200]),
                    recovery_suggestion=data.get("recovery_suggestion")
                )
            except json.JSONDecodeError:
                pass

        if "Created" in text or "created" in text:
            success = True
            summary = "Files created successfully"
        elif "error" in text.lower() or "failed" in text.lower():
            success = False
            summary = text[:200]
        else:
            success = not partial
            summary = text[:200] if text else "No output"

        return cls(
            success=success,
            files_created=files_created if files_created else [],
            files_modified=files_modified if files_modified else [],
            errors=[] if success else [text[:200]],
            summary=summary,
            recovery_suggestion="Check file permissions and workspace path" if not success else None
        )


def _parse_opencode_output(stdout: str, returncode: int) -> ToolResult:
    """Parse OpenCode stdout into ToolResult."""
    if returncode == 0:
        try:
            data = json.loads(stdout)
            return ToolResult(
                success=data.get("success", True),
                files_created=data.get("files_created", []),
                files_modified=data.get("files_modified", []),
                errors=data.get("errors", []),
                summary=data.get("summary", "Completed"),
                recovery_suggestion=data.get("recovery_suggestion")
            )
        except json.JSONDecodeError:
            return ToolResult.from_text(stdout)
    else:
        return ToolResult(
            success=False,
            errors=[stdout[:500]] if stdout else ["Unknown error"],
            summary="OpenCode execution failed",
            recovery_suggestion="Verify OpenCode is installed and PATH is correct"
        )


def invoke_opencode(
    prompt: str,
    context: dict,
    working_dir: str,
    timeout: int = 300,
    max_retries: int = 2,
    mutation_seed: Optional[str] = None
) -> ToolResult:
    """
    Invoke OpenCode as a tool for heavy codegen execution.

    Args:
        prompt: The main task prompt for OpenCode to execute
        context: Additional context to pass (site metadata, stack choice, etc.)
        working_dir: Directory where OpenCode should operate
        timeout: Timeout in seconds (default: 300 = 5 minutes)
        max_retries: Number of retries on partial failure (default: 2)
        mutation_seed: Optional memory-derived guidance string to inject

    Returns:
        ToolResult with structured output

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
        if result.success:
            print(f"Created: {result.files_created}")
    """
    context_summary = json.dumps(context, indent=2)

    mutation_section = f"\n\n{mutation_seed}" if mutation_seed else ""

    full_prompt = f"""{prompt}

## Context
{context_summary}{mutation_section}

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
    "summary": "What was accomplished",
    "recovery_suggestion": "string or null"
}}
"""

    opencode_cmd = shutil.which("opencode")
    if not opencode_cmd:
        return ToolResult(
            success=False,
            errors=["OpenCode not found in PATH. Install from https://opencode.ai"],
            summary="OpenCode not available",
            recovery_suggestion="Install OpenCode CLI: npm install -g opencode"
        )

    if opencode_cmd.lower().endswith(".ps1"):
        cmd_list = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", opencode_cmd, "run", "--", full_prompt]
    else:
        cmd_list = [opencode_cmd, "run", "--", full_prompt]

    attempt = 0
    last_result = None

    while attempt <= max_retries:
        try:
            result = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                cwd=working_dir,
                timeout=timeout,
                encoding='utf-8',
                errors='replace'
            )

            tool_result = _parse_opencode_output(result.stdout, result.returncode)
            last_result = tool_result

            if tool_result.success:
                return tool_result

            if tool_result.files_created and attempt < max_retries:
                attempt += 1
                prompt = f"Continue the previous task. Files created so far: {tool_result.files_created}. Errors: {tool_result.errors}. Complete the remaining work."
                continue

            return tool_result

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                errors=[f"OpenCode execution timed out after {timeout}s"],
                summary="Timeout",
                recovery_suggestion=f"Increase timeout (current: {timeout}s) or simplify the task"
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                errors=["OpenCode not found in PATH"],
                summary="OpenCode not available",
                recovery_suggestion="Install OpenCode CLI: npm install -g opencode"
            )
        except Exception as e:
            if attempt < max_retries:
                attempt += 1
                continue
            return ToolResult(
                success=False,
                errors=[str(e)],
                summary="Unexpected error",
                recovery_suggestion="Check Python environment and OpenCode installation"
            )

    return last_result or ToolResult(success=False, errors=["Max retries exceeded"], summary="Failed")


def invoke_opencode_simple(
    prompt: str,
    working_dir: str = ".",
    timeout: int = 300
) -> ToolResult:
    """
    Simplified OpenCode invocation without context.

    Args:
        prompt: The task prompt
        working_dir: Working directory
        timeout: Timeout in seconds

    Returns:
        ToolResult with structured output
    """
    return invoke_opencode(prompt, {}, working_dir, timeout)


if __name__ == "__main__":
    result = invoke_opencode(
        prompt="Create a simple hello world HTML file",
        context={"test": True},
        working_dir="."
    )
    print(f"Success: {result.success}")
    print(f"Summary: {result.summary}")
    print(f"Files: {result.files_created}")


def create_opencode_tool():
    """
    Create a LangGraph-compatible tool from invoke_opencode.

    Usage:
        from langgraph.prebuilt import create_react_agent
        from tools.opencode import create_opencode_tool

        opencode_tool = create_opencode_tool()

        agent = create_react_agent(
            model=your_model,
            tools=[opencode_tool]
        )

        result = agent.invoke({"messages": [{"role": "user", "content": "Build a portfolio site"}]})
    """
    from langchain_core.tools import tool

    @tool
    def opencode_tool(prompt: str, context: dict = None, working_dir: str = ".") -> dict:
        """
        OpenCode heavy codegen tool for building websites and applications.

        Args:
            prompt: The main task prompt describing what to build
            context: Additional context (site metadata, stack choice, etc.)
            working_dir: Directory where OpenCode should operate

        Returns:
            Structured ToolResult with success status, files created, errors
        """
        ctx = context or {}
        result = invoke_opencode(prompt, ctx, working_dir)
        return {
            "success": result.success,
            "files_created": result.files_created,
            "files_modified": result.files_modified,
            "errors": result.errors,
            "summary": result.summary,
            "recovery_suggestion": result.recovery_suggestion
        }

    return opencode_tool


if __name__ == "__langgraph__":
    opencode_tool = create_opencode_tool()