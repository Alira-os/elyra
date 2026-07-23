"""
artifacts.py — Unified artifact loaders for the Elyra blackboard.

Phase 1 of PLAN.md removed the per-persona ``*_agent.py`` loaders. Downstream
code (the Manager, root CLIs, tests) now reads planning + Forge artifacts
through the helpers in this module. Each loader is a thin wrapper over
``models.site_schemas`` + the ``memory/_coercion`` module:

  - load_site_understanding(site_id) -> Optional[SiteUnderstanding]
  - load_site_architecture(arch_id) -> Optional[SiteArchitecture]
  - load_content_recommendation(rec_id) -> Optional[ContentRecommendation]
  - load_visual_direction(site_slug) -> Optional[VisualDirection]
  - load_seo_strategy(seo_id) -> Optional[SeoStrategy]
  - load_geo_strategy(geo_id) -> Optional[GeoStrategy]
  - load_geo_build(geo_build_id) -> Optional[GeoBuildArtifacts]

All loaders are tolerant:
  - If the artifact lives at ``memory/<dir>/<id>.json``, read it.
  - If only the directory layout exists (the new recon-directory shape
    with ``site.json`` + ``sitemap.md`` + ``pages/``), build the slim
    artifact via the schema's ``from_directory`` constructor.
  - On any failure, log a brief error and return ``None``.

The on-disk directory layout per artifact type is documented in
``PLAN.md`` and the canonical :mod:`models.site_schemas` module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


SITE_UNDERSTANDINGS_DIR = Path("memory/site_understandings")
SITE_ARCHITECTURES_DIR = Path("memory/site_architectures")
RECOMMENDATIONS_DIR = Path("memory/site_recommendations")
VISUAL_SPECS_DIR = Path("memory/visual_specs")
SEO_STRATEGIES_DIR = Path("memory/seo_strategies")
GEO_STRATEGIES_DIR = Path("memory/geo_strategies")
GEO_BUILDS_DIR = Path("memory/geo_builds")


def _read_json(path: Path) -> Optional[dict]:
    """Read a JSON file safely. Returns None on any I/O or parse failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_pydantic(model_cls, data: dict, *, label: str = ""):
    """Instantiate a Pydantic model from a dict, returning None on failure."""
    try:
        return model_cls(**data)
    except Exception as e:
        if label:
            print(f"[ERROR] Failed to construct {label}: {e}")
        return None


# ---------------------------------------------------------------------------
# SiteUnderstanding — supports both legacy single-file + new recon-dir layouts
# ---------------------------------------------------------------------------


def load_site_understanding(site_id: str):
    """Load a saved SiteUnderstanding.

    Phase 2: prefer the new recon-directory shape (site.json + sitemap.md
    + pages/) at ``memory/site_understandings/<id>/``. Fall back to the
    legacy single-JSON artifact for backward compat with on-disk data and
    test fixtures that pre-date the simplification. The coercion module
    fills in ``slug`` / ``file_path`` for legacy inputs.
    """
    from models.site_schemas import SiteUnderstanding

    if not site_id:
        return None

    site_dir = SITE_UNDERSTANDINGS_DIR / site_id
    if site_dir.is_dir() and (site_dir / "site.json").exists():
        try:
            return SiteUnderstanding.from_directory(site_dir)
        except Exception as e:
            print(f"[ERROR] Failed to load SiteUnderstanding from {site_dir}: {e}")
            return None

    site_path = SITE_UNDERSTANDINGS_DIR / f"{site_id}.json"
    if not site_path.exists():
        site_path = Path(site_id)
    try:
        from models._coercion import load_site_understanding_from_path
        return load_site_understanding_from_path(site_path)
    except Exception as e:
        print(f"[ERROR] Failed to load SiteUnderstanding: {e}")
        return None


# ---------------------------------------------------------------------------
# SiteArchitecture
# ---------------------------------------------------------------------------


def load_site_architecture(arch_id: str):
    """Load a saved SiteArchitecture from memory/site_architectures/."""
    from models.site_schemas import SiteArchitecture

    if not arch_id:
        return None
    arch_path = SITE_ARCHITECTURES_DIR / f"{arch_id}.json"
    if not arch_path.exists():
        arch_path = Path(arch_id)
    data = _read_json(arch_path)
    if data is None:
        return None
    return _load_pydantic(SiteArchitecture, data, label="SiteArchitecture")


# ---------------------------------------------------------------------------
# ContentRecommendation
# ---------------------------------------------------------------------------


def load_content_recommendation(rec_id: str):
    """Load a saved ContentRecommendation from memory/site_recommendations/."""
    from models.site_schemas import ContentRecommendation

    if not rec_id:
        return None
    rec_path = RECOMMENDATIONS_DIR / f"{rec_id}.json"
    if not rec_path.exists():
        rec_path = Path(rec_id)
    data = _read_json(rec_path)
    if data is None:
        return None
    return _load_pydantic(ContentRecommendation, data, label="ContentRecommendation")


# ---------------------------------------------------------------------------
# VisualDirection — per-site_slug subdir
# ---------------------------------------------------------------------------


def load_visual_direction(site_slug: str):
    """Load the latest VisualDirection for a given site_slug.

    Used by the Phase 1.1 frontend_architect persona which reads its
    upstream artifacts from the blackboard. Returns the most recent
    VisualDirection JSON under ``memory/visual_specs/<site_slug>/``.
    """
    from models.site_schemas import VisualDirection

    if not site_slug:
        return None
    spec_dir = VISUAL_SPECS_DIR / site_slug
    if not spec_dir.exists():
        return None
    json_files = sorted(spec_dir.glob("*.json"), reverse=True)
    for json_file in json_files:
        data = _read_json(json_file)
        if data is None:
            continue
        try:
            vd = VisualDirection(**data)
            if vd.primary_change or vd.rationale:
                return vd
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Discoverability strategies (Phase E)
# ---------------------------------------------------------------------------


def load_seo_strategy(seo_id: str):
    """Load a saved SeoStrategy from memory/seo_strategies/."""
    from models.site_schemas import SeoStrategy

    if not seo_id:
        return None
    path = SEO_STRATEGIES_DIR / f"{seo_id}.json"
    if not path.exists():
        path = Path(seo_id)
    data = _read_json(path)
    if data is None:
        return None
    return _load_pydantic(SeoStrategy, data, label="SeoStrategy")


def load_geo_strategy(geo_id: str):
    """Load a saved GeoStrategy from memory/geo_strategies/."""
    from models.site_schemas import GeoStrategy

    if not geo_id:
        return None
    path = GEO_STRATEGIES_DIR / f"{geo_id}.json"
    if not path.exists():
        path = Path(geo_id)
    data = _read_json(path)
    if data is None:
        return None
    return _load_pydantic(GeoStrategy, data, label="GeoStrategy")


def load_geo_build(geo_build_id: str):
    """Load a saved GeoBuildArtifacts from memory/geo_builds/."""
    from models.site_schemas import GeoBuildArtifacts

    if not geo_build_id:
        return None
    path = GEO_BUILDS_DIR / f"{geo_build_id}.json"
    if not path.exists():
        path = Path(geo_build_id)
    data = _read_json(path)
    if data is None:
        return None
    return _load_pydantic(GeoBuildArtifacts, data, label="GeoBuildArtifacts")


# ---------------------------------------------------------------------------
# GEO file writing (Phase E: geo_specialist forge pass)
# ---------------------------------------------------------------------------


def write_geo_files(artifacts, site_dir: Path) -> list:
    """Write llms.txt + robots.txt (merge) + sitemap.xml (merge) and inject
    JSON-LD blocks into the relevant page files.

    Returns a list of absolute paths written. This is the persistence
    companion to GeoBuildArtifacts — it was previously a private helper
    in ``skills/agentic/geo_agent.py``; moving it here keeps the orchestrator
    free of geo-specific file-writing logic.

    The function also stamps ``artifacts.content_sha256`` with the sha256
    of each file written (relative path under ``site_dir``).
    """
    import hashlib

    written: list = []
    site_dir.mkdir(parents=True, exist_ok=True)

    # 1. llms.txt — overwrite (this persona owns it).
    if getattr(artifacts, "llms_txt", None):
        llms_path = site_dir / "llms.txt"
        llms_path.write_text(artifacts.llms_txt, encoding="utf-8")
        written.append(str(llms_path.resolve()))

    # 2. robots.txt — merge AI stanza. If file doesn't exist, create it.
    if getattr(artifacts, "robots_txt_ai_stanza", None):
        robots_path = site_dir / "robots.txt"
        existing = ""
        if robots_path.exists():
            try:
                existing = robots_path.read_text(encoding="utf-8")
            except Exception:
                existing = ""
        merged = (
            existing.rstrip()
            + "\n\n# AI crawlers (geo_specialist forge pass)\n"
            + artifacts.robots_txt_ai_stanza.rstrip()
            + "\n"
        )
        robots_path.write_text(merged, encoding="utf-8")
        written.append(str(robots_path.resolve()))

    # 3. sitemap.xml — append <url> entries inside <urlset>.
    sitemap_extras = list(getattr(artifacts, "sitemap_xml_extras", []) or [])
    if sitemap_extras:
        sitemap_path = site_dir / "sitemap.xml"
        existing = ""
        if sitemap_path.exists():
            try:
                existing = sitemap_path.read_text(encoding="utf-8")
            except Exception:
                existing = ""
        if "<urlset" in existing and "</urlset>" in existing:
            insertion = "\n" + "\n".join(
                f'  <url><loc>{e.get("loc", "")}</loc>'
                + (f'<lastmod>{e.get("lastmod")}</lastmod>' if e.get("lastmod") else "")
                + (
                    f'<priority>{e.get("priority")}</priority>'
                    if e.get("priority") is not None
                    else ""
                )
                + "</url>"
                for e in sitemap_extras
                if isinstance(e, dict)
            ) + "\n"
            new_sitemap = existing.replace("</urlset>", insertion + "</urlset>")
            sitemap_path.write_text(new_sitemap, encoding="utf-8")
            written.append(str(sitemap_path.resolve()))

    # 4. JSON-LD blocks — inject into page files.
    blocks_by_route = dict(getattr(artifacts, "json_ld_blocks_by_route", {}) or {})
    for route, blocks in blocks_by_route.items():
        if not blocks:
            continue
        if route == "/" or not route.strip("/"):
            page_path = site_dir / "index.html"
        else:
            page_path = site_dir / route.strip("/") / "index.html"
        if not page_path.exists():
            page_path.parent.mkdir(parents=True, exist_ok=True)
            page_path.write_text(
                "<!DOCTYPE html><html><head></head><body></body></html>",
                encoding="utf-8",
            )
        try:
            content = page_path.read_text(encoding="utf-8")
        except Exception:
            content = "<!DOCTYPE html><html><head></head><body></body></html>"
        injection = ""
        for block in blocks:
            if isinstance(block, dict):
                injection += (
                    f'\n<script type="application/ld+json">\n'
                    f"{json.dumps(block, indent=2)}\n</script>\n"
                )
        if injection and "</head>" in content:
            content = content.replace("</head>", injection + "</head>", 1)
            page_path.write_text(content, encoding="utf-8")
            written.append(str(page_path.resolve()))

    # Compute sha256 for every file written.
    artifacts.content_sha256 = {}
    for path_str in written:
        p = Path(path_str)
        try:
            rel = str(p.relative_to(site_dir))
        except ValueError:
            rel = p.name
        try:
            data = p.read_bytes()
            artifacts.content_sha256[rel] = hashlib.sha256(data).hexdigest()
        except Exception:
            artifacts.content_sha256[rel] = ""

    return written


__all__ = [
    "SITE_UNDERSTANDINGS_DIR",
    "SITE_ARCHITECTURES_DIR",
    "RECOMMENDATIONS_DIR",
    "VISUAL_SPECS_DIR",
    "SEO_STRATEGIES_DIR",
    "GEO_STRATEGIES_DIR",
    "GEO_BUILDS_DIR",
    "load_site_understanding",
    "load_site_architecture",
    "load_content_recommendation",
    "load_visual_direction",
    "load_seo_strategy",
    "load_geo_strategy",
    "load_geo_build",
    "write_geo_files",
]