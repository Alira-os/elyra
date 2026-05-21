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


def detect_platform_with_cascade(url: str, html: Optional[str] = None, use_llm_fallback: bool = True) -> dict:
    """
    Multi-stage platform detection with confidence cascade.

    Stage 0: URL regex pattern matching
    Stage 1: HTML DOM marker scan (triggered when Stage 0 confidence < 0.5)
    Stage 2: LLM meta-detector (triggered when Stage 1 confidence < 0.6)

    Args:
        url: The site URL to detect
        html: Optional HTML content (fetches if not provided)
        use_llm_fallback: If True, call LLM meta-detector when confidence < 0.6

    Returns:
        {
            "platform": "wix" | "squarespace" | "wordpress" | "generic",
            "confidence": 0.0 - 1.0,
            "indicators": list of detection signals found,
            "llm_invoked": bool,
            "stage": "url" | "html" | "llm",
            "error": None | error message string
        }
    """
    indicators = []
    stage = "url"
    llm_invoked = False

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

    if max_score < 0.5 and not html:
        html = _fetch_html(url)

    if html:
        stage = "html"
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

    if max_score < 0.6 and use_llm_fallback and html:
        llm_result = _meta_detect_with_llm(url, html[:3000])
        if llm_result:
            llm_invoked = True
            stage = "llm"
            if llm_result["confidence"] > max_score:
                max_platform = llm_result["platform"]
                max_score = llm_result["confidence"]
                indicators.extend([f"llm: {e}" for e in llm_result.get("evidence", [])])

    if max_score < 0.3:
        return {
            "platform": "generic",
            "confidence": max_score,
            "indicators": indicators if indicators else ["no strong platform indicators"],
            "llm_invoked": llm_invoked,
            "stage": stage,
            "error": None
        }

    return {
        "platform": max_platform,
        "confidence": min(max_score, 1.0),
        "indicators": indicators,
        "llm_invoked": llm_invoked,
        "stage": stage,
        "error": None
    }


def _meta_detect_with_llm(url: str, html_snippet: str) -> Optional[dict]:
    """
    Stage 2: LLM meta-detector for when URL+HTML detection confidence < 0.6.

    Uses a template-based approach for Phase 1 (LLM not fully wired).
    In Phase 2, this will call actual LLM with prompt template.

    Args:
        url: Site URL
        html_snippet: First 3000 chars of HTML

    Returns:
        Optional[dict] with platform, confidence, evidence
    """
    html_lower = html_snippet.lower()

    evidence = []

    if "wix" in html_lower and ("wixstudio" in url.lower() or "wixsite" in url.lower() or "wixeditor" in html_lower):
        evidence.append("Wix-specific markup patterns detected")
        return {"platform": "wix", "confidence": 0.75, "evidence": evidence}

    if "squarespace" in html_lower or ("squarespace" in url.lower()):
        evidence.append("Squarespace-specific markup patterns detected")
        return {"platform": "squarespace", "confidence": 0.75, "evidence": evidence}

    if "wp-content" in html_lower or "wp-includes" in html_lower or "wordpress" in html_lower:
        evidence.append("WordPress-specific markup patterns detected")
        return {"platform": "wordpress", "confidence": 0.75, "evidence": evidence}

    if "shopify" in html_lower or "myshopify" in html_lower:
        evidence.append("Shopify-specific markup detected")
        return {"platform": "shopify", "confidence": 0.7, "evidence": evidence}

    if "webflow" in html_lower or "webflow.io" in url.lower():
        evidence.append("Webflow-specific markup detected")
        return {"platform": "webflow", "confidence": 0.7, "evidence": evidence}

    if "framer" in html_lower or "framer.app" in url.lower():
        evidence.append("Framer-specific markup detected")
        return {"platform": "framer", "confidence": 0.7, "evidence": evidence}

    return None


# Alias for backwards compatibility
def detect_platform(url: str, html: Optional[str] = None, fetch_on_low_confidence: bool = True) -> dict:
    result = detect_platform_with_cascade(url, html, use_llm_fallback=False)
    result.pop("llm_invoked", None)
    result.pop("stage", None)
    return result