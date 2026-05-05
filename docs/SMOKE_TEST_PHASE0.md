# Phase 0 Smoke Test Report
**Date:** 2026-05-02
**Site:** https://merimeesolutions.wixstudio.com/my-site-2 (Homepage)
**Mode:** `task_type: "generic"`, Stop at Codegen

## Test Setup
- Used custom smoke test script to bypass full pipeline (no security gate/deploy).
- Forced `platform: "generic"` due to known detector limitation on custom domains.
- Scraping was stubbed (Phase 0 limitation).

## Friction Points Observed

### 1. Platform Detection Failure (High Priority) — PHASE 1 ITEM
**Observation:**
The `platform_detector` returned `{"platform": "generic", "confidence": 0.0}` for `wixstudio.com`.
**Reason:**
The URL uses a custom domain (`wixstudio.com`) instead of the standard `wixsite.com`. The current detector only looks for URL patterns (`wixsite.com`, `.wix.com`, `wix.com`) and does NOT include `wixstudio.com`.

Additionally, when URL confidence is low, the detector does NOT fetch HTML to check for platform-specific DOM markers.

**Impact:**
This forces the Conductor into "generic" routing, which may not be optimal for Wix sites. The demo.py hardcodes `"platform": "wix"` to bypass this, but production code cannot.

**Phase 1 Fix:**
1. Add `wixstudio.com` to Wix URL pattern list
2. When URL confidence < 0.5, fetch HTML and check for Wix-specific attributes (`data-wix`, `wix-` class names, meta generator tag)
3. If platform is "generic" due to detection failure, lower routing confidence to trigger LLM review

### 2. Routing Confidence vs. Reality
**Observation:**
The `routing_heuristics` returned `confidence: 1.0` for the `(generic, generic)` pair.
**Analysis:**
While the confidence is high for the *rule*, the rule itself is a fallback. The system correctly identified that it didn't know the platform, but it didn't flag this as "low confidence" to the user or trigger an override.
**Recommendation:**
- The `Router` should distinguish between "High confidence in a specific rule" vs. "High confidence in a fallback rule".
- If the platform is "generic" due to detection failure, the routing confidence should be artificially lowered to trigger LLM review.

### 3. OpenCode Invocation (Infrastructure)
**Status:** ✅ FIXED

**Root Cause:**
1. Multi-line prompt started with newline, causing OpenCode to see empty message
2. Windows encoding issue reading stderr (cp1252 codec couldn't decode some characters)
3. Wrong CLI syntax (using `--prompt` flag which doesn't exist for `opencode run`)

**Fixes Applied:**
- `tools/opencode.py`: Prompt now starts with actual text, not leading newline
- `tools/opencode.py`: Added `encoding='utf-8', errors='replace'` to subprocess.run()
- Verified: OpenCode now executes correctly and returns structured JSON

**Test Result:**
```
$ python -c "from tools.opencode import invoke_opencode; print(invoke_opencode('Create hello world HTML', {}, '.'))"
Created hello.html with basic HTML structure containing a heading with "Hello World" text.
```

**Remaining Consideration:**
OpenCode subprocess still can't participate in state machine directly. Consider wiring as LangGraph tool in Phase 1+.

### 4. Trace Quality
**Observation:**
The trace output is clean and readable.
**Verdict:** Pass. The `[OK]` format works well on Windows CLI.

## Next Steps (Phase 1)
1.  **Fix Platform Detection:** Add HTML fetching to `platform_detector` for custom domains.
2.  **Improve Routing Logic:** Lower confidence score when platform is "generic" due to detection failure.
3.  **Run Full Migration:** Execute the full pipeline on this site once Phase 1 (real scraping + memory) is complete to generate the first high-quality memory entry.

## Artifacts
- `smoke_test_output.txt`: Contains the raw trace and the prompt sent to OpenCode.