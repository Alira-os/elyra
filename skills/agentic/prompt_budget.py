"""
prompt_budget.py — Per-persona prompt-size budget helpers.

The last E2E run produced a 62,499-char designer prompt. The two biggest
contributors were the SiteUnderstanding JSON (26KB) and the
ContentRecommendation JSON (15.8KB). Kilo hung and we got 17 garbage
output attempts → 17 gap entries.

This module fixes the root cause: each persona's prompt builder now uses
*compact* representations of the upstream artifacts by default, with the
full artifacts kept on disk and addressable by ID. The persona reads the
summary inline and loads full detail from memory/ when it actually needs
it.

Design principle: the prompt should contain exactly the signal the
persona needs to make its decisions. Anything more is noise that
truncates attention and blows the prompt-size budget.

Per-persona budgets are tuned to fit within the 16K ceiling the
`invoke_kilo_safe` guard-rail enforces. When the persona still needs
the full detail (e.g., the builder is the last in the chain and has
to render every page), the builder can opt into a 32K window — but
even then, we strip redundant text and inline schemas.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

# Per-persona default prompt budget. Tune by running a real E2E and
# watching which personas hit the size-refusal guard.
DEFAULT_BUDGETS = {
    "scraper_specialist": 14_000,  # small — only a URL
    "architect_specialist": 14_000,  # site + schema
    "marketing_specialist": 14_000,  # site + arch
    "ui_designer": 14_000,  # site + rec (bigger inputs)
    "builder": 30_000,  # site + arch + rec + visual — needs more
    "deploy_specialist": 12_000,  # mostly metadata
}


# --- Compaction helpers ---------------------------------------------------

# Stopwords stripped when summarizing free-text fields.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "of", "to",
    "for", "in", "on", "at", "by", "with", "from", "as", "is", "are",
    "was", "were", "be", "been", "being", "this", "that", "these",
    "those", "it", "its", "we", "you", "they", "them", "their",
    "our", "your", "i", "me", "my", "he", "she", "his", "her", "do",
    "does", "did", "has", "have", "had", "will", "would", "should",
    "could", "may", "might", "can", "shall", "not", "no", "so",
    "up", "out", "about", "into", "over", "after", "before", "than",
    "between", "while", "also", "just", "very", "more", "most",
    "some", "any", "all", "each", "every", "such", "only",
}


def _truncate_words(text: str, max_words: int) -> str:
    """Keep the first max_words of meaningful text, dropping stopwords."""
    if not text:
        return ""
    words = re.findall(r"\b\w+\b", text)
    if len(words) <= max_words:
        return text
    # Keep first max_words — naive but adequate for prompts.
    return " ".join(words[:max_words]) + " ..."


def _compact_dict(
    obj: Any,
    keep_keys: set[str],
    text_max_words: int = 30,
) -> dict:
    """Build a dict with only the keep_keys; long text values are truncated."""
    if not isinstance(obj, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in obj.items():
        if k in keep_keys:
            if isinstance(v, str) and len(v) > text_max_words * 6:
                out[k] = _truncate_words(v, text_max_words)
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                # Compact list of dicts → keep first 3 only
                out[k] = v[:3]
            else:
                out[k] = v
    return out


# --- Per-artifact compact views -------------------------------------------

def compact_site_understanding(site: Any) -> dict:
    """Reduced SiteUnderstanding for downstream persona prompts.

    Keeps: url, site_name, platform + confidence, total_pages_discovered,
    page count, top-level page structure (first 3 pages with title + url),
    nav structure (first 8 items), and global_assets.

    Phase 0.6.1: returns a dict that is fully JSON-serializable
    (Pydantic HttpUrl and datetime fields are converted to strings) so
    callers can `json.dumps()` the result without errors.
    """
    if site is None:
        return {}
    if hasattr(site, "model_dump"):
        # mode="json" converts HttpUrl, datetime, etc. to JSON-safe types.
        data = site.model_dump(mode="json")
    elif isinstance(site, dict):
        data = site
    else:
        return {}

    pages = data.get("pages", []) or []
    page_summaries = [
        {
            "url": p.get("url"),
            "title": p.get("title"),
            "page_type": p.get("page_type"),
            "text_word_count": p.get("text_word_count"),
        }
        for p in pages[:3]
    ]
    nav = data.get("navigation_structure", []) or []
    nav_summaries = [
        {"label": n.get("label"), "url": n.get("url")}
        for n in nav[:8]
    ]
    global_assets = data.get("global_assets", {}) or {}
    # global_assets may have arbitrary keys; cap to a small repr.
    assets_compact = {k: str(v)[:80] for k, v in list(global_assets.items())[:6]}

    return {
        "url": data.get("url"),
        "site_name": data.get("site_name"),
        "platform": data.get("platform"),
        "platform_confidence": data.get("platform_confidence"),
        "total_pages_discovered": data.get("total_pages_discovered"),
        "estimated_fidelity": data.get("estimated_fidelity"),
        "pages": page_summaries,
        "pages_truncated": max(0, len(pages) - 3),
        "navigation_structure": nav_summaries,
        "nav_truncated": max(0, len(nav) - 8),
        "global_assets": assets_compact,
    }


def compact_site_architecture(arch: Any) -> dict:
    """Reduced SiteArchitecture. Keeps stack + page count + first 3 pages."""
    if arch is None:
        return {}
    if hasattr(arch, "model_dump"):
        data = arch.model_dump(mode="json")
    elif isinstance(arch, dict):
        data = arch
    else:
        return {}

    pages = data.get("pages", []) or []
    page_summaries = [
        {
            "path": p.get("path") or p.get("url"),
            "title": p.get("title"),
            "page_type": p.get("page_type"),
        }
        for p in pages[:3]
    ]
    return {
        "target_stack": data.get("target_stack"),
        "routing_strategy": data.get("routing_strategy"),
        "total_pages": len(pages),
        "pages": page_summaries,
        "pages_truncated": max(0, len(pages) - 3),
        "components_count": len(data.get("components", []) or []),
    }


def compact_content_recommendation(rec: Any, keep_brand: bool = True) -> dict:
    """Reduced ContentRecommendation. Keeps overall strategy, chosen variant
    headline/tagline, and (optionally) the full BrandSpec (which the
    designer and builder need)."""
    if rec is None:
        return {}
    if hasattr(rec, "model_dump"):
        data = rec.model_dump(mode="json")
    elif isinstance(rec, dict):
        data = rec
    else:
        return {}

    out: dict[str, Any] = {
        "site_name": data.get("site_name"),
        "chosen_variant": data.get("chosen_variant"),
        "final_rationale": data.get("final_rationale"),
        "overall_content_strategy": data.get("overall_content_strategy"),
    }
    if keep_brand and "brand_spec" in data and data["brand_spec"]:
        out["brand_spec"] = data["brand_spec"]
    # Drop page_strategies + content_recommendations — they're huge and
    # mostly redundant with BrandSpec + overall strategy. The builder
    # can re-load the full ContentRecommendation from memory/rec_id if it
    # needs the per-page detail.
    return out


def compact_visual_direction(vd: Any) -> dict:
    """Reduced VisualDirection. Keeps primary_change, rationale, deltas."""
    if vd is None:
        return {}
    if hasattr(vd, "model_dump"):
        data = vd.model_dump(mode="json")
    elif isinstance(vd, dict):
        data = vd
    else:
        return {}
    return {
        "primary_change": data.get("primary_change"),
        "rationale": data.get("rationale"),
        "stitch_status": data.get("stitch_status"),
        "color_delta": data.get("color_delta"),
        "typography_delta": data.get("typography_delta"),
        "motion_delta": data.get("motion_delta"),
        "impacted_components": (data.get("impacted_components") or [])[:8],
        "impacted_pages": (data.get("impacted_pages") or [])[:5],
    }


# --- Estimators ----------------------------------------------------------

def approx_chars(*objs: Any) -> int:
    """Rough char count for a set of objects, suitable for budget checks."""
    total = 0
    for o in objs:
        if o is None:
            continue
        if isinstance(o, str):
            total += len(o)
        elif hasattr(o, "model_dump_json"):
            total += len(o.model_dump_json())
        elif isinstance(o, dict):
            total += len(json.dumps(o, default=str))
    return total
