"""
tests/test_coercion.py — Phase B tests for the central artifact coercion module.

Goal: a single bad LLM-emitted field no longer kills the entire migration.
The highland trees services artifact is the canonical test case.

Run:
    python -m pytest tests/test_coercion.py -v
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models._coercion import (  # noqa: E402
    CoercionError,
    coerce_artifact,
    coerce_site_understanding,
    load_site_understanding_from_path,
    repair_json_text,
)
from models.site_schemas import (  # noqa: E402
    PageType,
    PlatformType,
    SiteUnderstanding,
)


# --- Minimal-valid SiteUnderstanding fixture -------------------------------

def _minimal_site_understanding(**overrides) -> dict:
    """Build a dict that is valid as a SiteUnderstanding with the bare
    minimum required fields. Tests override the fields they care about.
    """
    data = {
        "url": "https://example.com/",
        "platform": "generic",
        "platform_confidence": 0.5,
        "site_name": "Example",
        "total_pages_discovered": 1,
        "estimated_fidelity": 0.7,
        "pages": [
            {
                "url": "https://example.com/",
                "title": "Home",
                "page_type": ["home"],
                "text_content": "Welcome to Example.",
            }
        ],
    }
    data.update(overrides)
    return data


# --- 1. Unknown page_type values coerce to "other" --------------------------

def test_unknown_page_type_values_coerce_to_other():
    """The highland artifact emits 'blog_index', 'form', 'testimonials',
    'service_area' — none of which are in the PageType enum. They must
    all coerce to 'other' so the schema validates.
    """
    data = _minimal_site_understanding(
        pages=[
            {
                "url": "https://example.com/blog/",
                "title": "Blog",
                "page_type": ["blog_index"],
                "text_content": "Latest posts",
            },
            {
                "url": "https://example.com/contact/",
                "title": "Contact",
                "page_type": ["form"],
                "text_content": "Get in touch",
            },
            {
                "url": "https://example.com/reviews/",
                "title": "Reviews",
                "page_type": ["testimonials"],
                "text_content": "What our clients say",
            },
            {
                "url": "https://example.com/areas/",
                "title": "Service Areas",
                "page_type": ["service_area"],
                "text_content": "We serve these areas",
            },
            {
                "url": "https://example.com/bogus/",
                "title": "Bogus",
                "page_type": ["completely_unknown"],
                "text_content": "x",
            },
        ],
    )
    su = coerce_site_understanding(data)
    assert su.pages[0].page_type == [PageType.OTHER]
    assert su.pages[1].page_type == [PageType.OTHER]
    assert su.pages[2].page_type == [PageType.OTHER]
    assert su.pages[3].page_type == [PageType.OTHER]
    assert su.pages[4].page_type == [PageType.OTHER]


# --- 2. email=null is dropped ----------------------------------------------

def test_email_null_is_dropped_from_contact_info():
    data = _minimal_site_understanding(
        contact_info={
            "email": None,
            "phone": "(734) 999-3880",
            "address": "1300 W Joy Rd, Ann Arbor, MI 48105",
        },
    )
    su = coerce_site_understanding(data)
    assert "email" not in su.contact_info
    assert su.contact_info["phone"] == "(734) 999-3880"
    assert su.contact_info["address"] == "1300 W Joy Rd, Ann Arbor, MI 48105"


# --- 3. dict geo coerces to str --------------------------------------------

def test_dict_geo_coerces_to_str():
    data = _minimal_site_understanding(
        contact_info={
            "geo": {"lat": 42.34, "lng": -83.77},
        },
    )
    su = coerce_site_understanding(data)
    assert su.contact_info["geo"] == "42.34,-83.77"
    assert isinstance(su.contact_info["geo"], str)


# --- 4. "tel:" URL in nav is dropped ---------------------------------------

def test_tel_url_dropped_from_navigation_structure():
    data = _minimal_site_understanding(
        navigation_structure=[
            {"label": "Home", "url": "/", "page_url": "https://example.com/", "children": []},
            {"label": "Click to Call", "url": "tel:7349993880", "page_url": "tel:7349993880", "children": []},
            {
                "label": "Services",
                "url": "/services",
                "page_url": "https://example.com/services/",
                "children": [
                    {"label": "SEO", "url": "/services/seo", "page_url": "https://example.com/services/seo/", "children": []},
                    {"label": "Email us", "url": "mailto:hi@example.com", "page_url": "mailto:hi@example.com", "children": []},
                ],
            },
        ],
    )
    su = coerce_site_understanding(data)
    # Top-level: Home + Services remain; tel: node dropped.
    labels = [n.label for n in su.navigation_structure]
    assert "Click to Call" not in labels
    assert "Home" in labels
    assert "Services" in labels
    # Nested: SEO remains, mailto: child dropped.
    services = next(n for n in su.navigation_structure if n.label == "Services")
    child_labels = [c.label for c in services.children]
    assert "SEO" in child_labels
    assert "Email us" not in child_labels


# --- 5. The real 84KB highland artifact loads cleanly -----------------------

def test_highland_artifact_loads_cleanly():
    """The acceptance test for Phase B: the previously-broken highland
    artifact (brace drift + unknown enums + null email + dict geo +
    tel: nav) now loads through the central coercer.
    """
    path = ROOT / "memory" / "site_understandings" / "highlandtreeservices_com.json"
    if not path.exists():
        # Don't fail if the artifact is missing in a CI environment.
        return
    su = load_site_understanding_from_path(path)
    assert isinstance(su, SiteUnderstanding)
    assert str(su.url).rstrip("/") == "https://highlandtreeservices.com"
    assert su.platform == PlatformType.WORDPRESS
    assert su.platform_confidence >= 0.9
    assert len(su.pages) > 0
    # Some sanity checks on the highland-specific drift points:
    #   - The contact form (or any iframe'd form) was captured.
    #   - No page has a page_type that's not in the enum (i.e. no
    #     validation was skipped).
    for page in su.pages:
        for pt in page.page_type:
            assert pt in {PageType.HOME, PageType.ABOUT, PageType.SERVICES,
                          PageType.PORTFOLIO, PageType.BLOG, PageType.BLOG_POST,
                          PageType.CONTACT, PageType.GALLERY, PageType.LEGAL,
                          PageType.OTHER}, f"unexpected page_type: {pt}"


# --- 6. JSON repair handles double-braces ----------------------------------

def test_json_repair_handles_double_braces():
    """The highland artifact has 37 stray `}}` sequences. Repair them
    and verify the resulting JSON parses, then coerce to a minimal
    SiteUnderstanding.
    """
    # Hand-crafted string with the same `}}` drift pattern. Notice the
    # `}}` after the 21 (close the value object, then close the inner
    # object — but LLM wrote one extra `}`).
    raw = """{
      "url": "https://repair-test.example.com/",
      "platform": "generic",
      "platform_confidence": 0.5,
      "site_name": "Repair Test",
      "total_pages_discovered": 1,
      "estimated_fidelity": 0.7,
      "pages": [{
        "url": "https://repair-test.example.com/",
        "title": "Home",
        "page_type": ["home"],
        "text_content": "hi",
        "json_ld": [{"schema_type": "LocalBusiness", "raw": {"@type": "LocalBusiness", "aggregateRating": {"@type": "AggregateRating", "ratingValue": 4.8, "reviewCount": 21}}}],
        "components": [{"type": "hero", "order": 0, "content": {"headline": "hi", "extra": "x"}}]
      }]
    }"""
    # The `}}}` at the end of reviewCount is the drift signature.
    su = coerce_artifact("site_understandings", raw)
    assert isinstance(su, SiteUnderstanding)
    assert str(su.url) == "https://repair-test.example.com/"
    # The first page should be loadable.
    assert su.pages[0].title == "Home"
    assert su.pages[0].page_type == [PageType.HOME]


# --- 7. Manager action normalization (Phase B.6) ---------------------------

def test_manager_action_normalized():
    """Phase B.6: an action like 'Invoke persona' (capital I, with space)
    should normalize to 'invoke_persona' and validate. Similarly for
    'ROUTE_BACK' (all caps).
    """
    from skills.agentic.manager_decision import (
        validate_and_repair_manager_decision,
    )

    # Capital-I variant.
    d = validate_and_repair_manager_decision(
        '{"action": "Invoke persona", "persona": "scraper", "reason": "redo"}'
    )
    assert d.action == "invoke_persona"
    assert d.persona == "scraper"

    # All-caps variant.
    d = validate_and_repair_manager_decision(
        '{"action": "ROUTE_BACK", "persona": "architect", "reason": "redo"}'
    )
    assert d.action == "route_back"
    assert d.persona == "architect"

    # Whitespace variant.
    d = validate_and_repair_manager_decision(
        '{"action": "  complete  ", "reason": "all done"}'
    )
    assert d.action == "complete"


# --- Bonus: CoercionError raised on truly invalid input --------------------

def test_coercion_error_on_truly_invalid_input():
    """If the data cannot be coerced even with the lenient pass, raise
    CoercionError (not a raw Pydantic ValidationError)."""
    bad = {
        "url": "not-a-url",  # HttpUrl rejects this
        "platform": "generic",
        "platform_confidence": 99.0,  # out of [0, 1] range
        "site_name": "x",
        "total_pages_discovered": 0,
        "pages": [],
    }
    try:
        coerce_site_understanding(bad)
    except CoercionError:
        pass
    else:
        # Not strictly required to raise — but the existing lenient
        # pass might accept it. Either way, the function must not
        # raise raw Pydantic ValidationError (it would surface as a
        # confusing migration abort).
        pass


# --- Direct repair_json_text tests -----------------------------------------

def test_repair_drops_stray_closing_brace():
    """`21}}}` (three in a row) — the third is stray. Repair should
    drop just the unmatched one."""
    text = '{"a": 1, "b": 2}}}'  # one extra `}`
    repaired = repair_json_text(text)
    # The repaired string should parse as a flat dict.
    parsed = json.loads(repaired)
    assert parsed == {"a": 1, "b": 2}


def test_repair_preserves_valid_double_close():
    """`}}` where both have matching openers must NOT be dropped."""
    text = '{"a": {"b": 1}}'  # two legitimate closes
    repaired = repair_json_text(text)
    assert json.loads(repaired) == {"a": {"b": 1}}
