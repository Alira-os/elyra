# Phase 0 — Retrospective (Updated 2026-05-05)

**Status:** Complete but flawed — implementation pattern was wrong

---

## What Was Built

1. Conductor orchestration with phase sequence
2. Routing heuristics with table-based lookup
3. Python-based "MCP clients" in `tools/mcp/` — **THIS WAS WRONG**
4. Memory layer (SQLite) with mutation seeds
5. Persona markdown files in `registry/personas/`
6. Skill markdown + Python callables in `skills/`

---

## What Was Wrong: The MCP Pattern

### ❌ Wrong Pattern (What We Built)

```
Python App (Elyra)
├── tools/mcp/playwright.py  ← This is NOT an MCP server
│   └── Python wrapper that calls npx @playwright/mcp
└── This is middleware we invented
```

**Problem:** We created Python wrappers and called them "MCP clients." But real MCP servers are npm packages that implement the MCP protocol. OpenCode connects to them directly via its MCP configuration, not through our Python code.

### ✅ Correct Pattern

```
OpenCode (running with software architect persona)
├── MCP config points to real MCP servers
│   ├── @playwright/mcp (real npm package)
│   ├── @github/mcp-server (real npm package)
│   └── etc.
└── OpenCode calls MCP tools directly

Elyra's role:
├── Define personas (markdown guidance for the LLM)
├── Define skills (markdown + Python callables)
└── Define Pydantic schemas for structured output
```

**Elyra does NOT implement MCP clients.** Elyra defines how the LLM should USE the MCP tools.

---

## What We Need Instead

### Phase 0.5: Scraper Focus

**Goal:** Get ONE thing working perfectly — the agentic scraper.

**Pattern:**
1. Define `scraper_specialist` persona (markdown)
2. Define Pydantic schemas for `SiteUnderstanding`
3. Wire real `@playwright/mcp` to OpenCode
4. Test: "Go scrape site X and return its architecture"

**If this works:** We have a foundation we can build on.
**If this doesn't:** We know the pattern before scaling.

---

## Phase Definitions (Corrected)

### Phase 1: Agentic Scraper (CURRENT)

**Goal:** Given any URL, produce a rich `SiteUnderstanding` via OpenCode + real MCP + persona guidance.

**Success Criteria:**
- OpenCode can use `@playwright/mcp` to scrape any site
- `scraper_specialist` persona guides the LLM to reason deeply
- Output is valid Pydantic `SiteUnderstanding` with sitemap, tech stack, migration opportunities

**Out of scope:** Everything else (codegen, deploy, memory, etc.)

### Phase 2: Intake Agent

**Goal:** Build the onboarding/inquiry agent that asks questions and produces structured task_context.

### Phase 3: Rebuild Agent

**Goal:** Given SiteUnderstanding, rebuild the site with modern stack.

### Phase 4: Deploy Agent

**Goal:** Deploy the rebuilt site to hosting.

### Phase 5+: Memory + Debate Arena

**Goal:** Compound intelligence over multiple migrations.

---

## Issues with Current Code

| File | Issue | Action |
|------|-------|--------|
| `tools/mcp/playwright.py` | Not a real MCP server - Python wrapper | DELETE or refactor to thin wrapper for local dev only |
| `tools/mcp/fetch.py` | Not using real MCP | DELETE or keep as fallback only |
| `tools/mcp/github.py` | Same | DELETE or refactor |
| `tools/mcp/fly.py` | Same | DELETE or refactor |
| `conductor/orchestrator.py` | Premature orchestration | PAUSE - focus on scraper first |

---

## Correct Architecture for Phase 1

```
elyra/
├── registry/
│   ├── personas/
│   │   └── scraper_specialist.md  ← Persona guidance (markdown)
│   └── skills/
│       └── site_interpreter.md   ← How to produce SiteUnderstanding
├── schemas/
│   └── site_understanding.py     ← Pydantic models
├── skills/
│   └── executable/
│       └── site_interpreter.py  ← Python callable (thin)
└── opencode/
    └── .mcp.json                ← MCP server configurations

OpenCode workspace:
├── Uses real MCP servers (@playwright/mcp, etc.)
├── Loads scraper_specialist persona
├── Produces SiteUnderstanding (Pydantic)
```

---

## Next Steps

1. **Delete** the fake MCP client files in `tools/mcp/`
2. **Create** proper MCP configuration for OpenCode
3. **Define** `SiteUnderstanding` Pydantic schemas
4. **Update** `scraper_specialist.md` persona
5. **Test** with real OpenCode + @playwright/mcp

---

## What We Keep

- `NORTH_STAR.md` — Vision is correct
- `docs/ARCHITECTURE.md` — Need to update MCP section
- `memory/` — Keep, will use later
- `registry/personas/` — Keep, this is the right pattern
- `skills/` — Keep, this is the right pattern