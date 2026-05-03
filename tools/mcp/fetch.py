"""
Fetch MCP Client

**Phase 0 Status:** PARTIAL IMPLEMENTATION — urllib-based fetching works, but not using official MCP SDK.
**Phase 1+ Target:** Replace with official MCP client using mcp Python SDK.

Purpose:
    Clean content extraction from URLs.

Phase 0 Behavior:
    Uses Python urllib for HTTP requests. Works for basic fetching.
    Does NOT use official MCP protocol — just a local implementation.

Phase 1+ Behavior:
    Connect to Fetch MCP server via mcp.ClientSession.
    This allows integration with any MCP-compatible fetch server.

Note:
    urllib implementation is useful for Phase 0 testing without MCP servers.
    Keep interface compatible so replacement is straightforward.
"""

import urllib.request
import urllib.error
from typing import Optional
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass
class FetchResult:
    url: str
    status_code: int
    html: str
    text: str
    metadata: dict
    error: Optional[str] = None


def fetch_content(url: str, timeout: int = 30) -> FetchResult:
    """
    Fetch content from a URL.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        FetchResult with content and metadata
    """
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Elyra/1.0 (+https://github.com/merimeesoftware/elyra)"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="replace")
            status = response.getcode()

            parser = _ContentParser()
            parser.feed(html)

            return FetchResult(
                url=url,
                status_code=status,
                html=html,
                text=parser.get_text(),
                metadata={
                    "content_type": response.headers.get("Content-Type", ""),
                    "final_url": response.geturl()
                }
            )
    except urllib.error.HTTPError as e:
        return FetchResult(
            url=url,
            status_code=e.code,
            html="",
            text="",
            metadata={},
            error=f"HTTP {e.code}: {e.reason}"
        )
    except urllib.error.URLError as e:
        return FetchResult(
            url=url,
            status_code=0,
            html="",
            text="",
            metadata={},
            error=f"URL error: {e.reason}"
        )
    except Exception as e:
        return FetchResult(
            url=url,
            status_code=0,
            html="",
            text="",
            metadata={},
            error=str(e)
        )


def get_clean_content(url: str) -> FetchResult:
    """
    Get clean text content from a URL (alias for fetch_content).

    Args:
        url: URL to fetch

    Returns:
        FetchResult with clean text content
    """
    return fetch_content(url)


class _ContentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.in_script = False
        self.in_style = False
        self.skip_tags = {"script", "style", "noscript"}
        self.current_skip_tag = None

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.in_script = True
            self.current_skip_tag = tag

    def handle_endtag(self, tag):
        if tag == self.current_skip_tag:
            self.in_script = False
            self.current_skip_tag = None

    def handle_data(self, data):
        if not self.in_script:
            text = data.strip()
            if text:
                self.text_parts.append(text)

    def get_text(self) -> str:
        return " ".join(self.text_parts)


if __name__ == "__main__":
    result = fetch_content("https://example.com")
    print(f"Status: {result.status_code}")
    print(f"Text preview: {result.text[:200]}...")
    print(f"Error: {result.error}")