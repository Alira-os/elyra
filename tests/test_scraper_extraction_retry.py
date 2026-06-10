"""
Unit tests for skills/agentic/scraper_agent.py — JSON extraction robustness.

The Phase 1 scraper has been observed to log gap entries with
reason="no_valid_json_object_found" against a 2000-char Kilo output. The
underlying cause is twofold:

  1. tools/kilo.py truncates ToolResult.summary to the first 2000 chars of
     the concatenated text events. For long Kilo streams the JSON artifact
     (usually emitted as the final text event) can be entirely outside that
     2000-char window.
  2. If the first attempt's output is unparseable, there was no in-process
     retry — the failure was logged and scrape() returned None.

These tests lock in the new behavior of _try_extract_from_tool_result
(multi-strategy extraction) and the scrape()-level retry path.

Run:
    cd C:\\Users\\micha\\DevProjects\\Alira\\elyra
    python -m pytest tests/test_scraper_extraction_retry.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills.agentic.scraper_agent import (  # noqa: E402
    _try_extract_from_tool_result,
    build_scraper_prompt,
)
from tools.kilo import ToolResult  # noqa: E402


def _make_ndjson_stdout(text_payload: str, prefix_events: int = 0) -> str:
    """Build a synthetic NDJSON event stream that ends with a text event
    containing the given payload."""
    events = []
    for i in range(prefix_events):
        events.append(json.dumps({"type": "tool_use", "part": {"tool": "fetch", "i": i}}))
    events.append(json.dumps({"type": "text", "part": {"text": text_payload}}))
    events.append(json.dumps({"type": "step_finish"}))
    return "\n".join(events)


# --- _try_extract_from_tool_result: strategy coverage ---------------------

def test_extracts_fenced_json_from_text_event():
    """Standard case: Kilo emits a JSON fenced block in the final text event."""
    payload = "Working...\n\n```json\n{\"a\": 1, \"b\": [2,3]}\n```\nDone."
    stdout = _make_ndjson_stdout(payload)
    result = ToolResult(success=True, summary=stdout)
    data, last_text = _try_extract_from_tool_result(result)
    assert data is not None
    assert data == {"a": 1, "b": [2, 3]}
    assert last_text == payload


def test_extracts_bare_json_from_text_event():
    payload = '{"action": "complete", "value": 42}'
    stdout = _make_ndjson_stdout(payload)
    result = ToolResult(success=True, summary=stdout)
    data, _ = _try_extract_from_tool_result(result)
    assert data == {"action": "complete", "value": 42}


def test_returns_none_on_prose_only():
    """No JSON at all -> None, not a fake empty dict."""
    stdout = _make_ndjson_stdout("I explored the site but found no data.")
    result = ToolResult(success=True, summary=stdout)
    data, _ = _try_extract_from_tool_result(result)
    assert data is None


def test_recovers_when_summary_truncated_but_text_event_has_full_json():
    """The 2000-char ToolResult.summary cap can cut the JSON off. If the
    final text event body (preserved in NDJSON) still contains the JSON,
    the extractor must find it there."""
    long_prefix = "x" * 1500  # padding inside the text event
    json_body = "```json\n" + json.dumps({"url": "https://example.com", "platform": "wix"}) + "\n```"
    payload = long_prefix + "\n" + json_body
    # Truncate the summary to the first 2000 chars (mimicking tools/kilo.py).
    full_stdout = _make_ndjson_stdout(payload)
    truncated = full_stdout[:2000]
    assert json_body not in truncated, "test setup: truncated summary must NOT contain the JSON"
    result = ToolResult(success=True, summary=truncated)
    data, _ = _try_extract_from_tool_result(result)
    assert data is not None
    assert data["url"] == "https://example.com"
    assert data["platform"] == "wix"


def test_returns_none_for_truncated_and_no_recoverable_json():
    """When even the last text event is truncated past the JSON brace, the
    extractor correctly returns None instead of raising."""
    # Build a stdout whose first 2000 chars contain NO JSON and whose
    # last text event was also cut.
    junk = "y" * 200
    payload_no_json = junk + " ... some prose, no json"
    stdout = _make_ndjson_stdout(payload_no_json)[:2000]
    result = ToolResult(success=True, summary=stdout)
    data, _ = _try_extract_from_tool_result(result)
    assert data is None


def test_handles_empty_summary():
    result = ToolResult(success=True, summary="")
    data, _ = _try_extract_from_tool_result(result)
    assert data is None


# --- build_scraper_prompt: prompt size + retry mode -----------------------

def test_primary_prompt_under_size_warn_threshold():
    """The primary prompt must stay well under the 32K warn threshold that
    invoke_kilo_safe uses, so we never trip the prompt-too-large refusal."""
    p = build_scraper_prompt("https://example.com")
    assert len(p) < 32_000, f"primary prompt is {len(p)} chars — too large"


def test_retry_prompt_is_compact():
    """The retry prompt should be much smaller than the primary (no schema dump,
    no exploration guidance) so it can't itself trip size limits."""
    p = build_scraper_prompt("https://example.com", retry_mode=True)
    assert len(p) < 15_000, f"retry prompt is {len(p)} chars"
    # The retry must NOT contain the schema dump — that's the point of retry_mode.
    assert "model_json_schema" not in p
    # It must contain the "RETRY" marker so the model understands the context.
    assert "RETRY" in p


# --- scrape(): retry path uses invoke_kilo_safe twice ----------------------

def test_scrape_retries_with_retry_mode_when_first_output_unparseable():
    """scrape() must issue a second invoke_kilo_safe call (with retry_mode)
    when the first call's output cannot be parsed. The second call's
    response is the one that gets parsed."""
    from skills.agentic.scraper_agent import scrape

    call_log = []

    valid_payload = json.dumps({
        "url": "https://example.com",
        "platform": "wix",
        "platform_confidence": 0.9,
        "site_name": "example",
        "total_pages_discovered": 1,
        "pages": [{
            "url": "https://example.com",
            "title": "Example",
            "page_type": ["home"],
            "text_content": "Hello",
            "text_word_count": 1,
            "images": [],
            "components": [],
        }],
        "global_assets": {},
        "contact_info": {},
        "navigation_structure": [],
        "estimated_fidelity": 0.5,
        "accessibility_flags": [],
    })
    retry_stdout = json.dumps({
        "type": "text",
        "part": {"text": "```json\n" + valid_payload + "\n```"},
    })

    def fake_invoke(prompt, context, working_dir, persona, timeout, **kwargs):
        call_log.append({"persona": persona, "prompt_len": len(prompt), "context": context})
        if len(call_log) == 1:
            return ToolResult(success=True, summary="prose only, no JSON here")
        return ToolResult(success=True, summary=retry_stdout)

    with patch("skills.agentic.scraper_agent.invoke_kilo_safe", side_effect=fake_invoke):
        result = scrape("https://example.com")

    assert len(call_log) == 2, f"expected 2 invocations (initial + retry), got {len(call_log)}"
    assert result is not None, "scrape() should return a SiteUnderstanding after retry"
    assert str(result.url) == "https://example.com/"
    assert result.platform.value == "wix"


def test_scrape_does_not_retry_when_first_output_is_valid():
    """Happy path: one invocation is enough; the retry must not fire."""
    from skills.agentic.scraper_agent import scrape

    call_count = {"n": 0}
    valid_payload = json.dumps({
        "url": "https://example.com",
        "platform": "wix",
        "platform_confidence": 0.9,
        "site_name": "example",
        "total_pages_discovered": 1,
        "pages": [{
            "url": "https://example.com",
            "title": "Example",
            "page_type": ["home"],
            "text_content": "Hello",
            "text_word_count": 1,
            "images": [],
            "components": [],
        }],
        "global_assets": {},
        "contact_info": {},
        "navigation_structure": [],
        "estimated_fidelity": 0.5,
        "accessibility_flags": [],
    })
    stdout = json.dumps({
        "type": "text",
        "part": {"text": "```json\n" + valid_payload + "\n```"},
    })

    def fake_invoke(prompt, context, working_dir, persona, timeout, **kwargs):
        call_count["n"] += 1
        return ToolResult(success=True, summary=stdout)

    with patch("skills.agentic.scraper_agent.invoke_kilo_safe", side_effect=fake_invoke):
        result = scrape("https://example.com")

    assert call_count["n"] == 1
    assert result is not None


if __name__ == "__main__":
    import traceback
    tests = [
        test_extracts_fenced_json_from_text_event,
        test_extracts_bare_json_from_text_event,
        test_returns_none_on_prose_only,
        test_recovers_when_summary_truncated_but_text_event_has_full_json,
        test_returns_none_for_truncated_and_no_recoverable_json,
        test_handles_empty_summary,
        test_primary_prompt_under_size_warn_threshold,
        test_retry_prompt_is_compact,
        test_scrape_retries_with_retry_mode_when_first_output_unparseable,
        test_scrape_does_not_retry_when_first_output_is_valid,
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
