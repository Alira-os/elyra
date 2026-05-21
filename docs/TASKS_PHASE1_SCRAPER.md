# Phase 1 — Agentic Scraper (Kilo Code)

**Status:** Active  
**Focus:** One thing done exceptionally — fully agentic site understanding

---

## Core Philosophy (Kilo Code)

- Personas are markdown charters (exactly like custom modes).
- Real intelligence = LLM reasoning guided by persona.
- Python = thin glue only (MCP calls + prompt assembly + Pydantic).
- No imperative parsing or traditional scraper logic.
- We replicate how a human software architect works: load the persona, give it MCP tools + raw context, let it deeply reason.

---

## Primary Goal

Given any URL, return a production-grade `SiteUnderstanding` + rich `PageStructure[]` for every page that matches or exceeds the quality of manually prompting the best software architect persona in Kilo Code.

**Output must include:**
- Platform detection with confidence
- Complete site map (pages discovered, navigation structure)
- Detailed per-page `PageStructure` (headings, components, images, links, forms, clean text, SEO, LLM notes)
- Strategic overview (content philosophy, migration opportunities, recommendations)
- Full reasoning trace

**Measurement of Done**
- Works reliably on 5+ real sites (Wix, Squarespace, WordPress, custom)
- 100% valid Pydantic output on every run
- Human review quality ≥ 85%
- Clean invocable entrypoint (CLI or function)

---

## What We Build (Tight Scope)

| Artifact | Location | Purpose |
|----------|----------|---------|
| Schemas | `models/site_schemas.py` | `SiteUnderstanding` + `PageStructure` (Pydantic) |
| Persona | `registry/personas/scraper_specialist.md` | Pure LLM charter (no code examples) |
| Skill | `skills/agentic/site_interpreter.py` | Thin glue: persona + raw MCP → validated output |
| MCP Config | `kilocode/.mcp.json` | Real Playwright + Fetch MCP servers |
| Entrypoint | `scrape.py` (or CLI) | `scrape(url) → SiteUnderstanding` |

---

## Explicitly Out of Scope (This Phase)

- Conductor orchestration
- Code generation / rebuilding
- Deployment
- Memory crystallization
- Debate Arena
- Full migration pipeline

---

## Tasks (Prioritized)

1. **Finalize Pydantic Schemas** (`models/site_schemas.py`)
   - `SiteUnderstanding` (strategic overview + pages[])
   - `PageStructure` (granular per-page detail)
   - Add reasoning_trace, warnings, recommendations

2. **Rewrite `scraper_specialist.md`** as pure charter
   - World-class web archaeologist + software architect
   - Mandate deep MCP exploration + step-by-step reasoning
   - Strict instruction: output ONLY valid JSON matching schema

3. **Create Kilo Code MCP Config** (`kilocode/.mcp.json`)
   - Wire `@playwright/mcp@latest` and fetch MCP

4. **Implement `site_interpreter` skill**
   - Load persona
   - Feed raw MCP artifacts + schema instruction to LLM
   - Validate and return `SiteUnderstanding`

5. **Create thin `scrape(url)` entrypoint**
   - Orchestrates MCP sensory → interpreter → validated output

6. **Remove obsolete imperative MCP clients**
   - Delete `tools/mcp/playwright.py`, `fetch.py`, etc.

7. **Test on 5+ real sites + human review**

---

## GitHub Issues (Scraper Phase)

| # | Title | Priority |
|---|-------|----------|
| 20 | Create SiteUnderstanding + PageStructure Pydantic schemas | P0 |
| 21 | Rewrite scraper_specialist.md as pure Kilo persona charter | P0 |
| 22 | Create kilocode/.mcp.json with Playwright + Fetch | P0 |
| 23 | Implement site_interpreter skill (thin glue) | P1 |
| 24 | Build scrape(url) entrypoint / CLI | P1 |
| 25 | Delete fake MCP client files (tools/mcp/*) | P2 |
| 26 | Test scraper on 5+ real sites with human review | P1 |

---

**Reference:** Kilo Code custom modes + MCP integration patterns
