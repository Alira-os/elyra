"""
models/_coercion.py — Central artifact coercion for the planning room.

Phase B goal: a single bad LLM-emitted field must not kill the entire
migration. This module absorbs the inline coercion logic that used to
live in skills/agentic/scraper_agent.py:parse_and_validate, generalizes
it across all personas, and adds a JSON-repair pass so artifacts with
LLM-emitted brace drift (the highlandtreeservices_com.json artifact has
37 stray `}}` sequences) still load.

The pipeline runs in this order, with Pydantic re-validation after each
non-trivial transform:

  1. JSON repair (only when the input is a raw string) — strip stray
     double-braces from the LLM's closing-brace drift.
  2. Page-type enum mapping — unknown values → "other".
  3. Component-type enum mapping — unknown values → "unknown".
  4. Contact-info cleanup — drop null entries, coerce dict → str for
     the geo field.
  5. Navigation-structure cleanup — drop tel: / mailto: page_url nodes,
     strip whitespace, null out non-http(s) page_url.
  6. Page-level image cleanup — drop images with no src.
  7. Final Pydantic validation. If still failing, raise CoercionError.

Mapping reference (also recorded in each function's docstring):

  PageType mapping (unknown → "other"):
    "blog_index"    → "other"  (LLM drift: blog index pages are blogs)
    "form"          → "other"  (LLM drift: forms are a component, not a page type)
    "testimonials"  → "other"  (LLM drift: testimonials are a component, not a page type)
    "service_area"  → "other"  (LLM drift: service areas are content, not a page type)
    (any other unrecognized string) → "other"

  ComponentType mapping (unknown → "unknown"):
    "header"        → "unknown"
    "sidebar"       → "unknown"
    "search_bar"    → "unknown"
    (any other unrecognized string) → "unknown"

  Contact-info mapping:
    value is None         → drop the entry
    value is a dict       → coerce to "k1: v1, k2: v2" (preferred for {lat,lng})
                             or json.dumps(value) (preserves shape otherwise)
    value is non-string   → str(value)

  Navigation-structure mapping:
    page_url starts with "tel:" or "mailto:"  → drop the whole node
    page_url is non-http(s) string            → set to None (keep node)
    url / page_url whitespace                 → stripped
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, ValidationError

from models.site_schemas import (
    ComponentType,
    PageType,
    SiteUnderstanding,
)


class CoercionError(ValueError):
    """Raised when an artifact cannot be coerced into its target schema."""


# --- Module-level constants -------------------------------------------------

# Persona short names → directory names (the dispatch key for coerce_artifact).
# Centralizing it here keeps _invoke_persona honest and makes the routing
# table visible to anyone scanning this module.
ARTIFACT_DISPATCH: Dict[str, str] = {
    "site_understandings": "SiteUnderstanding",
    "site_architectures": "SiteArchitecture",
    "site_recommendations": "ContentRecommendation",
    "site_builds": "BuildManifest",
}

_VALID_PAGE_TYPES = {t.value for t in PageType}
_VALID_COMPONENT_TYPES = {t.value for t in ComponentType}


# --- Step 1: JSON repair ----------------------------------------------------

def repair_json_text(text: str) -> str:
    """Drop stray unmatched closing braces / brackets.

    The LLM occasionally emits an extra `}` or `]` at the end of an
    object/array — most often right after the legitimate close. E.g.
    the highland artifact has 37 such occurrences (e.g.
    `"reviewCount": 21}}}` where the LLM wrote an extra `}` after
    the legitimate triple-close for nested objects).

    The repair tracks a `{` / `[` stack while scanning. When a close
    is encountered whose matching opener is NOT on the stack (i.e. a
    stray), the close is dropped from the output. This preserves
    valid `}}` patterns (e.g. closing two objects back-to-back) while
    removing the genuine drift.

    Returns the repaired string. If the input still does not parse,
    the caller gets a clear error from the subsequent json.loads
    attempt.
    """
    out: list[str] = []
    stack: list[str] = []
    in_string = False
    escape = False
    for c in text:
        if in_string:
            out.append(c)
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
            out.append(c)
            continue
        if c == "{" or c == "[":
            stack.append(c)
            out.append(c)
            continue
        if c == "}" or c == "]":
            if stack and (
                (c == "}" and stack[-1] == "{")
                or (c == "]" and stack[-1] == "[")
            ):
                stack.pop()
                out.append(c)
            # else: stray close — drop silently.
            continue
        out.append(c)
    return "".join(out)


def _coerce_str_to_dict(text: str) -> Dict[str, Any]:
    """Parse a JSON string into a dict, repairing brace drift first."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        repaired = repair_json_text(text)
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError as e:
            preview = text[:200].replace("\n", " ")
            raise CoercionError(
                f"JSON repair failed: {e.msg} at line {e.lineno} col {e.colno}; "
                f"preview: {preview!r}"
            ) from e
    if not isinstance(parsed, dict):
        raise CoercionError(
            f"expected JSON object at top level, got {type(parsed).__name__}"
        )
    return parsed


# --- Step 2-6: per-field transforms -----------------------------------------

def _coerce_page_types(data: Dict[str, Any]) -> None:
    """Unknown page_type values → "other". Mutates in place."""
    for page in data.get("pages", []) or []:
        if not isinstance(page, dict):
            continue
        pt = page.get("page_type")
        if not isinstance(pt, list):
            continue
        cleaned: list = []
        for v in pt:
            if isinstance(v, str) and v in _VALID_PAGE_TYPES:
                cleaned.append(v)
            elif isinstance(v, str):
                # Documented mappings (the highland artifact is the case
                # that produced all of these):
                #   "blog_index"   → "other"
                #   "form"         → "other"
                #   "testimonials" → "other"
                #   "service_area" → "other"
                # Any other unknown string is also → "other".
                cleaned.append(PageType.OTHER.value)
        page["page_type"] = cleaned


def _coerce_component_types(data: Dict[str, Any]) -> None:
    """Unknown component.type → "unknown". Drops components with no type
    at all. Drops assets with null/empty src. Mutates in place."""
    for page in data.get("pages", []) or []:
        if not isinstance(page, dict):
            continue
        comps = page.get("components")
        if not isinstance(comps, list):
            continue
        for comp in comps:
            if not isinstance(comp, dict):
                continue
            t = comp.get("type")
            if not isinstance(t, str):
                # No type at all — drop the component.
                comp["type"] = ComponentType.UNKNOWN.value
            elif t not in _VALID_COMPONENT_TYPES:
                # Documented mappings:
                #   "header"     → "unknown"
                #   "sidebar"    → "unknown"
                #   "search_bar" → "unknown"
                # Any other unknown string → "unknown".
                comp["type"] = ComponentType.UNKNOWN.value
            assets = comp.get("assets")
            if isinstance(assets, list):
                comp["assets"] = [
                    a for a in assets
                    if isinstance(a, dict) and a.get("src")
                ]


def _coerce_contact_info(data: Dict[str, Any]) -> None:
    """Drop null entries; coerce dict → str for `geo`; coerce non-string
    scalars to str. Mutates in place."""
    ci = data.get("contact_info")
    if not isinstance(ci, dict):
        return
    cleaned: Dict[str, str] = {}
    for k, v in ci.items():
        if v is None:
            # Documented mapping: email: null → drop entry.
            continue
        if k == "geo" and isinstance(v, dict):
            lat = v.get("lat")
            lng = v.get("lng")
            if lat is not None and lng is not None:
                # Documented mapping: {lat, lng} → "lat,lng".
                v = f"{lat},{lng}"
            else:
                # Preserve information even when shape is unexpected.
                v = json.dumps(v, sort_keys=True)
        if not isinstance(v, str):
            v = str(v)
        cleaned[k] = v
    data["contact_info"] = cleaned


def _strip_url(u: Any) -> Any:
    if isinstance(u, str):
        return u.strip()
    return u


def _coerce_nav(data: Dict[str, Any]) -> None:
    """Recursively walk navigation_structure. Drop nodes whose `page_url`
    is a tel: / mailto: URL. Strip whitespace from `url` and `page_url`.
    Null out non-http(s) `page_url` so Pydantic HttpUrl accepts None.

    Mutates in place.
    """

    def _walk(node: Any) -> bool:
        """Returns False if the node should be dropped."""
        if not isinstance(node, dict):
            return True
        # Strip whitespace.
        for key in ("url", "page_url"):
            if key in node:
                node[key] = _strip_url(node[key])
        page_url = node.get("page_url")
        if isinstance(page_url, str):
            low = page_url.lower()
            # Documented mapping: tel: / mailto: page_url → drop node.
            if low.startswith("tel:") or low.startswith("mailto:"):
                return False
            if not (low.startswith("http://") or low.startswith("https://")):
                # Non-page URL (e.g. "/about/") — let schema decide.
                # SiteUnderstanding.nav.page_url is Optional[HttpUrl], so
                # a bare path is rejected. Set to None to keep the node.
                node["page_url"] = None
        children = node.get("children")
        if isinstance(children, list):
            kept = [c for c in children if _walk(c)]
            node["children"] = kept
        return True

    nav = data.get("navigation_structure")
    if isinstance(nav, list):
        data["navigation_structure"] = [n for n in nav if _walk(n)]


def _coerce_page_images(data: Dict[str, Any]) -> None:
    """Drop page.images entries with no src. Mutates in place."""
    for page in data.get("pages", []) or []:
        if not isinstance(page, dict):
            continue
        imgs = page.get("images")
        if isinstance(imgs, list):
            page["images"] = [
                i for i in imgs
                if isinstance(i, dict) and i.get("src")
            ]


def _coerce_page_refs(data: Dict[str, Any]) -> None:
    """Fill in the new PageRef fields (slug, file_path) on each page dict.

    Legacy / highland artifacts have rich PageStructure fields but no
    `slug` or `file_path`. The slim SiteUnderstanding requires them. We
    derive `slug` from the URL path and leave `file_path` empty (the
    legacy artifact has no on-disk file to point at).

    Also drops legacy fields that the slim PageRef schema rejects
    (text_content, components, forms, images, links, json_ld, cta_text,
    text_word_count, navigation_from_page, etc.). They remain available
    in the legacy artifact on disk; callers that need them can read the
    legacy file directly.

    Mutates in place.
    """
    legacy_fields = {
        "canonical_url", "components", "forms", "text_content",
        "text_word_count", "seo", "json_ld", "breadcrumb_path",
        "cta_text", "notes", "navigation_from_page", "images", "links",
    }
    for page in data.get("pages", []) or []:
        if not isinstance(page, dict):
            continue
        url = page.get("url") or ""
        # Derive slug from the URL path.
        if not page.get("slug"):
            from urllib.parse import urlparse
            try:
                path = urlparse(str(url)).path
            except Exception:
                path = ""
            slug = path.strip("/").replace("/", "-") or "page"
            page["slug"] = slug
        # file_path is empty for legacy artifacts — the rich data is in
        # the on-disk JSON, not in a per-page file. Callers that need
        # it can `SiteUnderstanding.load_legacy()` the old way.
        page.setdefault("file_path", "")
        # is_dynamic defaults to False.
        page.setdefault("is_dynamic", False)
        # Drop legacy rich fields so Pydantic strict validation passes.
        for f in legacy_fields:
            page.pop(f, None)


# --- Top-level entry points -------------------------------------------------

def coerce_site_understanding(data: Dict[str, Any]) -> SiteUnderstanding:
    """Take a dict (already JSON-decoded) and return a SiteUnderstanding.

    Raises CoercionError if the input cannot be coerced.
    """
    if not isinstance(data, dict):
        raise CoercionError(
            f"coerce_site_understanding expects a dict, got {type(data).__name__}"
        )
    # Run transforms in order. Each step is idempotent and safe to re-run
    # on already-clean data.
    _coerce_contact_info(data)
    _coerce_page_types(data)
    _coerce_component_types(data)
    _coerce_page_images(data)
    _coerce_nav(data)
    _coerce_page_refs(data)
    try:
        return SiteUnderstanding.model_validate(data)
    except ValidationError as e:
        # One last lenient pass: filter to fields the schema knows about.
        # This is the same fallback pattern scraper_agent.py:197 used to
        # do, lifted up so it lives in one place.
        allowed = {k: v for k, v in data.items() if k in SiteUnderstanding.model_fields}
        try:
            return SiteUnderstanding.model_validate(allowed)
        except ValidationError as e2:
            raise CoercionError(
                f"SiteUnderstanding still invalid after coercion: {e2}"
            ) from e2


def coerce_artifact(
    artifact_name: str,
    data: Union[str, Dict[str, Any], BaseModel, Any],
) -> BaseModel:
    """Dispatch on artifact_name to the right schema + coercer.

    artifact_name is the directory name (e.g. "site_understandings"),
    not the persona short name. The dispatch table at the top of this
    module records which schema each name maps to.

    `data` may be:
      - a raw JSON string (with or without brace drift)
      - a dict (already decoded)
      - a Pydantic model (returned after a round-trip to validate the
        schema actually accepts it)

    Raises CoercionError on failure.
    """
    if isinstance(data, BaseModel):
        return data
    if isinstance(data, str):
        data = _coerce_str_to_dict(data)
    if not isinstance(data, dict):
        raise CoercionError(
            f"coerce_artifact({artifact_name!r}) expects dict/str/BaseModel, "
            f"got {type(data).__name__}"
        )

    if artifact_name == "site_understandings":
        return coerce_site_understanding(data)

    # For other personas we don't yet have rich drift handling. Use the
    # lenient "filter to allowed fields" pattern and let Pydantic raise
    # the precise error if it still fails.
    schema_name = ARTIFACT_DISPATCH.get(artifact_name)
    if schema_name is None:
        raise CoercionError(
            f"unknown artifact_name {artifact_name!r}; known: "
            f"{sorted(ARTIFACT_DISPATCH)}"
        )
    schema_cls = _import_schema(schema_name)
    try:
        return schema_cls.model_validate(data)
    except ValidationError as e:
        allowed = {k: v for k, v in data.items() if k in schema_cls.model_fields}
        try:
            return schema_cls.model_validate(allowed)
        except ValidationError as e2:
            raise CoercionError(
                f"{schema_name} still invalid after lenient parse: {e2}"
            ) from e2


def _import_schema(name: str) -> type:
    """Import the Pydantic model class by schema name. Lazy import keeps
    this module's import cost low (avoids pulling in the entire
    site_schemas module for callers that only need JSON repair)."""
    if name == "SiteUnderstanding":
        from models.site_schemas import SiteUnderstanding
        return SiteUnderstanding
    if name == "SiteArchitecture":
        from models.site_schemas import SiteArchitecture
        return SiteArchitecture
    if name == "ContentRecommendation":
        from models.site_schemas import ContentRecommendation
        return ContentRecommendation
    if name == "BuildManifest":
        from models.site_schemas import BuildManifest
        return BuildManifest
    raise CoercionError(f"no schema mapping for {name!r}")


def load_site_understanding_from_path(path: Union[str, Path]) -> SiteUnderstanding:
    """Convenience: read a JSON file from disk and coerce it. This is
    what acceptance tests and ad-hoc loaders should call. It runs the
    JSON-repair pass before the schema coercion."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    return coerce_artifact("site_understandings", text)  # type: ignore[return-value]
