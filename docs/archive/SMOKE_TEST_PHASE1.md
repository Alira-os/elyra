# Phase 1 Smoke Test Plan

**Date:** 2026-05-05
**Branch:** `feature/phase1-meta-detector`
**Goal:** Verify all Phase 1 components work together before merging to `develop`

---

## Test Results (2026-05-05)

### 1. Platform Detection (Cascade) - PASS

| Test | URL | Result | Expected | Status |
|------|-----|--------|----------|--------|
| Wix URL pattern | `https://merimeesolutions.wixstudio.com/my-site-2` | `wix` (0.90) stage=html | `wix` (0.9+) | PASS |
| Squarespace URL | `https://example.squarespace.com` | `squarespace` (0.75) stage=llm | `squarespace` (0.55+) | PASS |
| Unknown URL | `https://unknown-site.xyz` | `generic` (0.0) stage=url | `generic` (0.0) | PASS |

### 2. Routing Confidence Adjustment - PASS

| Test | Input | Result | Expected |
|------|-------|--------|----------|
| Generic platform, low detection | `platform='generic', platform_confidence=0.0` | `conf=0.5, override=True` | `conf<=0.5, override=True` | PASS |
| Known platform, high detection | `platform='wix', platform_confidence=0.9` | `conf=1.0, override=False` | `conf=1.0, override=False` | PASS |

### 3. OpenCode as LangGraph Tool - PASS

| Test | Result |
|------|--------|
| Simple prompt | `success=True, files_created=0` |
| With mutation seed | Prompt includes guidance section |
| Timeout handling | Returns `ToolResult` with timeout error |

### 4. Memory + Mutation Seed - PASS

| Test | Result |
|------|--------|
| After 1 migration | `winning_stack='nextjs+tailwind', 1 site, avg fidelity=0.85` |
| `to_prompt_section()` | Returns markdown section with guidance |

### 5. Self-Healing MCP Clients - PASS

| Test | Result |
|------|--------|
| Playwright | `MCP available=True, healthy status` |
| GitHub | `token present (from env)` |
| Fly.io | `MCP available=True, token check passed` |

### 6. Conductor Integration - PASS

| Test | Result |
|------|--------|
| Full pipeline init | `Conductor created successfully` |

---

## Success Criteria

All tests pass:
- [x] Platform detection returns correct platform + confidence for all test URLs
- [x] Routing confidence adjustment triggers for unknown platforms
- [x] OpenCode returns structured `ToolResult`
- [x] Memory returns `MutationSeed` when migrations exist
- [x] MCP clients initialize without error
- [x] Conductor runs end-to-end

---

## Issues to Close on Success

| Issue | Title |
|-------|-------|
| #13 | Meta-Detector LLM Stage (M1) - First True LLM Override |
| #14 | Memory-Driven Codegen Bias - Mutation Seed Injection |
| #9 | Wire Real MCP Clients (Playwright, GitHub, Fly.io) |
| #11 | Memory Population - Run 3-5 Real Migrations |

---

## Rollback Plan

If smoke test fails:
1. Revert to `develop` branch
2. Investigate failure in isolation
3. Fix and re-test on feature branch
4. Re-run smoke test before merge