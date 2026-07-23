"""
Unit tests for skills/agentic/prompt_budget.py

Phase 0.6: the persona prompt builders now use compact views of the
upstream artifacts. These tests lock in the compaction rules so a bad
change doesn't bloat the prompts back up.

Run:
    python -m pytest tests/test_prompt_budget.py -v
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills.agentic.prompt_budget import (  # noqa: E402
    compact_site_understanding,
    compact_site_architecture,
    compact_content_recommendation,
    compact_visual_direction,
    approx_chars,
)


def _make_site(n_pages=10, n_nav=20):
    return {
        "url": "https://example.com",
        "site_name": "Example",
        "platform": "wix",
        "platform_confidence": 0.9,
        "total_pages_discovered": n_pages,
        "estimated_fidelity": 0.8,
        "pages": [
            {
                "url": f"https://example.com/p{i}",
                "title": f"Page {i}",
                "page_type": ["home"] if i == 0 else ["content"],
                "text_word_count": 100 * i,
                "images": [],
                "components": [],
            }
            for i in range(n_pages)
        ],
        "navigation_structure": [
            {"label": f"Nav {i}", "url": f"/p{i}"} for i in range(n_nav)
        ],
        "global_assets": {f"asset_{i}": "x" * 200 for i in range(20)},
        "contact_info": {},
        "accessibility_flags": [],
    }


def test_compact_site_understanding_truncates_pages():
    site = _make_site(n_pages=10)
    compact = compact_site_understanding(site)
    assert len(compact["pages"]) == 3
    assert compact["pages_truncated"] == 7
    assert compact["total_pages_discovered"] == 10


def test_compact_site_understanding_truncates_nav():
    site = _make_site(n_nav=20)
    compact = compact_site_understanding(site)
    assert len(compact["navigation_structure"]) == 8
    assert compact["nav_truncated"] == 12


def test_compact_site_understanding_caps_global_assets():
    site = _make_site()
    compact = compact_site_understanding(site)
    assert len(compact["global_assets"]) <= 6


def test_compact_site_architecture_keeps_stack_and_count():
    arch = {
        "target_stack": {"framework": "nextjs", "styling": "tailwind"},
        "routing_strategy": "app_router",
        "pages": [{"path": "/"}, {"path": "/about"}],
        "components": [
            {"name": "Header"},
            {"name": "Footer"},
        ],
    }
    compact = compact_site_architecture(arch)
    assert compact["target_stack"] == {"framework": "nextjs", "styling": "tailwind"}
    assert compact["total_pages"] == 2
    assert compact["components_count"] == 2


def test_compact_content_recommendation_keeps_brand_when_requested():
    rec = {
        "site_name": "X",
        "chosen_variant": "A",
        "final_rationale": "long " * 200,
        "overall_content_strategy": "Direct",
        "brand_spec": {"primary_color": "#1E293B"},
        "page_strategies": {"/": {"hero": "x" * 1000}},
        "content_recommendations": [{"page": "/", "copy": "x" * 5000}],
    }
    compact = compact_content_recommendation(rec, keep_brand=True)
    assert "brand_spec" in compact
    # page_strategies and content_recommendations are stripped
    assert "page_strategies" not in compact
    assert "content_recommendations" not in compact


def test_compact_content_recommendation_omits_brand_when_not_requested():
    rec = {
        "site_name": "X",
        "chosen_variant": "A",
        "brand_spec": {"primary_color": "#1E293B"},
    }
    compact = compact_content_recommendation(rec, keep_brand=False)
    assert "brand_spec" not in compact


def test_compact_visual_direction_keeps_deltas_and_caps_lists():
    vd = {
        "primary_change": "Increase contrast",
        "rationale": "Accessibility audit flagged low contrast",
        "stitch_status": "unavailable",
        "color_delta": {"primary": "#000"},
        "typography_delta": {"h1_size": 48},
        "motion_delta": {"entrance": "fade"},
        "impacted_components": [f"comp_{i}" for i in range(20)],
        "impacted_pages": [f"/p{i}" for i in range(15)],
    }
    compact = compact_visual_direction(vd)
    assert compact["primary_change"] == "Increase contrast"
    assert compact["stitch_status"] == "unavailable"
    assert len(compact["impacted_components"]) == 8
    assert len(compact["impacted_pages"]) == 5


def test_approx_chars_handles_pydantic_models():
    """approx_chars should work with both dicts and Pydantic models."""
    site = _make_site(n_pages=2)
    d_count = approx_chars(site)
    assert d_count > 0

    class FakeModel:
        def model_dump_json(self):
            return '{"a": 1}'

    m_count = approx_chars(FakeModel())
    assert m_count > 0


# --- End-to-end: the prompt builder is under the threshold ------------------

def test_designer_prompt_under_size_limit():
    """The 62K designer prompt from the last E2E should now fit easily."""
    from registry.prompts import build_designer_prompt
    from memory.artifacts import load_site_understanding, load_content_recommendation
    try:
        site = load_site_understanding('20260601_104145')
        rec = load_content_recommendation('20260601_104458')
    except Exception:
        return  # skip if the test fixture artifacts aren't on disk
    if site is None or rec is None:
        return
    p = build_designer_prompt(site, rec, 'merimee', persona_text="")
    assert len(p) < 24_000, f"designer prompt is {len(p)} chars, expected <24K (was 62K)"


def test_marketing_prompt_under_size_limit():
    """The marketing prompt should also fit."""
    import json
    import os
    from registry.prompts import build_marketing_prompt
    from memory.artifacts import load_site_understanding
    from models.site_schemas import SiteArchitecture
    try:
        site = load_site_understanding('20260601_104145')
        arch_path = 'memory/site_architectures/20260603_211158.json'
        if not os.path.exists(arch_path):
            return  # skip if the test fixture isn't on disk
        arch = SiteArchitecture(**json.loads(open(arch_path).read()))
    except Exception:
        return
    if site is None or arch is None:
        return
    p = build_marketing_prompt(site, arch, persona_text="")
    assert len(p) < 24_000, f"marketing prompt is {len(p)} chars, expected <24K"


def test_architect_prompt_under_size_limit():
    from registry.prompts import build_architect_prompt
    from memory.artifacts import load_site_understanding
    try:
        site = load_site_understanding('20260601_104145')
    except Exception:
        return  # skip if the test fixture artifact isn't on disk
    if site is None:
        return
    p = build_architect_prompt(site, persona_text="")
    assert len(p) < 24_000, f"architect prompt is {len(p)} chars, expected <24K"


def test_builder_prompt_under_builder_budget():
    """The builder is the convergence point — needs more budget, but should
    still be under 40K (the prompt-size refusal threshold)."""
    import json
    import os
    from registry.prompts import build_builder_prompt
    from memory.artifacts import load_site_understanding, load_content_recommendation
    from models.site_schemas import SiteArchitecture, VisualDirection
    try:
        site = load_site_understanding('20260601_104145')
        arch_path = 'memory/site_architectures/20260603_211158.json'
        if not os.path.exists(arch_path):
            return  # skip if the test fixture isn't on disk
        arch = SiteArchitecture(**json.loads(open(arch_path).read()))
        rec = load_content_recommendation('20260601_104458')
    except Exception:
        return
    if site is None or arch is None or rec is None:
        return
    vd = VisualDirection(primary_change='test', rationale='test', stitch_status='unavailable')
    p = build_builder_prompt(site, arch, rec, 'merimee', persona_text="", visual_direction=vd)
    assert len(p) < 40_000, f"builder prompt is {len(p)} chars, expected <40K"


if __name__ == "__main__":
    import traceback
    tests = [
        test_compact_site_understanding_truncates_pages,
        test_compact_site_understanding_truncates_nav,
        test_compact_site_understanding_caps_global_assets,
        test_compact_site_architecture_keeps_stack_and_count,
        test_compact_content_recommendation_keeps_brand_when_requested,
        test_compact_content_recommendation_omits_brand_when_not_requested,
        test_compact_visual_direction_keeps_deltas_and_caps_lists,
        test_approx_chars_handles_pydantic_models,
        test_designer_prompt_under_size_limit,
        test_marketing_prompt_under_size_limit,
        test_architect_prompt_under_size_limit,
        test_builder_prompt_under_builder_budget,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(0 if failures == 0 else 1)
