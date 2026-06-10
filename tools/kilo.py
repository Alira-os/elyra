"""
Kilo Tool Interface

**Migration Status:** Ported from OpenCode to Kilo.
**Phase 1 Status:** LANGGRAPH-READY — Structured output, error handling, retry support.

Purpose:
    Heavy codegen execution — Kilo is the "hands" that builds the site.

Interface (stable):
    invoke_kilo(prompt, context, working_dir, timeout) -> ToolResult

The implementation may evolve but the interface remains stable.
"""

import subprocess
import json
import shutil
import re
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ToolResult:
    """Structured result from Kilo tool execution."""
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
        """Parse Kilo text output into ToolResult."""
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


def _parse_kilo_output(stdout: str, returncode: int) -> ToolResult:
    """Parse Kilo stdout into ToolResult.

    Kilo outputs NDJSON (newline-delimited JSON) when using --format json.
    Each line is a separate JSON object with event type in "type" field.
    """
    if not stdout.strip():
        return ToolResult(
            success=False,
            errors=[f"No output (returncode={returncode})"],
            summary="Kilo produced no output",
            recovery_suggestion="Check Kilo configuration and API access"
        )

    # Parse NDJSON - each line is a separate JSON object
    lines = [line.strip() for line in stdout.strip().split('\n') if line.strip()]
    if not lines:
        return ToolResult(
            success=False,
            errors=[f"Empty output after parsing (returncode={returncode})"],
            summary="No JSON objects in output",
            recovery_suggestion="Check Kilo version and format settings"
        )

    files_created = []
    files_modified = []
    final_text = ""
    last_event_type = None

    for line in lines:
        try:
            obj = json.loads(line)
            event_type = obj.get("type", "")

            if event_type == "text":
                # Accumulate ALL text content (don't overwrite — Kilo may emit multiple text events)
                part = obj.get("part", {})
                if isinstance(part, dict):
                    text_content = part.get("text", "")
                    if text_content:
                        if final_text:
                            final_text += "\n" + text_content
                        else:
                            final_text = text_content

            elif event_type == "tool_use":
                # Extract file creation/modification from tool calls
                part = obj.get("part", {})
                if isinstance(part, dict):
                    tool_name = part.get("tool", "")
                    tool_input = part.get("state", {}).get("input", {})
                    if tool_name == "write" and isinstance(tool_input, dict):
                        file_path = tool_input.get("filePath", "")
                        if file_path:
                            files_created.append(file_path)
                    elif tool_name in ("read", "edit", "multi_edit") and tool_input:
                        file_path = tool_input.get("filePath") if isinstance(tool_input, dict) else None
                        if file_path:
                            files_modified.append(file_path)

            last_event_type = event_type

        except json.JSONDecodeError:
            # Skip malformed JSON lines
            continue

    # Determine success based on return code and actual work done
    success = returncode == 0 and bool(files_created or files_modified or final_text)

    if not final_text and not files_created and not files_modified:
        # No text or file output - may be a simple acknowledgment
        # Look at the last event to determine what happened
        if returncode == 0 and last_event_type in ("step_finish", "tool_use"):
            success = True
            final_text = "Kilo task completed"
        elif returncode == 0:
            final_text = "Completed"
        else:
            final_text = f"Kilo error (code {returncode})"

    # Phase 0.6.2: bumped from 2000 to 16000 chars. A 2000-char cap
    # truncated planning personas' JSON artifacts (e.g. a 2-variant
    # ContentRecommendation with a full BrandSpec and page_strategies
    # is 5-10KB) mid-string, producing "no JSON found" extraction
    # failures. 16KB comfortably covers all persona outputs while
    # staying well below any memory pressure. The invoke_kilo_safe
    # Output capture limit (advisory). The cap exists to bound memory
    # usage on long Kilo runs; the *real* artifact is recovered from
    # the on-disk scratch dir + the post-run validator. Most persona
    # outputs are <8KB; this 512KB ceiling accommodates even a
    # 60K-prompt-then-60K-output scenario with headroom. Bump it if
    # Kilo's response format ever changes.
    return ToolResult(
        success=success,
        files_created=list(set(files_created)),  # Deduplicate
        files_modified=list(set(files_modified)),
        errors=[] if success else [f"Return code: {returncode}"],
        summary=final_text[:512_000] if final_text else "No output",
        recovery_suggestion=None if success else "Check Kilo output for errors"
    )


def _find_kilo_bin() -> Optional[tuple[list[str], Path]]:
    """Find Kilo binary and determine how to invoke it.
    Returns (invocation_cmd_list, kilo_bin_path) or (None, None).
    On Windows, kilo.exe is a native binary invoked directly (not via node).
    On other platforms, kilo is a node script invoked via node.
    """
    import platform

    system = platform.system()

    # Possible kilo binary locations
    local_kilo = (
        Path(__file__).resolve().parents[1]
        / "node_modules"
        / "@kilocode"
        / "cli"
        / "bin"
        / "kilo"
    )
    npm_kilo = Path(
        "C:\\Users\\micha\\AppData\\Roaming\\npm\\node_modules\\@kilocode\\cli\\bin\\kilo"
    )
    npm_kilo_exe = Path(
        "C:\\Users\\micha\\AppData\\Roaming\\npm\\node_modules\\@kilocode\\cli\\node_modules\\@kilocode\\cli-windows-x64\\bin\\kilo.exe"
    )

    if system == "Windows":
        # On Windows, prefer kilo.exe (native binary) over kilo.bat
        if npm_kilo_exe.exists():
            return ([str(npm_kilo_exe)], npm_kilo_exe)
        if local_kilo.exists():
            # local might be .bat or .exe
            ext = local_kilo.suffix.lower()
            if ext in (".exe", ""):
                return ([str(local_kilo)], local_kilo)
            # it's a .bat/.cmd - need special handling via node script
            bat_path = local_kilo.with_suffix(".bat")
            if bat_path.exists():
                return ([str(bat_path)], bat_path)
        if npm_kilo.exists():
            ext = npm_kilo.suffix.lower()
            if ext in (".exe", ""):
                return ([str(npm_kilo)], npm_kilo)
            bat_path = npm_kilo.with_suffix(".bat")
            if bat_path.exists():
                return ([str(bat_path)], bat_path)
        return None, None
    else:
        # Unix - use kilo script directly
        for candidate in [local_kilo, npm_kilo]:
            if candidate.exists():
                return ([str(candidate)], candidate)
        return None, None


def _run_kiloInteractive(
    kilo_invocation: list[str],
    prompt: str,
    timeout: int,
    cwd: str,
    artifact_dir: Optional[str] = None,
    session_id: Optional[str] = None,
    use_stdin: bool = False,
) -> tuple[int, str, str]:
    """Run Kilo.

    On Windows with a native .exe (kilo.exe), we can safely pass the prompt
    via stdin since there's no batch interpreter involved. For .bat files
    on Windows, we must use a prompt file (@filepath) to avoid the batch stdin hang.

    Args:
        kilo_invocation: Command list, e.g. ['C:\\path\\to\\kilo.exe'] or ['node', 'C:\\path\\to\\kilo']
        prompt: The full prompt string
        timeout: Timeout in seconds
        cwd: Working directory
        artifact_dir: If set, Kilo MCP artifacts go here
        session_id: Session ID for artifact scoping
        use_stdin: If True, pass prompt via stdin; if False, use @prompt_file
    """
    import tempfile

    prompt_file = None
    if use_stdin:
        # Pass prompt via stdin - safe only for native .exe on Windows
        cmd = kilo_invocation + ["run", "--auto", "--format", "json"]
        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )
            return result.returncode, result.stdout or "", result.stderr or ""
        except subprocess.TimeoutExpired:
            return -1, "", f"Timed out after {timeout}s"
    else:
        # Use prompt file - required for batch files, safe for all platforms
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            cmd = kilo_invocation + ["run", "--auto", "--format", "json", "--", f"@{prompt_file}"]

            # Determine where Kilo runs and writes artifacts
            if artifact_dir:
                resolved_artifact_dir = Path(artifact_dir)
                if not resolved_artifact_dir.is_absolute():
                    repo_root = Path(__file__).resolve().parents[1]
                    resolved_artifact_dir = repo_root / resolved_artifact_dir
                if session_id:
                    resolved_artifact_dir = resolved_artifact_dir / session_id
                resolved_artifact_dir.mkdir(parents=True, exist_ok=True)
                run_cwd = str(resolved_artifact_dir)
            else:
                run_cwd = cwd

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=run_cwd,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )
            return result.returncode, result.stdout or "", result.stderr or ""
        finally:
            try:
                os.unlink(prompt_file)
            except Exception:
                pass


def invoke_kilo(
    prompt: str,
    context: dict,
    working_dir: str,
    timeout: int = 300,
    max_retries: int = 2,
    mutation_seed: Optional[str] = None,
    artifact_dir: Optional[str] = None,
    session_id: Optional[str] = None,
) -> ToolResult:
    """
    Invoke Kilo as a tool for heavy codegen execution.

    Args:
        prompt: The task prompt.
        context: Dict of context values injected into the prompt.
        working_dir: Directory to run Kilo in.
        timeout: Seconds before timeout (default 300).
        max_retries: Number of retries on failure (default 2).
        mutation_seed: Optional pre-injected memory context.
        artifact_dir: If set, Kilo MCP artifacts are written here instead of CWD.
                     Relative paths are resolved from repo root.
                     Example: ".kilo/artifacts/session-abc-123"
        session_id: Session ID used to scope artifacts. If artifact_dir is set and this
                   is not provided, a new session_id is generated. Ignored if
                   artifact_dir is None.
    """
    # context may contain Pydantic HttpUrl/datetime/etc. values when
    # callers pass model fields directly. Coerce them to JSON-safe types
    # via default=str so the prompt build never crashes on serialization.
    context_summary = json.dumps(context, indent=2, default=str)
    mutation_section = f"\n\n{mutation_seed}" if mutation_seed else ""

    full_prompt = f"""{prompt}

## Context
{context_summary}{mutation_section}

## Instructions
Execute the task as specified. Return a summary of what was done.

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

    kilo_invocation, kilo_bin = _find_kilo_bin()
    if not kilo_invocation:
        return ToolResult(
            success=False,
            errors=["Kilo not found in PATH"],
            summary="Kilo not available",
            recovery_suggestion="Install Kilo CLI: npm install -g @kilocode/cli"
        )

    # For native Windows .exe, we can safely use stdin; for batch files we must use prompt file
    import platform
    is_windows_native = (
        platform.system() == "Windows"
        and kilo_bin is not None
        and kilo_bin.suffix.lower() == ".exe"
    )
    use_stdin = is_windows_native

    attempt = 0
    last_result = None
    max_attempts = max(1, max_retries + 1)

    while attempt < max_attempts:
        try:
            returncode, stdout, stderr = _run_kiloInteractive(
                kilo_invocation,
                full_prompt,
                timeout,
                working_dir,
                artifact_dir=artifact_dir,
                session_id=session_id,
                use_stdin=use_stdin,
            )

            tool_result = _parse_kilo_output(stdout, returncode)
            last_result = tool_result

            # If Kilo wrote files to disk (even if JSON summary parsing failed),
            # treat it as a successful execution. The caller can look for
            # artifacts on disk to recover the result.
            if tool_result.files_created and not tool_result.success:
                tool_result.success = True
                tool_result.errors = [e for e in tool_result.errors if "returncode" in e.lower()]
                if not tool_result.errors:
                    tool_result.errors = []

            if tool_result.success:
                return tool_result

            if tool_result.files_created and attempt < max_attempts:
                attempt += 1
                continue

            return tool_result

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                errors=[f"Kilo execution timed out after {timeout}s"],
                summary="Timeout",
                recovery_suggestion=f"Increase timeout (current: {timeout}s)"
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                errors=["Kilo not found in PATH"],
                summary="Kilo not available",
                recovery_suggestion="Install Kilo CLI"
            )
        except Exception as e:
            if attempt < max_attempts:
                attempt += 1
                continue
            return ToolResult(
                success=False,
                errors=[str(e)],
                summary="Unexpected error",
                recovery_suggestion="Check Python environment"
            )

    return last_result or ToolResult(success=False, errors=["Max retries exceeded"], summary="Failed")


def invoke_kilo_simple(prompt: str, working_dir: str = ".", timeout: int = 300) -> ToolResult:
    """Simplified Kilo invocation."""
    return invoke_kilo(prompt, {}, working_dir, timeout)


# ---------------------------------------------------------------------------
# invoke_kilo_safe — Phase 0: hard timeouts + prompt-size logging
# ---------------------------------------------------------------------------
#
# Rationale (from triage of last E2E run):
#   - Builder timeout was 10 minutes (600s) with no size check, and Manager
#     timeout was 120s. Timeouts on persona calls were inconsistent: 120s,
#     300s, 600s. We saw two real timeouts in the last run (10min builder,
#     120s designer).
#   - The manager prompt is ~13K chars (per inline comment at orchestrator.py:541).
#     Kilo can hang on prompts > 16K.
#
# This wrapper:
#   1. Logs prompt size in characters before each invocation.
#   2. Enforces min/max bounds on the timeout parameter (30s ≤ t ≤ 600s).
#   3. On timeout, invokes a caller-supplied callback (typically: log a gap
#      to the Gap Ledger with the prompt size, elapsed time, and persona name).
#   4. Returns a uniform ToolResult shape so existing callers don't change.
#
# Usage in persona modules:
#   from tools.kilo import invoke_kilo_safe
#   result = invoke_kilo_safe(
#       prompt=...,
#       context={...},
#       working_dir=".",
#       persona="ui_designer",
#       timeout=300,
#       on_timeout=lambda elapsed, size, persona: log_gap(...),
#   )

_MIN_KILO_TIMEOUT = 30
_MAX_KILO_TIMEOUT = 600
# Phase 0.8 (operational quality): the prompt-size guard was REMOVED.
# The legacy code refused to invoke Kilo when the prompt exceeded
# _PROMPT_REFUSE_CHARS (40K) — but the actual failure mode was a
# Kilo CLI truncation bug (2000-char summary cap) which has since
# been fixed. The "refuse to invoke" gate was a heuristic that
# blocked legitimate large prompts (e.g. the frontend architect
# legitimately needs ~35K to converge all upstream artifacts).
#
# The new policy is ADVISORY: we log the size for observability, but
# the actual constraint is the LLM/Kilo. If a persona consistently
# produces 60K+ prompts, that means the prompt builder needs work,
# not that we should refuse the call.
_PROMPT_WARN_CHARS = 64_000  # Soft warn — log only.
# The "refuse" threshold is now effectively infinity. The variable is
# kept for backward compat (callers can read it for diagnostics).
_PROMPT_REFUSE_CHARS = 10_000_000  # 10M chars — never triggered in practice.


def invoke_kilo_safe(
    prompt: str,
    context: dict,
    working_dir: str,
    persona: str,
    timeout: int = 300,
    max_retries: int = 2,
    on_timeout=None,
    mutation_seed: Optional[str] = None,
    artifact_dir: Optional[str] = None,
    session_id: Optional[str] = None,
) -> ToolResult:
    """Thin wrapper around invoke_kilo() with prompt-size + timeout safety.

    Args:
        prompt: task prompt
        context: context dict (passed through to invoke_kilo)
        working_dir: CWD for the subprocess
        persona: name of the calling persona (e.g. "ui_designer", "builder");
                 used in log lines and the on_timeout callback.
        timeout: seconds; clamped to [30, 600].
        max_retries: passed through to invoke_kilo.
        on_timeout: optional callable(elapsed_s, prompt_size_chars, persona)
                    invoked when the Kilo subprocess times out. Use it to log
                    a gap. If None, the timeout is silent.
        mutation_seed, artifact_dir, session_id: passed through to invoke_kilo.

    Returns:
        ToolResult — same shape as invoke_kilo().
    """
    import time
    import sys

    safe_timeout = max(_MIN_KILO_TIMEOUT, min(int(timeout), _MAX_KILO_TIMEOUT))
    prompt_size = len(prompt or "")

    # Phase 0.8: prompt-size is now ADVISORY only. The previous
    # hard-refuse at _PROMPT_REFUSE_CHARS blocked legitimate large
    # prompts and forced the manager loop to short-circuit. The
    # actual fix is in the prompt builders (compact views + lean
    # schemas); if a persona's prompt blows past _PROMPT_WARN_CHARS,
    # we log it for observability but proceed.
    if prompt_size > _PROMPT_WARN_CHARS:
        print(
            f"[KILO_SAFE][{persona}] INFO prompt is {prompt_size} chars "
            f"(> {_PROMPT_WARN_CHARS}); consider compacting."
        )
        # Emit a soft gap so the gap ledger shows when a persona
        # has a bloated prompt — this is a sign the prompt builder
        # needs attention, not a hard failure.
        try:
            from memory.gap_ledger import log_gap
            log_gap(
                migration_id="",
                gap_type="advisory",
                source_persona=persona,
                description=(
                    f"Persona prompt is {prompt_size} chars "
                    f"(> soft warn {_PROMPT_WARN_CHARS}). "
                    f"Consider compacting via skills/agentic/prompt_budget.py."
                ),
                suggested_fix="Run persona prompt builder and check for untruncated schema dumps.",
                severity="low",
            )
        except Exception:
            pass

    # The _PROMPT_REFUSE_CHARS variable is kept for diagnostics but
    # no longer blocks invocation. The actual constraint is the LLM
    # and the Kilo CLI's own input handling.
    if prompt_size > _PROMPT_REFUSE_CHARS:
        # Should not be reachable now (~10M chars). Log defensively.
        print(
            f"[KILO_SAFE][{persona}] WARN: prompt is {prompt_size} chars, "
            f"exceeding diagnostic threshold {_PROMPT_REFUSE_CHARS}."
        )

    t0 = time.time()
    try:
        result = invoke_kilo(
            prompt=prompt,
            context=context,
            working_dir=working_dir,
            timeout=safe_timeout,
            max_retries=max_retries,
            mutation_seed=mutation_seed,
            artifact_dir=artifact_dir,
            session_id=session_id,
        )
    except Exception as e:
        # Defensive: invoke_kilo is supposed to catch everything and return a
        # ToolResult, but a hard failure (e.g. unexpected exception type) is
        # still possible. Surface it uniformly.
        elapsed = time.time() - t0
        print(f"[KILO_SAFE][{persona}] invoke_kilo raised {type(e).__name__}: {e}")
        return ToolResult(
            success=False,
            errors=[f"{type(e).__name__}: {e}"],
            summary=f"Kilo invocation failed after {elapsed:.1f}s",
            recovery_suggestion="Inspect Kilo logs and persona prompt.",
        )

    # Detect timeout via the standard recovery_suggestion string set in
    # invoke_kilo. The persona can also see the ToolResult and decide, but
    # logging here gives consistent gap attribution.
    if (
        not result.success
        and result.recovery_suggestion
        and "timeout" in result.recovery_suggestion.lower()
        and on_timeout is not None
    ):
        elapsed = time.time() - t0
        try:
            on_timeout(elapsed, prompt_size, persona)
        except Exception:
            # Callback failure must not crash the persona.
            pass

    return result


if __name__ == "__main__":
    result = invoke_kilo(
        prompt="Create a simple hello world HTML file",
        context={"test": True},
        working_dir="."
    )
    print(f"Success: {result.success}")
    print(f"Summary: {result.summary}")
    print(f"Files: {result.files_created}")


def create_kilo_tool():
    """Create a LangGraph-compatible tool from invoke_kilo."""
    from langchain_core.tools import tool

    @tool
    def kilo_tool(prompt: str, context: dict = None, working_dir: str = ".") -> dict:
        ctx = context or {}
        result = invoke_kilo(prompt, ctx, working_dir)
        return {
            "success": result.success,
            "files_created": result.files_created,
            "files_modified": result.files_modified,
            "errors": result.errors,
            "summary": result.summary,
            "recovery_suggestion": result.recovery_suggestion
        }

    return kilo_tool


if __name__ == "__langgraph__":
    kilo_tool = create_kilo_tool()