"""
data_engineer.py — Phase 1.1 Forge Room persona.

Produces a DataContracts artifact (Pydantic-validated) describing the
data layer of the migrated site. Runs early in the Forge Room —
after DevOps (which provides the DeploySpec constraints) and before
the Backend / Frontend specialists (which consume the data contracts).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Path setup: see forge_common.py for rationale.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.site_schemas import (  # noqa: E402
    DataContract,
    DataContracts,
    SiteArchitecture,
    DeploySpec,
)

from skills.agentic.forge_common import (  # noqa: E402
    DATA_CONTRACTS_DIR,
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


DATA_CONTRACTS_EXAMPLE = """{
  "migration_id": "<filled-in by orchestrator>",
  "site_slug": "<filled-in by orchestrator>",
  "contracts": [
    {
      "name": "BlogPost",
      "kind": "static",
      "fields": [
        {"name": "title",       "type": "string",   "required": "true",  "notes": ""},
        {"name": "body",        "type": "markdown", "required": "true",  "notes": ""},
        {"name": "published_at","type": "date",     "required": "true",  "notes": ""}
      ],
      "relationships": [],
      "cms_sync": null,
      "notes": "One .md file per post under content/blog/<slug>.md"
    }
  ],
  "data_architecture_summary": "Static site, all content as Markdown files under content/.",
  "reasoning_trace": ["..."],
  "produced_at": "",
  "produced_by": "data_engineer"
}"""


def build_data_engineer_prompt(
    site,
    architecture: SiteArchitecture,
    deploy_spec: Optional[DeploySpec] = None,
    *,
    gap_context: Optional[str] = None,
) -> str:
    """Build the data engineer's prompt.

    Inputs (in order of importance):
      - DeploySpec (if available) — constrains platform / scaling / security
      - SiteUnderstanding — source platform signals
      - SiteArchitecture — the data-model sketch (pages, components, nav)

    The persona markdown is the system prompt; the artifact info
    above is the task. Both are passed in compact form.
    """
    persona = load_persona_markdown("data_engineer")

    site_json, arch_json = _serialize_compact(
        compact_site_understanding(site),
        compact_site_architecture(architecture),
    )

    if deploy_spec is not None:
        deploy_block = (
            "## Input DeploySpec (from DevOps Engineer — early constraint)\n"
            + json.dumps(deploy_spec.model_dump(mode="json"), indent=2)
        )
    else:
        deploy_block = (
            "## Input DeploySpec (from DevOps Engineer — early constraint)\n"
            "NOT YET AVAILABLE — DevOps has not run yet. Assume a conservative "
            "default: a static-hosting-style target (every contract `kind="
            "\"static\"`). If the SiteUnderstanding clearly shows a CMS-driven "
            "or e-commerce source, it is acceptable to use `kind=\"cms\"` for "
            "those entities, but do NOT introduce a `database` contract."
        )

    gap_section = ""
    if gap_context:
        gap_section = f"""

## Prioritized Rework Instructions (from Quality Gate)
{gap_context}

Apply these changes first. The orchestrator will route you back here if the Integration Coordinator finds an unresolved cross-layer issue.
"""

    return f"""{persona}

## Task
Produce a `DataContracts` artifact describing the data layer of the
migrated site. Output ONLY valid JSON — no markdown fences, no
commentary, no text outside the JSON object.
{gap_section}

{deploy_block}

## Input SiteUnderstanding (compact view)
{site_json}

## Input SiteArchitecture (compact view)
{arch_json}

## Output Contract — exact required shape
Return ONE JSON object with these top-level keys (in this order):
- `migration_id` (string) — set to the migration_id you were given in context
- `site_slug` (string) — set to the site_slug you were given in context
- `contracts` (array of contract objects, may be empty)
- `data_architecture_summary` (string, 1-2 sentences)
- `reasoning_trace` (array of short strings, may be empty)
- `produced_at` (string ISO-8601 timestamp, may be empty)
- `produced_by` (string — set to "data_engineer")

Each contract object has:
- `name` (PascalCase, e.g. "BlogPost")
- `kind` — exactly one of: "static", "cms", "database", "file"
- `fields` (array of {{name, type, required, notes}} dicts)
- `relationships` (array of other contract names, may be empty)
- `cms_sync` (string or null)
- `notes` (string, may be empty)

CRITICAL field-shape rules:
- `required` on each field is the STRING `"true"` or `"false"` — NOT a boolean.
  This is the most common validation error. Use quotes.
- `type` on each field is a free-form string ("string", "markdown",
  "date", "number", "url", "image", etc.).
- `name` on each field is lowercase, snake_case, no spaces.

## Minimal example (not the answer — illustrative shape only)
{DATA_CONTRACTS_EXAMPLE}

Begin data modeling now."""


def _lenient_load_data_contracts(data: dict) -> "DataContracts":
    """Drop unknown top-level + per-contract keys before validation.

    Kilo often appends helpful-but-extra fields (e.g. `id`, `timestamp`,
    `confidence`, `_meta`). The Pydantic schema is strict by default
    (no `extra='allow'` on DataContracts) so those extras cause a
    ValidationError. Strip them out so the artifact is recoverable.

    Also normalises the per-field `required` value to the string
    `"true"` / `"false"` — the schema declares Dict[str, str] but Kilo
    frequently emits a real Python boolean, which then fails str
    coercion. This is the single most common validation error.
    """
    allowed_top = set(DataContracts.model_fields.keys())
    clean = {k: v for k, v in data.items() if k in allowed_top}

    contracts_in = clean.get("contracts") or []
    clean_contracts = []
    for c in contracts_in:
        if not isinstance(c, dict):
            continue
        cc = {k: v for k, v in c.items() if k in DataContract.model_fields}
        fixed_fields = []
        for f in cc.get("fields") or []:
            if not isinstance(f, dict):
                continue
            f = {k: v for k, v in f.items() if k in {"name", "type", "required", "notes"}}
            req = f.get("required")
            if isinstance(req, bool):
                f["required"] = "true" if req else "false"
            elif req is None:
                f["required"] = "false"
            elif not isinstance(req, str):
                f["required"] = str(req)
            f.setdefault("required", "false")
            f.setdefault("notes", "")
            fixed_fields.append(f)
        cc["fields"] = fixed_fields
        clean_contracts.append(cc)
    clean["contracts"] = clean_contracts
    return DataContracts(**clean)


def _retry_prompt_for_reemit() -> str:
    """Short, terse re-emit prompt used after a first extraction failure.

    The Kilo output was either truncated or prose. We ask for a clean
    JSON-only re-emit. No markdown fences, no prose, no schema dump —
    we already have the JSON shape in the original prompt; we just need
    the model to produce it again, smaller.
    """
    return (
        "Your previous response was not parseable JSON. "
        "Re-emit the DataContracts as a single JSON object "
        "(no ``` fence, no prose, no comments). "
        'Example: {"migration_id": "m1", "site_slug": "x", '
        '"contracts": [], "data_architecture_summary": "static", '
        '"reasoning_trace": [], "produced_at": "", "produced_by": "data_engineer"} '
        "Keep it under 1500 chars. Use snake_case for field names."
    )


def design_data_contracts(
    site,
    architecture: SiteArchitecture,
    deploy_spec: Optional[DeploySpec] = None,
    *,
    migration_id: str = "",
    site_slug: str = "",
    gap_context: Optional[str] = None,
) -> Optional[DataContracts]:
    """Main entry point. Builds the prompt, calls Kilo, validates the
    response against DataContracts, persists to disk, returns the artifact.

    Reliability behavior:
      - First Kilo call uses the full persona prompt.
      - On extraction failure (json_str is None) a single retry is issued
        with a terse ~600-char re-emit prompt (120s timeout).
      - On validation failure, a single "repair" call is issued with a
        field-shape fix prompt (separate concern).
      - On any failure, returns None and logs a high-severity gap with
        target_persona="data_engineer" so the manager routes back here.
    """
    persona = "data_engineer"
    prompt = build_data_engineer_prompt(
        site, architecture, deploy_spec, gap_context=gap_context
    )
    json_str, _last_text = invoke_kilo_for_persona(
        persona=persona,
        prompt=prompt,
        context={"migration_id": migration_id, "site_slug": site_slug},
        migration_id=migration_id,
        timeout_s=PERSONA_TIMEOUTS_S[persona],
    )
    if json_str is None:
        # Phase 0.6.2 reliability: retry with a terse re-emit prompt.
        # Common cause is truncation to 2K chars; the retry asks for
        # a small (<1500 char) JSON-only re-emit.
        retry_prompt = _retry_prompt_for_reemit()
        retry_str, _ = invoke_kilo_for_persona(
            persona=persona,
            prompt=retry_prompt,
            context={
                "migration_id": migration_id,
                "site_slug": site_slug,
                "mode": "reemit",
            },
            migration_id=migration_id,
            timeout_s=120,
        )
        if retry_str is None:
            make_failed_invocation_gap(
                migration_id=migration_id,
                persona=persona,
                description=(
                    "DataContracts: Kilo returned no parseable JSON "
                    "even after re-emit retry."
                ),
            )
            return None
        json_str = retry_str

    try:
        data = json.loads(json_str)
        contracts = _lenient_load_data_contracts(data)
    except Exception as e:
        # One repair attempt: feed the validation error back to Kilo
        # with a tight "fix only these field shapes" prompt, then
        # re-parse leniently.
        repair_prompt = (
            "The JSON you produced failed Pydantic validation with this error:\n\n"
            f"  {e}\n\n"
            "Repair the JSON so it matches the required shape. Rules:\n"
            "- `required` on each field must be the STRING \"true\" or \"false\" "
            "(not a boolean, not null).\n"
            "- Drop any top-level keys that are not in the schema "
            "(migration_id, site_slug, contracts, data_architecture_summary, "
            "reasoning_trace, produced_at, produced_by).\n"
            "- Drop any per-contract keys that are not in the schema "
            "(name, kind, fields, relationships, cms_sync, notes).\n"
            "- Inside each `fields` entry keep only name, type, required, notes.\n"
            "- Return ONLY the repaired JSON object, no commentary.\n"
        )
        repaired_str, _ = invoke_kilo_for_persona(
            persona=persona,
            prompt=repair_prompt,
            context={"migration_id": migration_id, "site_slug": site_slug,
                     "repair_of": "data_engineer"},
            migration_id=migration_id,
            timeout_s=PERSONA_TIMEOUTS_S[persona],
        )
        if repaired_str is not None:
            try:
                data = json.loads(repaired_str)
                contracts = _lenient_load_data_contracts(data)
            except Exception as e2:
                make_failed_invocation_gap(
                    migration_id=migration_id,
                    persona=persona,
                    description=(
                        f"DataContracts JSON parsed but failed Pydantic validation "
                        f"on first attempt ({e}); repair attempt also failed ({e2})."
                    ),
                )
                return None
        else:
            make_failed_invocation_gap(
                migration_id=migration_id,
                persona=persona,
                description=(
                    f"DataContracts JSON parsed but failed Pydantic validation: {e}. "
                    f"Repair call did not return JSON."
                ),
            )
            return None

    # Stamp produced_at and produced_by since the LLM may forget.
    contracts.produced_at = contracts.produced_at or datetime.now().isoformat()
    contracts.produced_by = persona
    if not contracts.migration_id:
        contracts.migration_id = migration_id
    if not contracts.site_slug:
        contracts.site_slug = site_slug

    save_artifact_to_dir(contracts, DATA_CONTRACTS_DIR, migration_id, persona)
    return contracts


def load_latest_data_contracts(migration_id: str = "") -> Optional[DataContracts]:
    """Load the most recent DataContracts artifact (or the one matching
    `migration_id` if provided). For now we just return the latest;
    per-migration scoping is a follow-up."""
    artifact_id = get_latest_artifact_id(DATA_CONTRACTS_DIR)
    if not artifact_id:
        return None
    path = DATA_CONTRACTS_DIR / f"{artifact_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DataContracts(**data)
    except Exception as e:
        print(f"[WARN] Failed to load DataContracts {path}: {e}")
        return None
