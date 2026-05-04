# Platform Detector Skill

**Version:** 1.1
**Status:** Phase 1 MVP — Multi-stage detection with HTML fetch

---

## Purpose

Detects the source platform (Wix, Squarespace, WordPress, or generic/unknown) from a URL and/or HTML content. This is the first skill invoked after the user provides a URL, and its output feeds into the routing decision.

---

## Detection Architecture (Multi-Stage)

### Stage 1: URL Pattern Matching
Fast, no network call. Check for known platform patterns in URL:
- **Wix:** `wixsite.com`, `.wix.com`, `wix.com`, `wixstudio.com`
- **Squarespace:** `squarespace.com`
- **WordPress:** `/wp-content/`, `/wp-includes/`

### Stage 2: HTML Fetch (Low Confidence Fallback)
When URL detection confidence < 0.5 and no HTML provided:
1. Fetch HTML from URL (10s timeout)
2. Check for platform-specific DOM markers
3. Update confidence scores

### Stage 3: DOM Inspection
Check for:
- Platform-specific class names (`wix-*`, `squarespace-*`)
- Platform-specific attributes (`data-wix`)
- Meta generator tags (Wix, Squarespace, WordPress)

---

## When to Call

- **After onboarding:** When user provides a URL, immediately call `platform_detector`
- **Confirmation:** The scraper_specialist may re-check platform to confirm
- **Routing override:** If platform detector returns low confidence (< 0.3) or "generic", the Conductor may invoke LLM override

---

## Detection Indicators

### Wix
| Indicator | Confidence Weight |
|-----------|-------------------|
| URL contains `wixsite.com`, `.wix.com`, `wix.com`, or `wixstudio.com` | +0.4 |
| HTML contains `wix-` marker | +0.15 |
| HTML contains `wix` in class names | +0.15 |
| Meta tag `generator` contains `Wix` | +0.2 |
| **Maximum confidence** | 1.0 |

### Squarespace
| Indicator | Confidence Weight |
|-----------|-------------------|
| URL contains `squarespace.com` | +0.4 |
| HTML contains `squarespace-` marker | +0.15 |
| HTML contains `squarespace` in class names | +0.15 |
| Meta tag `generator` contains `Squarespace` | +0.2 |
| **Maximum confidence** | 1.0 |

### WordPress
| Indicator | Confidence Weight |
|-----------|-------------------|
| URL contains `/wp-content/` | +0.3 |
| URL contains `/wp-includes/` | +0.3 |
| HTML contains `wp-content` or `wp-includes` marker | +0.15 |
| Meta tag `generator` contains `WordPress` | +0.2 |
| **Maximum confidence** | 1.0 |

### Generic/Unknown
| Condition | Result |
|-----------|--------|
| Total score < 0.3 after all stages | platform = "generic" |
| All indicators present but conflicting | platform = "generic", confidence = 0.2 |

---

## Interface

```python
def detect_platform(url: str, html: str | None = None, fetch_on_low_confidence: bool = True) -> dict:
    """
    Detect platform from URL and/or HTML content.

    Args:
        url: The site URL to detect
        html: Optional HTML content (fetches if not provided)
        fetch_on_low_confidence: If True, fetch HTML when URL confidence < 0.5

    Returns:
        {
            "platform": "wix" | "squarespace" | "wordpress" | "generic",
            "confidence": 0.0 - 1.0,
            "indicators": ["wixstudio.com in URL", "wix- in HTML class names"],
            "error": None | "string error message"
        }
    """
```

---

## Usage Examples

```python
from skills.executable.platform_detector import detect_platform

# Stage 1 only (URL-based, no fetch)
result = detect_platform("https://photographer.wixsite.com/portfolio", fetch_on_low_confidence=False)
# {"platform": "wix", "confidence": 0.4, ...}

# Stage 1 + 2 (auto-fetch on low confidence)
result = detect_platform("https://merimeesolutions.wixstudio.com/my-site-2")
# {"platform": "wix", "confidence": 0.9, "indicators": ["wixstudio.com in URL", "wix- in HTML", ...]}
```

---

## Edge Cases

### URL Redirect Chain
If URL redirects (301/302), follow redirects and detect from final URL.

### JavaScript-Heavy Sites
Some sites use client-side rendering. HTML fetch captures static HTML; for JS-rendered content, use Playwright MCP.

### Subdomains with Platform Indicators
Wix and Squarespace often use subdomains:
- `site-name.wixsite.com`
- `site-name.squarespace.com`
- `site-name.wixstudio.com` (custom domain)
- `www.platform.com` (less common)

### Password-Protected Sites
If site returns 401/403, return URL-based detection (don't block on HTML fetch).

### Custom Domains
Sites using custom domains (e.g., `wixstudio.com`) rely on HTML markers since URL doesn't contain platform identifier.

---

## Dependencies

- `urllib.request` — Built-in for HTML fetching
- `tools.mcp.playwright` — For JS-rendered content (Phase 1+)

---

## What Gets Passed to Conductor

```python
{
    "platform": "wix",
    "confidence": 0.9,
    "indicators": ["wixstudio.com in URL", "wix- in HTML class names", "Wix in meta generator"]
}
```

---

## Anti-Patterns

- **Do not** return "wix" just because URL contains "wix" — require supporting evidence
- **Do not** require HTML for URL-based detection — URL alone is sufficient for high-confidence matches
- **Do not** block on HTML fetch — use `fetch_on_low_confidence=False` if timeout is unacceptable
- **Do not** cache detection results — platform can theoretically change