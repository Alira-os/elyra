"""
backend_architect.py — Phase 1.1 Forge Room persona.

Produces an APIContracts artifact describing the API surface of the
migrated site. Runs after the Data Engineer and DevOps Engineer, and
before the Frontend Architect (which consumes the API contracts).

For most static-site migrations, the expected output is an *empty*
APIContracts (endpoints: [], base_url: null). The persona is built
to make that the easy, default, correct answer — and to recover
gracefully from Kilo output quirks (prose wrappers, schema drift,
truncation) via a strict-format retry and a lenient Pydantic parse.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import (  # noqa: E402
    APIEndpoint,
    APIContracts,
    DataContracts,
    DeploySpec,
    SiteArchitecture,
)
from skills.agentic.forge_common import (  # noqa: E402
    API_CONTRACTS_DIR,
    PERSONA_TIMEOUTS_S,
    _serialize_compact,
    get_latest_artifact_id,
    invoke_kilo_for_persona,
    load_persona_markdown,
    make_failed_invocation_gap,
    save_artifact_to_dir,
)
from skills.agentic.prompt_budget import (  # noqa: E402
    compact_site_architecture,
    compact_site_understanding,
)


_ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}


def _coerce_endpoint(raw):
    if not isinstance(raw, dict):
        return None
    method = raw.get("method")
    if not isinstance(method, str):
        return None
    method = method.upper().strip()
    if method not in _ALLOWED_METHODS:
        return None
    path = raw.get("path")
    if not isinstance(path, str) or not path.startswith("/"):
        return None
    purpose = raw.get("purpose")
    if not isinstance(purpose, str):
        purpose = ""
    request_schema = raw.get("request_schema")
    if request_schema is not None and not isinstance(request_schema, dict):
        request_schema = None
    response_schema = raw.get("response_schema")
    if response_schema is not None and not isinstance(response_schema, dict):
        response_schema = None
    auth_required = raw.get("auth_required", False)
    if isinstance(auth_required, bool):
        pass
    elif isinstance(auth_required, str):
        lowered = auth_required.strip().lower()
        if lowered in ("true", "1", "yes", "y"):
            auth_required = True
        elif lowered in ("false", "0", "no", "n", ""):
            auth_required = False
        else:
            auth_required = bool(auth_required)
    else:
        auth_required = bool(auth_required) if auth_required else False
    notes = raw.get("notes", "")
    if not isinstance(notes, str):
        notes = str(notes)
    try:
        return APIEndpoint(
            method=method, path=path, purpose=purpose,
            request_schema=request_schema, response_schema=response_schema,
            auth_required=auth_required, notes=notes,
        )
    except Exception:
        return None


def lenient_parse_api_contracts(data, *, migration_id="", site_slug=""):
    if not isinstance(data, dict):
        return None
    raw_eps = data.get("endpoints")
    if raw_eps is None:
        endpoints = []
    elif isinstance(raw_eps, list):
        endpoints = []
        for ep in raw_eps:
            coerced = _coerce_endpoint(ep)
            if coerced is not None:
                endpoints.append(coerced)
    else:
        endpoints = []
    def _str_or_none(v):
        if v is None:
            return None
        if isinstance(v, str):
            return v
        return str(v)
    base_url = _str_or_none(data.get("base_url"))
    auth_strategy = _str_or_none(data.get("auth_strategy"))
    business_logic_summary = data.get("business_logic_summary", "")
    if not isinstance(business_logic_summary, str):
        business_logic_summary = str(business_logic_summary)
    reasoning_trace = data.get("reasoning_trace", [])
    if not isinstance(reasoning_trace, list):
        reasoning_trace = []
    else:
        reasoning_trace = [str(x) for x in reasoning_trace if x is not None]
    resolved_migration_id = data.get("migration_id") or migration_id
    resolved_site_slug = data.get("site_slug") or site_slug
    produced_at = data.get("produced_at") or ""
    produced_by = data.get("produced_by") or "backend_architect"
    try:
        return APIContracts(
            migration_id=resolved_migration_id, site_slug=resolved_site_slug,
            base_url=base_url, auth_strategy=auth_strategy,
            endpoints=endpoints, business_logic_summary=business_logic_summary,
            reasoning_trace=reasoning_trace,
            produced_at=produced_at, produced_by=produced_by,
        )
    except Exception:
        if not migration_id:
            return None
        return APIContracts(
            migration_id=migration_id, site_slug=site_slug,
            base_url=base_url, auth_strategy=auth_strategy,
            endpoints=endpoints, business_logic_summary=business_logic_summary,
            reasoning_trace=reasoning_trace,
            produced_at=produced_at, produced_by=produced_by,
        )


def _empty_contracts(migration_id, site_slug):
    return APIContracts(
        migration_id=migration_id, site_slug=site_slug,
        base_url=None, auth_strategy=None, endpoints=[],
        business_logic_summary=(
            "Backend Architect invocation failed or timed out. "
            "Treating as static site with no API surface; the Frontend "
            "Architect will wire any forms to third-party services."
        ),
        reasoning_trace=[
            "Falling back to empty APIContracts because Kilo invocation failed.",
            "This is the canonical answer for static-site migrations.",
        ],
        produced_at=datetime.now().isoformat(),
        produced_by="backend_architect",
    )


def build_backend_prompt(site, architecture, data_contracts=None, deploy_spec=None,
                         *, migration_id="", site_slug="",
                         gap_context=None, strict_format=False):
    persona = load_persona_markdown("backend_architect")
    if not persona:
        persona = (
            "You are the Backend Architect in Elyra Forge Room. "
            "Produce an APIContracts artifact. Most static sites have "
            "no APIs — return endpoints: [] and base_url: null. "
            "Output ONLY valid JSON matching the schema."
        )
    site_json, arch_json, data_json, deploy_json = _serialize_compact(
        compact_site_understanding(site),
        compact_site_architecture(architecture),
        data_contracts.model_dump(mode="json") if data_contracts is not None else {},
        deploy_spec.model_dump(mode="json") if deploy_spec is not None else {},
    )
    schema_json = json.dumps(APIContracts.model_json_schema(), indent=2)
    gap_section = ""
    if gap_context:
        gap_section = f"\n\n## Prioritized Rework Instructions (from Quality Gate)\n{gap_context}\n\nApply these changes first.\n"
    strict_section = ""
    if strict_format:
        strict_section = "\n\n## FORMAT REMINDER (Retry)\nYour previous response was not parseable. This is a strict-format retry.\n\nRespond with EXACTLY one JSON object. The response must:\n- Start with `{` (after optional whitespace)\n- End with `}` (before optional whitespace)\n- Contain NO markdown fences (no ```json ... ```)\n- Contain NO prose, NO commentary, NO explanation before or after\n- Contain NO code-block language tags\n- Be valid JSON parseable by Python json.loads\n\nThe first character of your response must be `{` and the last must be `}`.\n"
    return f"""{persona}

## Identity (copy these into the output)
- migration_id: `{migration_id}`
- site_slug: `{site_slug}`

## Task
Produce an `APIContracts` artifact (Pydantic schema below) describing
the API surface of the migrated site.

**Default for static sites:** return `endpoints: []` and
`base_url: null`. An empty artifact is a valid, complete, correct
artifact for the majority of Elyra migrations. Do NOT invent
endpoints for sites that do not need them.
{gap_section}## Input DeploySpec (from DevOps Engineer)
{deploy_json}

## Input DataContracts (from Data Engineer)
{data_json}

## Input SiteArchitecture (compact view)
{arch_json}

## Input SiteUnderstanding (compact view)
{site_json}

## Output Contract
Output ONLY valid JSON matching the schema below — no markdown, no commentary,
no text outside the JSON object:
{schema_json}
{strict_section}

Begin API design now."""


def design_api_contracts(site, architecture, data_contracts=None, deploy_spec=None,
                         *, migration_id="", site_slug="", gap_context=None):
    persona = "backend_architect"
    timeout_s = PERSONA_TIMEOUTS_S[persona]
    prompt = build_backend_prompt(
        site, architecture, data_contracts, deploy_spec,
        migration_id=migration_id, site_slug=site_slug,
        gap_context=gap_context, strict_format=False,
    )
    json_str, _last_text = invoke_kilo_for_persona(
        persona=persona, prompt=prompt,
        context={"migration_id": migration_id, "site_slug": site_slug},
        migration_id=migration_id, timeout_s=timeout_s,
    )
    contracts = _parse_or_retry(
        json_str=json_str, site=site, architecture=architecture,
        data_contracts=data_contracts, deploy_spec=deploy_spec,
        migration_id=migration_id, site_slug=site_slug,
        gap_context=gap_context, persona=persona, timeout_s=timeout_s,
    )
    if contracts is None:
        make_failed_invocation_gap(
            migration_id=migration_id, persona=persona,
            description=(
                "APIContracts Kilo invocation failed twice; returning "
                "empty APIContracts (canonical static-site answer)."
            ),
            severity="medium",
        )
        contracts = _empty_contracts(migration_id, site_slug)
        save_artifact_to_dir(contracts, API_CONTRACTS_DIR, migration_id, persona)
        return contracts
    contracts.produced_at = contracts.produced_at or datetime.now().isoformat()
    contracts.produced_by = persona
    save_artifact_to_dir(contracts, API_CONTRACTS_DIR, migration_id, persona)
    return contracts


def _parse_or_retry(*, json_str, site, architecture, data_contracts,
                    deploy_spec, migration_id, site_slug, gap_context,
                    persona, timeout_s):
    if json_str is None:
        return _retry_strict(
            site=site, architecture=architecture,
            data_contracts=data_contracts, deploy_spec=deploy_spec,
            migration_id=migration_id, site_slug=site_slug,
            gap_context=gap_context, persona=persona, timeout_s=timeout_s,
        )
    try:
        data = json.loads(json_str)
    except Exception:
        return _retry_strict(
            site=site, architecture=architecture,
            data_contracts=data_contracts, deploy_spec=deploy_spec,
            migration_id=migration_id, site_slug=site_slug,
            gap_context=gap_context, persona=persona, timeout_s=timeout_s,
        )
    contracts = lenient_parse_api_contracts(
        data, migration_id=migration_id, site_slug=site_slug
    )
    if contracts is not None:
        return contracts
    return _retry_strict(
        site=site, architecture=architecture,
        data_contracts=data_contracts, deploy_spec=deploy_spec,
        migration_id=migration_id, site_slug=site_slug,
        gap_context=gap_context, persona=persona, timeout_s=timeout_s,
    )


def _retry_strict(*, site, architecture, data_contracts, deploy_spec,
                  migration_id, site_slug, gap_context, persona, timeout_s):
    strict_prompt = build_backend_prompt(
        site, architecture, data_contracts, deploy_spec,
        migration_id=migration_id, site_slug=site_slug,
        gap_context=gap_context, strict_format=True,
    )
    json_str2, _ = invoke_kilo_for_persona(
        persona=persona, prompt=strict_prompt,
        context={"migration_id": migration_id, "site_slug": site_slug, "retry": True},
        migration_id=migration_id, timeout_s=timeout_s,
    )
    if json_str2 is None:
        return None
    try:
        data = json.loads(json_str2)
    except Exception:
        return None
    return lenient_parse_api_contracts(
        data, migration_id=migration_id, site_slug=site_slug
    )


def load_latest_api_contracts(migration_id=""):
    artifact_id = get_latest_artifact_id(API_CONTRACTS_DIR)
    if not artifact_id:
        return None
    path = API_CONTRACTS_DIR / f"{artifact_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return APIContracts(**data)
    except Exception as e:
        print(f"[WARN] Failed to load APIContracts {path}: {e}")
        return None
