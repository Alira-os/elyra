"""
devops_engineer.py — Phase 1.1 Forge Room persona (Deployment Guardian).

Produces a DeploySpec artifact describing the deployment, scaling,
monitoring, and CI/CD setup for the migrated site. Runs EARLY in
the Forge Room (per the design) so its constraints inform the
Data Engineer's and Backend Architect's decisions.

This is a NEW persona, distinct from `github_strategy_agent.py`:
  - `github_strategy_agent` runs AFTER the build, creates the GitHub
    repo, sets up CI workflow files, and creates GitHub issues for
    failed migrations. It uses the deploy_specialist.md persona
    markdown (a GitHub-strategy playbook).
  - `devops_engineer` runs EARLY in the Forge Room, before any code
    is written. It produces a DeploySpec (Pydantic schema) that the
    rest of the Forge Room reads. It loads `deploy_engineer.md`
    (a purpose-built, small persona) — NOT `deploy_specialist.md`,
    which is geared toward GitHub strategy and at ~20KB consumes
    half the prompt budget while telling Kilo to invoke Cloudflare
    MCP and wait for human approval, neither of which is wanted
    here.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import (  # noqa: E402
    DeploySpec,
    SiteArchitecture,
    SiteUnderstanding,
)

from skills.agentic.forge_common import (  # noqa: E402
    DEPLOY_SPECS_DIR,
    PERSONA_TIMEOUTS_S,
    _serialize_compact,
    get_latest_artifact_id,
    invoke_kilo_for_persona,
    load_persona_markdown,
    make_failed_invocation_gap,
    save_artifact_to_dir,
)
from skills.agentic.prompt_budget import (  # noqa: E402
    compact_site_understanding,
    compact_site_architecture,
)


def build_devops_prompt(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
    *,
    gap_context: Optional[str] = None,
) -> str:
    """Build the devops engineer's prompt — runs FIRST in the Forge Room."""
    persona = load_persona_markdown("deploy_engineer")
    if not persona:
        persona = load_persona_markdown("deploy_specialist")
    if not persona:
        persona = (
            "You are the DevOps Engineer (Deployment Guardian) in Elyra's "
            "Forge Room. You produce a DeploySpec (Pydantic schema below) "
            "that constrains the rest of the Forge Room. You run EARLY so "
            "the Data Engineer and Backend Architect can design their "
            "artifacts to match the deploy target. For most sites this "
            "is a static deploy (Vercel, Netlify, Cloudflare Pages, or "
            "fly.io with a small machine). For CMS-driven or e-commerce "
            "sites this may include a managed database, edge functions, "
            "or a custom auth layer."
        )

    site_json, arch_json = _serialize_compact(
        compact_site_understanding(site),
        compact_site_architecture(architecture),
    )
    schema_json = json.dumps(DeploySpec.model_json_schema(), indent=2)

    gap_section = ""
    if gap_context:
        gap_section = f"""

## Prioritized Rework Instructions
{gap_context}

Apply these changes first. The orchestrator may route you back here if the Data Engineer or Backend Architect find your spec unworkable.
"""

    return f"""{persona}

## Task
Produce a `DeploySpec` artifact (Pydantic schema below) describing the
deployment, scaling, monitoring, and CI/CD setup for the migrated site.
{gap_section}

## Input SiteUnderstanding (compact view)
{site_json}

## Input SiteArchitecture (compact view)
{arch_json}

## Output Contract
Output ONLY valid JSON matching the schema below — no markdown, no commentary,
no text outside the JSON object:
{schema_json}

Begin deploy design now."""


def _scan_json_state(body: str) -> tuple:
    depth_brace = 0
    depth_bracket = 0
    in_string = False
    escape_next = False
    last_complete_index = -1
    for i, c in enumerate(body):
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth_brace += 1
        elif c == "}":
            depth_brace -= 1
            if depth_brace == 0 and depth_bracket == 0:
                last_complete_index = i
        elif c == "[":
            depth_bracket += 1
        elif c == "]":
            depth_bracket -= 1
            if depth_brace == 0 and depth_bracket == 0:
                last_complete_index = i
    return depth_brace, depth_bracket, in_string, last_complete_index


def _close_truncated_json(text: str) -> Optional[str]:
    """If `text` looks like a truncated JSON object, append the missing
    `}` / `]` / quote and try to make it valid. Returns the repaired
    string, or None if the input doesn't look like an open JSON object.

    Strategy: try multiple candidate cut points (at each top-level
    comma) and return the longest that yields valid JSON. Drops a
    trailing partial entry but keeps complete ones.
    """
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    body = text[start:]

    depth_brace, depth_bracket, in_string, _ = _scan_json_state(body)
    if depth_brace == 0 and depth_bracket == 0 and not in_string:
        return body

    if in_string:
        body = body + '"'

    top_level_commas = []
    db = 0
    dq = 0
    ins = False
    esc = False
    for i, c in enumerate(body):
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"' and not esc:
            ins = not ins
            continue
        if ins:
            continue
        if c == "{":
            db += 1
        elif c == "}":
            db -= 1
        elif c == "[":
            dq += 1
        elif c == "]":
            dq -= 1
        elif c == "," and db == 1 and dq == 0:
            top_level_commas.append(i)

    cut_points = [len(body)] + top_level_commas[::-1] + [0]

    def _try_close(candidate: str) -> Optional[str]:
        if not candidate.startswith("{"):
            return None
        cdb, cdq, cins, _ = _scan_json_state(candidate)
        if cins or cdb < 0 or cdq < 0:
            return None
        closed = candidate.rstrip()
        if closed.endswith(","):
            closed = closed[:-1].rstrip()
        if closed.endswith(":"):
            return None
        closed += "]" * cdq + "}" * cdb
        try:
            obj = json.loads(closed)
            return obj
        except Exception:
            return None

    for cut in cut_points:
        candidate = body[:cut].rstrip()
        if _try_close(candidate) is not None:
            cdb, cdq, _, _ = _scan_json_state(candidate)
            closed = candidate.rstrip()
            if closed.endswith(","):
                closed = closed[:-1].rstrip()
            closed += "]" * cdq + "}" * cdb
            return closed

    return None


def _lenient_parse_deploy_spec(raw: str) -> Optional[dict]:
    if not raw or not raw.strip():
        return None

    def _try_load(candidate: str) -> Optional[dict]:
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    parsed = _try_load(raw)
    if parsed is not None:
        return parsed

    fence_re = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    for m in fence_re.finditer(raw):
        parsed = _try_load(m.group(1).strip())
        if parsed is not None:
            return parsed

    repaired = _close_truncated_json(raw)
    if repaired is not None:
        parsed = _try_load(repaired)
        if parsed is not None:
            return parsed

    try:
        from skills.agentic.json_extract import extract_json
        return extract_json(raw)
    except Exception:
        return None


def _retry_prompt_for_reemit() -> str:
    """Short, terse re-emit prompt used after a first extraction failure.

    The Kilo output was either truncated or prose. We ask for a clean
    JSON-only re-emit. No markdown fences, no prose, no schema dump —
    we already have the JSON shape in the original prompt; we just need
    the model to produce it again, smaller.
    """
    return (
        "Your previous response was not parseable JSON. "
        "Re-emit the DeploySpec as a single JSON object "
        "(no ``` fence, no prose, no comments). "
        'Example: {"platform": "fly", "site_slug": "x", '
        '"scaling": {"min_instances": 0, "max_instances": 1}} '
        "Keep it under 1500 chars. Use platform one of: "
        '"fly", "vercel", "netlify", "cloudflare_pages", "static_hosting", "other".'
    )


def design_deploy_spec(
    site: SiteUnderstanding,
    architecture: SiteArchitecture,
    *,
    migration_id: str = "",
    site_slug: str = "",
    gap_context: Optional[str] = None,
) -> Optional[DeploySpec]:
    """Main entry. Produces a DeploySpec artifact.

    Reliability strategy:
      - Loads a small, purpose-built persona (`deploy_engineer.md`) so
        the prompt is well under 8K chars and Kilo reliably emits
        small JSON, not a GitHub-strategy script.
      - Lenient parse recovers common Kilo pathologies: fenced blocks,
        prose-wrapped JSON, and 2K-mid-object truncations.
      - If lenient parse still fails, retries Kilo once with a terse
        re-emit prompt (120s timeout) — same shape as the architect
        and data_engineer retry paths.
      - On any failure, returns None and logs a high-severity gap with
        target_persona="deploy_engineer" so the manager routes back.
    """
    persona = "deploy_engineer"
    prompt = build_devops_prompt(site, architecture, gap_context=gap_context)
    json_str, _last_text = invoke_kilo_for_persona(
        persona=persona,
        prompt=prompt,
        context={"migration_id": migration_id, "site_slug": site_slug},
        migration_id=migration_id,
        timeout_s=PERSONA_TIMEOUTS_S[persona],
    )

    data: Optional[dict] = None
    if json_str is not None:
        data = _lenient_parse_deploy_spec(json_str)

    if data is None:
        # Phase 0.6.2 reliability: retry with a terse re-emit prompt.
        # Common cause is truncation to 2K chars; the retry asks for
        # a small (<1500 char) JSON-only re-emit.
        retry_str, _ = invoke_kilo_for_persona(
            persona=persona,
            prompt=_retry_prompt_for_reemit(),
            context={
                "migration_id": migration_id,
                "site_slug": site_slug,
                "mode": "reemit",
            },
            migration_id=migration_id,
            timeout_s=120,
        )
        if retry_str is not None:
            data = _lenient_parse_deploy_spec(retry_str)

    if data is None:
        make_failed_invocation_gap(
            migration_id=migration_id,
            persona=persona,
            description="DeploySpec: Kilo returned no parseable JSON even after retry.",
        )
        return None

    try:
        spec = DeploySpec(**data)
    except Exception as e:
        make_failed_invocation_gap(
            migration_id=migration_id,
            persona=persona,
            description=f"DeploySpec JSON parsed but failed Pydantic validation: {e}",
        )
        return None

    spec.produced_at = spec.produced_at or datetime.now().isoformat()
    spec.produced_by = persona
    save_artifact_to_dir(spec, DEPLOY_SPECS_DIR, migration_id, persona)
    return spec


def load_latest_deploy_spec(migration_id: str = "") -> Optional[DeploySpec]:
    artifact_id = get_latest_artifact_id(DEPLOY_SPECS_DIR)
    if not artifact_id:
        return None
    path = DEPLOY_SPECS_DIR / f"{artifact_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DeploySpec(**data)
    except Exception as e:
        print(f"[WARN] Failed to load DeploySpec {path}: {e}")
        return None
