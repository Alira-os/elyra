import re
import urllib.request
from typing import Optional


WIX_URL_PATTERNS = [
    "wixsite.com",
    ".wix.com",
    "wix.com",
    "wixstudio.com",
]

SQUARESPACE_URL_PATTERNS = [
    "squarespace.com",
]

WORDPRESS_URL_PATTERNS = [
    "/wp-content/",
    "/wp-includes/",
]

PLATFORM_HTML_MARKERS = {
    "wix": [
        "data-wix",
        "wix-",
        "wix.com",
    ],
    "squarespace": [
        "squarespace-",
        "squarespace.com",
    ],
    "wordpress": [
        "wp-content",
        "wp-includes",
        "wp-json",
    ],
}


def _fetch_html(url: str, timeout: int = 10) -> Optional[str]:
    """Fetch HTML from URL with timeout and error handling."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except Exception:
        return None


def detect_platform(url: str, html: Optional[str] = None, fetch_on_low_confidence: bool = True) -> dict:
    """
    Detect platform (Wix, Squarespace, WordPress, generic) from URL and/or HTML.

    Args:
        url: The site URL to detect
        html: Optional HTML content (fetches if not provided)

    Returns:
        {
            "platform": "wix" | "squarespace" | "wordpress" | "generic",
            "confidence": 0.0 - 1.0,
            "indicators": list of detection signals found,
            "error": None | error message string
        }
    """
    indicators = []
    platform_scores = {"wix": 0.0, "squarespace": 0.0, "wordpress": 0.0}

    url_lower = url.lower()

    for pattern in WIX_URL_PATTERNS:
        if pattern in url_lower:
            platform_scores["wix"] += 0.4
            indicators.append(f"{pattern} in URL")
            break

    for pattern in SQUARESPACE_URL_PATTERNS:
        if pattern in url_lower:
            platform_scores["squarespace"] += 0.4
            indicators.append("squarespace.com in URL")
            break

    for pattern in WORDPRESS_URL_PATTERNS:
        if pattern in url_lower:
            platform_scores["wordpress"] += 0.3
            indicators.append(f"{pattern} in URL")
            break

    max_platform = max(platform_scores, key=platform_scores.get)
    max_score = platform_scores[max_platform]

    if max_score < 0.5 and fetch_on_low_confidence and not html:
        html = _fetch_html(url)

    if html:
        html_lower = html.lower()

        for marker in PLATFORM_HTML_MARKERS["wix"]:
            if marker in html_lower:
                platform_scores["wix"] += 0.15
                indicators.append(f"wix marker '{marker}' in HTML")
                break

        for marker in PLATFORM_HTML_MARKERS["squarespace"]:
            if marker in html_lower:
                platform_scores["squarespace"] += 0.15
                indicators.append(f"squarespace marker '{marker}' in HTML")
                break

        for marker in PLATFORM_HTML_MARKERS["wordpress"]:
            if marker in html_lower:
                platform_scores["wordpress"] += 0.15
                indicators.append(f"wordpress marker '{marker}' in HTML")
                break

        if "wix" in html_lower and "class=" in html_lower:
            wix_class_matches = re.findall(r'class="[^"]*wix[^"]*"', html_lower, re.IGNORECASE)
            if wix_class_matches:
                platform_scores["wix"] += 0.15
                indicators.append(f"wix in class names ({len(wix_class_matches)} found)")

        if "squarespace" in html_lower and "class=" in html_lower:
            ss_class_matches = re.findall(r'class="[^"]*squarespace[^"]*"', html_lower, re.IGNORECASE)
            if ss_class_matches:
                platform_scores["squarespace"] += 0.15
                indicators.append(f"squarespace in class names ({len(ss_class_matches)} found)")

        generator_match = re.search(r'<meta[^>]*name=["\']generator["\'][^>]*content=["\']([^"\']*)["\']', html_lower)
        if generator_match:
            generator = generator_match.group(1).lower()
            if "wix" in generator:
                platform_scores["wix"] += 0.2
                indicators.append("Wix in meta generator")
            if "squarespace" in generator:
                platform_scores["squarespace"] += 0.2
                indicators.append("Squarespace in meta generator")
            if "wordpress" in generator:
                platform_scores["wordpress"] += 0.2
                indicators.append("WordPress in meta generator")

    max_platform = max(platform_scores, key=platform_scores.get)
    max_score = platform_scores[max_platform]

    if max_score < 0.3:
        return {
            "platform": "generic",
            "confidence": max_score,
            "indicators": indicators if indicators else ["no strong platform indicators"],
            "error": None
        }

    return {
        "platform": max_platform,
        "confidence": min(max_score, 1.0),
        "indicators": indicators,
        "error": None
    }


if __name__ == "__main__":
    test_cases = [
        ("https://photographer.wixsite.com/portfolio", None),
        ("https://example.squarespace.com", None),
        ("https://blog.example.com/wp-content/uploads/2024/01/post.jpg", None),
        ("https://unknown-site.com", None),
    ]

    for url, html in test_cases:
        result = detect_platform(url, html)
        print(f"{url} -> {result['platform']} ({result['confidence']:.2f})")