import re
from typing import Optional


def detect_platform(url: str, html: Optional[str] = None) -> dict:
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

    if "wixsite.com" in url_lower or ".wix.com" in url_lower or "wix.com" in url_lower:
        platform_scores["wix"] += 0.4
        indicators.append("wixsite.com or .wix.com in URL")

    if "squarespace.com" in url_lower:
        platform_scores["squarespace"] += 0.4
        indicators.append("squarespace.com in URL")

    if "/wp-content/" in url_lower:
        platform_scores["wordpress"] += 0.3
        indicators.append("/wp-content/ in URL")

    if "/wp-includes/" in url_lower:
        platform_scores["wordpress"] += 0.2
        indicators.append("/wp-includes/ in URL")

    if html:
        html_lower = html.lower()

        if " data-wix" in html_lower or 'data-wix' in html_lower:
            platform_scores["wix"] += 0.2
            indicators.append("data-wix attributes")

        if "wix" in html_lower and ("class=" in html_lower):
            wix_class_matches = re.findall(r'class="[^"]*wix[^"]*"', html_lower, re.IGNORECASE)
            if wix_class_matches:
                platform_scores["wix"] += 0.2
                indicators.append(f"wix in class names ({len(wix_class_matches)} found)")

        if "squarespace" in html_lower and "class=" in html_lower:
            ss_class_matches = re.findall(r'class="[^"]*squarespace[^"]*"', html_lower, re.IGNORECASE)
            if ss_class_matches:
                platform_scores["squarespace"] += 0.2
                indicators.append(f"squarespace in class names ({len(ss_class_matches)} found)")

        if "wp-content" in html_lower:
            platform_scores["wordpress"] += 0.2
            indicators.append("wp-content in HTML")

        if "wp-includes" in html_lower:
            platform_scores["wordpress"] += 0.1
            indicators.append("wp-includes in HTML")

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

    if max_score < 0.5:
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