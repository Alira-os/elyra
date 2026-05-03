# Platform Detector Skill

**Version:** 1.0
**Status:** Phase 0 MVP

---

## Purpose

Detects the source platform (Wix, Squarespace, WordPress, or generic/unknown) from a URL and/or HTML content. This is the first skill invoked after the user provides a URL, and its output feeds into the routing decision.

---

## When to Call

- **After onboarding:** When user provides a URL, immediately call `platform_detector`
- **Confirmation:** The scraper_specialist may re-check platform to confirm
- **Routing override:** If platform detector returns low confidence (< 0.5) or "generic", the Conductor may invoke LLM override

---

## Detection Indicators

### Wix
| Indicator | Confidence Weight |
|-----------|-------------------|
| URL contains `wixsite.com` or `.wix.com` | +0.4 |
| HTML contains `wix` in class names | +0.2 |
| HTML contains `data-wix` attributes | +0.2 |
| Meta tag `generator` contains `Wix` | +0.2 |
| **Maximum confidence if all present** | 1.0 |

### Squarespace
| Indicator | Confidence Weight |
|-----------|-------------------|
| URL contains `squarespace.com` | +0.4 |
| HTML contains `squarespace` in class names | +0.2 |
| Squarespace-specific CSS classes (e.g., `.Header`, `.Footer`) | +0.2 |
| Meta tag `generator` contains `Squarespace` | +0.2 |
| **Maximum confidence if all present** | 1.0 |

### WordPress
| Indicator | Confidence Weight |
|-----------|-------------------|
| URL contains `/wp-content/` | +0.3 |
| URL contains `/wp-includes/` | +0.2 |
| HTML contains `wp-content` in paths | +0.2 |
| Meta tag `generator` contains `WordPress` | +0.2 |
| WordPress-specific meta tags (`og:locale`, etc.) | +0.1 |
| **Maximum confidence if all present** | 1.0 |

### Generic/Unknown
| Condition | Result |
|-----------|--------|
| No indicators above threshold (total < 0.5) | platform = "generic", confidence = 0.3 |
| All indicators present but conflicting | platform = "generic", confidence = 0.2 |

---

## Interface

```python
def detect_platform(url: str, html: str | None = None) -> dict:
    """
    Detect platform from URL and/or HTML content.

    Args:
        url: The site URL to detect
        html: Optional HTML content (fetches if not provided)

    Returns:
        {
            "platform": "wix" | "squarespace" | "wordpress" | "generic",
            "confidence": 0.0 - 1.0,
            "indicators": ["wixsite.com in URL", "wix in class names"],
            "error": None | "string error message"
        }
    """
```

---

## Usage Example

```python
from skills.executable.platform_detector import detect_platform

result = detect_platform("https://photographer.wixsite.com/portfolio")
# {
#     "platform": "wix",
#     "confidence": 0.94,
#     "indicators": ["wixsite.com in URL", "wix in class names", "data-wix attributes"],
#     "error": None
# }
```

---

## Edge Cases

### URL Redirect Chain
If URL redirects (301/302), follow redirects and detect from final URL.

### JavaScript-Heavy Sites
Some sites use client-side routing. If URL-based detection fails but HTML is available, rely on HTML indicators.

### Subdomains with Platform Indicators
Wix and Squarespace often use subdomains. Detection should handle:
- `site-name.wixsite.com`
- `site-name.squarespace.com`
- `www.platform.com` (less common)

### Password-Protected Sites
If site returns 401/403, still attempt URL-based detection (don't need HTML).

---

## Dependencies

- `tools.mcp.fetch` — For fetching HTML content if not provided
- `tools.mcp.playwright` — For JS-rendered content if needed

---

## What Gets Passed to Conductor

```python
{
    "platform": "wix",
    "confidence": 0.94,
    "indicators": ["wixsite.com in URL", "wix in class names"]
}
```

---

## Anti-Patterns

- **Do not** return "wix" just because URL contains "wix" (some sites are hosted on Wix incorrectly)
- **Do not** require HTML for URL-based detection — URL alone is sufficient for high-confidence matches
- **Do not** cache detection results — platform can theoretically change