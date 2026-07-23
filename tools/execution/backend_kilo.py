"""
Kilo execution backend — subprocess LLM invocation + structured output.

This module preserves the existing `invoke_kilo` / `invoke_kilo_safe` /
`ToolResult` implementations (originally in `tools/kilo.py`) and adds a thin
:class:`KiloBackend` wrapper that conforms to the :class:`ExecutionBackend`
protocol defined in ``tools/execution/__init__.py``.

The wrapper is intentionally minimal: it composes the persona charter with the
task prompt, calls the existing subprocess machinery, extracts the first JSON
object from the resulting text, and validates it against the requested
``output_model``. Phase 1 callers will progressively replace ad-hoc
``invoke_kilo_safe`` calls in ``skills/agentic/*_agent.py`` with direct
``backend.invoke(persona, prompt, output_model)`` calls; this module is the
seam that makes that migration possible.

The legacy module ``tools/kilo.py`` is now a thin re-export shim that imports
from here. See ``AGENTS.md`` for the agent definition pattern.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Type, Union

from pydantic import BaseModel, ValidationError


# ---------------------------------------------------------------------------
# ToolResult — preserved verbatim from the legacy tools/kilo.py so existing
# callers (tests, orchestrator, skills/agentic/*) keep working unchanged.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _parse_kilo_output — preserved verbatim from the legacy tools/kilo.py.
# ---------------------------------------------------------------------------


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
    # truncated planning personas' JSON artifacts mid-string. 16KB
    # comfortably covers all persona outputs while staying well below
    # any memory pressure. See tools/kilo.py history for the full
    # rationale.
    return ToolResult(
        success=success,
        files_created=list(set(files_created)),  # Deduplicate
        files_modified=list(set(files_modified)),
        errors=[] if success else [f"Return code: {returncode}"],
        summary=final_text[:65_536] if final_text else "No output",
        recovery_suggestion=None if success else "Check Kilo output for errors"
    )


# ---------------------------------------------------------------------------
# Kilo binary discovery + subprocess runner — preserved verbatim.
# ---------------------------------------------------------------------------


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
        Path(__file__).resolve().parents[2]
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
    subprocess_env: Optional[dict[str, str]] = None,
) -> tuple[int, str, str]:
    """Run Kilo.

    On Windows with a native .exe (kilo.exe), we can safely pass the prompt
    via stdin since there's no batch interpreter involved. For .bat files
    on Windows, we must use a prompt file (@filepath) to avoid the batch stdin hang.
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
                env=subprocess_env,
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
                    repo_root = Path(__file__).resolve().parents[2]
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
                env=subprocess_env,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )
            return result.returncode, result.stdout or "", result.stderr or ""
        finally:
            try:
                os.unlink(prompt_file)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Legacy invoke_kilo / invoke_kilo_simple / invoke_kilo_safe — preserved
# verbatim so the existing callers (Phase 1 migration targets) keep working.
# ---------------------------------------------------------------------------


def invoke_kilo(
    prompt: str,
    context: dict,
    working_dir: str,
    timeout: int = 300,
    max_retries: int = 2,
    mutation_seed: Optional[str] = None,
    artifact_dir: Optional[str] = None,
    session_id: Optional[str] = None,
    sandbox_root: Optional[Path] = None,
    subprocess_env: Optional[dict[str, str]] = None,
) -> ToolResult:
    """Invoke Kilo as a tool for heavy codegen execution.

    See ``tools/kilo.py`` (legacy module) for the full docstring. This
    implementation is byte-identical to the original; it lives here now so
    the KiloBackend wrapper has the subprocess machinery in scope.
    """
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

    if subprocess_env is None:
        from tools.kilo_sandbox import make_sandbox_env, NO_SANDBOX_ENV_VAR
        sid = session_id or uuid.uuid4().hex[:12]
        try:
            subprocess_env, _sandbox_root = make_sandbox_env(sid)
        except Exception as e:
            print(f"[KILO] WARN could not build sandbox env: {e}; falling back to parent env")
            subprocess_env = None
    elif sandbox_root is not None:
        subprocess_env = {**os.environ, "XDG_DATA_HOME": str(sandbox_root)}

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
                subprocess_env=subprocess_env,
            )

            tool_result = _parse_kilo_output(stdout, returncode)
            last_result = tool_result

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
# invoke_kilo_safe — preserved verbatim (prompt-size + timeout guard-rails).
# ---------------------------------------------------------------------------

_MIN_KILO_TIMEOUT = 30
_MAX_KILO_TIMEOUT = 365 * 24 * 3600  # 1 year, effectively uncapped (Phase 1.2)
_PROMPT_WARN_CHARS = 999_999  # Soft warn disabled (Phase 1.2)
_PROMPT_REFUSE_CHARS = 256_000  # Hard refuse — catches true runaways


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
    sandbox_root: Optional[Path] = None,
    subprocess_env: Optional[dict[str, str]] = None,
) -> ToolResult:
    """Thin wrapper around invoke_kilo() with prompt-size + timeout safety.

    See ``tools/kilo.py`` (legacy module) for the full docstring.
    """
    import time

    safe_timeout = max(_MIN_KILO_TIMEOUT, min(int(timeout), _MAX_KILO_TIMEOUT))
    prompt_size = len(prompt or "")

    if prompt_size > _PROMPT_REFUSE_CHARS:
        msg = (
            f"Refusing to invoke Kilo: prompt is {prompt_size} chars "
            f"(> hard refuse {_PROMPT_REFUSE_CHARS}). This is a "
            f"runaway — the persona prompt builder is producing a "
            f"prompt that the LLM cannot handle well. "
            f"Reduce persona scope; check for binary files or "
            f"unbounded data in the prompt."
        )
        print(f"[KILO_SAFE][{persona}] {msg}")
        if on_timeout is not None:
            try:
                on_timeout(0.0, prompt_size, persona)
            except Exception:
                pass
        return ToolResult(
            success=False,
            errors=[msg],
            summary="Prompt too large for Kilo",
            recovery_suggestion=(
                "Reduce persona scope. Check the prompt builder "
                f"in skills/agentic/{persona}.py for untruncated schema "
                f"dumps, binary files, or unbounded data."
            ),
        )

    if prompt_size > _PROMPT_WARN_CHARS:
        print(
            f"[KILO_SAFE][{persona}] INFO prompt is {prompt_size} chars "
            f"(> soft warn {_PROMPT_WARN_CHARS}); consider compacting."
        )
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
            sandbox_root=sandbox_root,
            subprocess_env=subprocess_env,
        )
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[KILO_SAFE][{persona}] invoke_kilo raised {type(e).__name__}: {e}")
        return ToolResult(
            success=False,
            errors=[f"{type(e).__name__}: {e}"],
            summary=f"Kilo invocation failed after {elapsed:.1f}s",
            recovery_suggestion="Inspect Kilo logs and persona prompt.",
        )

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
            pass

    return result


# ---------------------------------------------------------------------------
# JSON extraction + BackendInvokeError — minimal helpers for KiloBackend.
# Kept deliberately small in Phase 0; Phase 1 callers may swap in
# skills/agentic/json_extract.py for richer error reporting.
# ---------------------------------------------------------------------------


class BackendInvokeError(RuntimeError):
    """Raised by a backend when it cannot produce a validated output_model."""

    def __init__(self, message: str, *, persona: Optional[str] = None,
                 output_model: Optional[Type[BaseModel]] = None,
                 raw_text: Optional[str] = None):
        self.persona = persona
        self.output_model = output_model
        self.raw_text = raw_text
        if output_model is not None:
            message = f"[{output_model.__name__}] {message}"
        if persona is not None:
            message = f"[{persona}] {message}"
        super().__init__(message)


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)


def _extract_json_object(text: str) -> dict:
    """Find a JSON object in text. Raises ValueError if none can be found.

    Tries, in order:
      1. Whole text parses as a JSON object
      2. A fenced ```json { ... } ``` block
      3. NDJSON event stream: scan lines, take the last "text" event's text
         and recurse into it
      4. Outermost { ... } in the text via json.JSONDecoder.raw_decode
    """
    if not text or not text.strip():
        raise ValueError("Empty text")

    # 1. Whole text
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 2. Fenced ```json ... ```
    m = _FENCE_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # 3. NDJSON: collect the last "text" event's text and recurse
    last_text = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if isinstance(event, dict) and event.get("type") == "text":
                part = event.get("part", {})
                if isinstance(part, dict):
                    t = part.get("text", "")
                    if isinstance(t, str) and t:
                        last_text = t
        except json.JSONDecodeError:
            continue

    if last_text and last_text != text:
        try:
            return _extract_json_object(last_text)
        except ValueError:
            pass

    # 4. Outermost { ... } via raw_decode
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, _end = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx = text.find("{", idx + 1)

    raise ValueError("No JSON object found in text")


# ---------------------------------------------------------------------------
# Persona resolution helper — used by KiloBackend.invoke() and exposed for
# other backends that want the same contract.
# ---------------------------------------------------------------------------


def resolve_persona(persona: "str | Path") -> tuple[str, str]:
    """Return (persona_name, persona_content).

    - If `persona` is a Path (or string path that exists on disk), read it
      and use its stem as the persona name.
    - If `persona` is a non-empty string, treat it as either a path (if it
      exists) or as the persona charter content directly.
    - Otherwise return ("unknown", "").
    """
    if isinstance(persona, Path):
        if persona.exists():
            try:
                content = persona.read_text(encoding="utf-8")
            except OSError:
                content = ""
            return persona.stem, content
        return persona.stem, ""

    if isinstance(persona, str):
        if not persona:
            return "", ""
        p = Path(persona)
        if p.exists() and p.is_file():
            try:
                content = p.read_text(encoding="utf-8")
            except OSError:
                content = ""
            return p.stem, content
        # Not a path — treat as raw charter content.
        return _infer_persona_name(persona), persona

    return "", ""


def _infer_persona_name(text: str) -> str:
    """Best-effort: pull a short name from a charter's first heading."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            name = line.lstrip("#").strip()
            if name:
                # Normalise to lowercase snake_case-ish identifier.
                return re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_").lower() or "persona"
    return "persona"


# ---------------------------------------------------------------------------
# KiloBackend — the ExecutionBackend implementation.
# ---------------------------------------------------------------------------


class KiloBackend:
    """ExecutionBackend that invokes the Kilo CLI as a subprocess LLM.

    Composes the persona charter with the task prompt, calls
    ``invoke_kilo_safe`` (preserving the prompt-size + timeout guard-rails),
    extracts the first JSON object from the resulting text, and validates it
    against the requested ``output_model``.

    Phase 0: provides the seam. Phase 1: callers in ``skills/agentic/*`` are
    rewritten to call ``backend.invoke(persona, prompt, output_model)``
    directly and the JSON-extraction + validation logic moves into this
    backend instead of being duplicated in every persona module.
    """

    DEFAULT_TIMEOUT_S = 300

    def __init__(self) -> None:
        # Append-only log of invocations — useful for tests and debugging.
        self.calls: list[dict[str, Any]] = []

    def invoke(
        self,
        persona: Union[str, Path],
        prompt: str,
        output_model: Type[BaseModel],
    ) -> BaseModel:
        """Invoke Kilo and validate the response against ``output_model``.

        Args:
            persona: Either a Path to a persona ``.md`` file in
                ``registry/personas/``, or a raw persona charter string.
            prompt: The task instruction (will be appended after the
                persona charter if a path/empty charter was supplied).
            output_model: The Pydantic class the response should conform to.

        Returns:
            A validated ``output_model`` instance.

        Raises:
            BackendInvokeError: Subprocess failure, missing JSON, or schema
                mismatch (after logging the validation error).
        """
        persona_name, persona_content = resolve_persona(persona)
        if persona_content:
            full_prompt = f"{persona_content}\n\n---\n\n{prompt}"
        else:
            full_prompt = prompt

        # Record the call for debugging / tests.
        self.calls.append({
            "persona": persona_name or str(persona),
            "prompt_size": len(full_prompt),
            "output_model": output_model.__name__,
        })

        result = invoke_kilo_safe(
            prompt=full_prompt,
            context={},
            working_dir=".",
            persona=persona_name or "persona",
            timeout=self.DEFAULT_TIMEOUT_S,
        )

        if not result.success:
            raise BackendInvokeError(
                f"Kilo invocation failed: {result.errors}",
                persona=persona_name or None,
                output_model=output_model,
            )

        raw_text = result.summary or ""
        try:
            parsed = _extract_json_object(raw_text)
        except ValueError as e:
            raise BackendInvokeError(
                f"No JSON object in Kilo output ({e}); raw_text[:400]={raw_text[:400]!r}",
                persona=persona_name or None,
                output_model=output_model,
                raw_text=raw_text,
            ) from e

        try:
            return output_model.model_validate(parsed)
        except ValidationError as e:
            # Lenient: log + raise. Do NOT silently coerce.
            print(
                f"[KILO_BACKEND] ValidationError for {output_model.__name__} "
                f"(persona={persona_name}): {e}"
            )
            raise BackendInvokeError(
                f"Kilo output did not match schema: {e}",
                persona=persona_name or None,
                output_model=output_model,
                raw_text=raw_text,
            ) from e


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


__all__ = [
    "ToolResult",
    "invoke_kilo",
    "invoke_kilo_simple",
    "invoke_kilo_safe",
    "KiloBackend",
    "BackendInvokeError",
    "resolve_persona",
]
