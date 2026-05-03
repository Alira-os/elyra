# Phase 0 Retrospective — MVP Scaffolding Complete

**Status:** Completed
**Completed:** 2026-05-02
**Duration:** ~1 session (~2 hours)

---

## What We Built

Phase 0 MVP scaffolding — the minimum lovable product that demonstrates the Conductor + memory pattern works.

### Deliverables Completed

| Component | Files | Status |
|-----------|-------|--------|
| **4 Persona Definitions** | `registry/personas/{migration_orchestrator,onboarding_specialist,scraper_specialist,deploy_specialist}.md` | ✅ Complete |
| **6 Skill Pairs** | `skills/{memory_query,platform_detector,routing_heuristics,lighthouse,npm_audit,seo_optimizer}.md` + `skills/executable/*.py` | ✅ Complete |
| **Registry Query Interface** | `registry/registry.py` | ✅ Complete |
| **Tools** | `tools/opencode.py`, `tools/mcp/{playwright,fetch,github,netlify}.py` | ✅ Complete |
| **SQLite Memory Layer** | `memory/sqlite/schema.sql`, `memory/sqlite/crud.py`, `memory/memory.py` | ✅ Complete |
| **Conductor Skeleton** | `conductor/{orchestrator,routing,state_machine,memory_client,trace,security_gate}.py` | ✅ Complete |
| **Onboarding Flows** | `onboarding/flows/{adaptive,questions}.py` | ✅ Complete |
| **GitHub Actions CI/CD** | `.github/workflows/{ci,deploy-staging,semgrep}.yml` | ✅ Complete |
| **Demo + Test Sites** | `conductor/demo.py`, `examples/test_sites/` | ✅ Complete |

**Total files created:** ~40

---

## What We Learned

### 1. Pattern: Skills = Markdown Guidance + Python Callable Pair

The markdown provides rich context (when to call, edge cases, what passes to next persona) while the Python callable provides executable logic. This separation allows:
- Personas to reference markdown for guidance
- Conductor to invoke callable without parsing markdown
- Easy testing of executable in isolation

**Lesson:** Keep markdown focused on "when/why" and callable focused on "how". Don't duplicate logic.

### 2. Pattern: Stub Everything in Phase 0, Interface First

Every MCP client (Playwright, Fetch, GitHub, Netlify) is stubbed in Phase 0. The interface is correct, but execution returns mock data. This allowed:
- Complete scaffolding without external dependencies
- Testing import chains without network access
- Clear upgrade path for Phase 1

**Lesson:** Stub with print statements so you can see what's being called. E.g., `[GitHub MCP Stub] Would push 5 files to https://github.com/...`

### 3. Pattern: Unicode Characters Break Windows CLI

Trace output used ✓ ✗ → symbols which encode fine in UTF-8 but fail on Windows `cp1252` console. Fixed by using ASCII alternatives: `[OK] [X] ->`.

**Lesson:** Always use ASCII in code that will output to console. Use Unicode only in files that won't be printed.

### 4. Pattern: Platform Detection Confidence Threshold

Platform detector achieved 0.4 confidence for standard URLs (e.g., `example.wixsite.com`) because detection relies on HTML indicators which aren't fetched by default. URL-based detection alone isn't sufficient for custom domains.

**Lesson:** For Phase 1, add HTML-based detection fallback when URL doesn't contain obvious platform indicators.

### 5. Pattern: Conductor is the Orchestrator, Not the Executor

The Conductor delegates all real work:
- Codegen → OpenCode tool
- Scraping → scraper_specialist (calls Playwright/Fetch MCPs)
- Deployment → deploy_specialist (calls GitHub/Netlify MCPs)

The Conductor's job is routing, state management, and quality gates.

**Lesson:** Keep Conductor thin. If you're writing business logic in the Conductor, it belongs in a persona or skill.

### 6. Pattern: Trace Output is the User's View of the System

Clean bullet-pointed trace (`[OK] Routing: wix portfolio -> [...]`) is what the user sees. It's not debugging output — it's the product. A clean trace with 15-20 lines beats verbose logging.

**Lesson:** Design trace output first. Everything else is infrastructure to produce that trace.

### 7. Pattern: Phase Artifacts Live in Pairs

Every phase should produce:
1. `NORTH_STAR.md` — updated with phase learnings
2. `PHASE_N_RETROSPECTIVE.md` — what we built, what we learned, what changed

The sprint backlog (TASKS_PHASE0.md) is temporary — it lives in the retrospective at phase end, then gets cleaned up.

**Lesson:** This pattern keeps the repo clean while capturing institutional memory.

---

## Architecture Changes from Initial Design

### 1. Memory Layer Simplified

Original design had separate CRUD modules (`migrations.py`, `debates.py`, `heuristics.py`) inside `memory/sqlite/`. Implementation consolidated into single `crud.py` with classes (`MigrationCRUD`, `DebateCRUD`, etc.) accessed via `Memory` wrapper class.

**Why:** Cleaner import structure, less file navigation.

### 2. State Machine Uses TypedDict + Enum

Instead of full LangGraph state machine in Phase 0, we used `TypedDict` + Python `Enum` for phases. This is lighter weight and can be upgraded to full LangGraph in Phase 1.

**Why:** LangGraph adds complexity. Get it working first, upgrade later.

### 3. Routing Heuristics in Separate Skill

Instead of hard-coding routing in Conductor, routing rules are in `skills/executable/routing_heuristics.py` as a skill pair. This allows:
- Conductor to call `get_routing_sequence()` as a skill
- Routing rules to be updated without Conductor changes
- Clear interface for LLM override to modify

**Why:** Separation of concerns. Routing is a skill, not core Conductor logic.

---

## Fidelity Trends

No real migrations run yet (Phase 1 task). Current scaffolding produces:
- Mock fidelity estimates
- Stub security gate results
- Mock deploy URLs

Once real migrations run, we'll track:
- Content coverage % per platform
- Lighthouse scores achieved
- Routing sequence adjustments made

**Target for Phase 0 completion:** ≥ 55% fidelity on first real migration.

---

## Known Gaps (Not Blockers for Phase 1)

These are known and documented. They don't block Phase 1 since we have clear upgrade paths:

| Gap | Impact | Resolution |
|-----|--------|------------|
| Platform detector lower confidence on custom domains | May route to generic | Add HTML detection in Phase 1 |
| OpenCode invoke is subprocess, not tool-bound | Can't participate in state machine | Wire as LangGraph tool in Phase 1 |
| Memory returns empty (LanceDB stubbed) | No routing improvement yet | Populate SQLite + wire LanceDB in Phase 1.5 |
| No Debate Arena | Can't learn from failures | Phase 1 feature |
| Playwright stubbed | Can't scrape real JS sites | Wire MCP in Phase 1 |

---

## Architecture Corrections (Post-Phase 0 Review)

After Phase 0 completion, a code review identified structural issues that were corrected:

### 1. Directory Duplication Fixed

**Problem:** `personas/` (root) and `registry/personas/` created confusion and maintenance burden.

**Fix:** Removed `personas/` root directory entirely. Single source of truth is now `registry/personas/` (markdown definitions) + `registry/registry.py` (loader).

**Also removed:**
- `registry/tools/` (empty)
- `registry/skills/` (empty, skills live at root `skills/`)

**Result:** Clean single-source-of-truth for all persona and skill definitions.

### 2. MCP Stubs Marked as Phase 0 Scaffolding

**Problem:** It wasn't clear that `tools/mcp/*.py` were Phase 0 stubs, not production code.

**Fix:** Added header comments to all MCP stub files:

```python
"""
Playwright MCP Client Stub

**Phase 0 Status:** STUB — Interface only, returns mock data.
**Phase 1+ Target:** Replace with official MCP client using mcp Python SDK.
"""
```

**Files updated:**
- `tools/mcp/playwright.py` — STUB
- `tools/mcp/fetch.py` — PARTIAL (urllib works, not MCP)
- `tools/mcp/github.py` — STUB
- `tools/mcp/netlify.py` — STUB

### 3. ARCHITECTURE.md Created

**Problem:** NORTH_STAR.md contains both vision and implementation details, making it too dense.

**Fix:** Created `docs/ARCHITECTURE.md` as a separate, detailed implementation guide that:
- Shows containerized deployment topology
- Documents MCP integration pattern (client vs server)
- Provides LangGraph evolution path
- Includes docker-compose.yml target
- Defines Phase 1 upgrade checklist

**Relationship:**
- NORTH_STAR.md = Vision + phasing (stable, rarely changes)
- ARCHITECTURE.md = Implementation details (evolves as we learn)

---

## What We'd Do Differently

### 1. Start with Real Site Testing Earlier

We built all scaffolding without testing on a real site. Better approach: build one persona/skill, test on real site, repeat. This would have caught platform detector confidence issues earlier.

### 2. Define Trace Format Before Building Conductor

We designed trace output at the end. Better: define the exact trace format first, then build everything to produce that trace. Trace is the user-facing product, so it should drive design.

### 3. MCP Stubs Should Log What They'd Do

Current stubs just return mock data. Better: print `[MCP Stub] Would call create_repo(name='elyra-xxx')` so you can see the interface being used without running real MCP.

---

## Appendix: Completed Task List (Archived)

The original TASKS_PHASE0.md contained 11 sections with 37 checkbox items. All were completed:

- [x] 1.4 Add `tests/` and `examples/test_sites/` directories
- [x] 2.1-2.4 4 persona definitions (≥200 words each)
- [x] 3.1-3.6 6 skill pairs (markdown + Python callable)
- [x] 4.1 registry.py with load_persona/skill/tool + list functions
- [x] 5.1-5.5 tools/opencode.py + 4 MCP client stubs
- [x] 6.1-6.5 SQLite schema + CRUD + unified Memory interface
- [x] 7.1-7.5 Conductor orchestrator, state_machine, routing, memory_client, trace
- [x] 8.1-8.3 Adaptive onboarding (5 questions max, structured output)
- [x] 9.1 SecurityQualityGate class
- [x] 10.1-10.4 GitHub Actions CI/CD workflows
- [x] 11.1-11.3 Demo script + test sites directory

**Verification commands:**
```bash
python -c "from registry.registry import list_personas; print(list_personas())"
python -c "from conductor.orchestrator import Conductor; print('Conductor loaded')"
python -c "from memory.memory import Memory; m = Memory(); print(m.query_similar_sites('wix', 'portfolio'))"
```

All pass.

---

## Next Steps

Phase 1 is already scoped in NORTH_STAR.md. Top priorities:

1. **End-to-end test** — Run demo.py on a real Wix/Squarespace site, verify clean trace
2. **Wire Playwright MCP** — Real scraping for JS-heavy sites
3. **Wire GitHub + Netlify MCPs** — Real deploy pipeline
4. **Implement memory queries** — Populate SQLite, verify routing uses memory

See GitHub Issues (when created) for detailed task breakdown.

---

## Reference

- Architecture (target state): `docs/ARCHITECTURE.md`
- Vision + phasing: `docs/NORTH_STAR.md`
- This retrospective follows the **Phase Artifact Pattern**: every phase produces NORTH_STAR updates + PHASE_N_RETROSPECTIVE