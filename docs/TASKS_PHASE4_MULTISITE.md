# Phase 4: Multi-Site Builder + Quality Gates + Self-Improvement Loop

**Version:** 1.0
**Status:** In Progress
**Last Updated:** 2026-05-21
**Branch:** `feature/phase1-meta-detector`
**Owner:** Elyra Team

> **Normative model:** see [`AGENTS.md`](../AGENTS.md) for the agent vs. tool decision rule. This doc assumes you already know what an "agent" is in Elyra (a persona `.md` invoked via Kilo CLI, not an MCP server). The scraper is the canonical worked example.

---

## Goal

Build a production-grade, multi-site web creation pipeline with:
- Isolated output per site (`sites/[site-slug]/`)
- Hard quality gates (build success, Impeccable, visual fidelity)
- Two-persona flow: UI Designer (with Google Stitch) → Builder (with Impeccable)
- Post-run self-improvement loop (Gap Ledger + Elyra Engineer → persona PRs)

---

## Architecture Decisions

### Output Isolation
- All build output goes to `sites/[site-slug]/` (e.g., `sites/merimee-solutions/`)
- Each site directory contains: `app/`, `components/`, `public/`, `package.json`, `build-manifest.json`, `visual-spec.json`, `impeccable-report.json`
- `site-slug` derived from `ContentRecommendation.site_name` (lowercase kebab-case)

### Two-Persona Handoff
```
SiteUnderstanding → Architect → Marketing → Designer (Stitch) → Builder (Impeccable) → Deploy
```
- **UI Designer**: Consumes `SiteUnderstanding` + `ContentRecommendation` + `BrandSpec`, invokes Stitch MCP, produces lightweight `VisualDirection` artifact
- **Builder**: Consumes `SiteUnderstanding` + `SiteArchitecture` + `ContentRecommendation` + `VisualDirection`, generates Next.js code, invokes Impeccable, writes to `sites/[site-slug]/`

### Quality Gates (Post-Build, Deterministic)
Gates run AFTER Builder writes code — NOT inside the Kilo LLM call:
- `npm run build` exits 0
- Impeccable audit passes (no high-severity violations)
- Token fidelity check (100% BrandSpec + VisualDirection usage)
- Accessibility scan (WCAG AA minimum)
- `quality_gate.py` script updates `BuildManifest` with `build_success`, `impeccable_report`, `quality_gates_passed`

### Self-Improvement Loop
- **Gap Ledger**: Structured log of data extraction gaps, visual/implementation gaps, and gate failures
- **Elyra Engineer**: Aggregates Gap Ledger entries + BuildManifest patterns, generates persona improvement PRs
- **Human review gate**: All persona changes go through GitHub PR (approve/reject)
- Gap Ledger v1 scope: data extraction gaps + visual/implementation gaps only (strategic gaps in v2)

### MCP Integration
Both Impeccable and Google Stitch registered as MCP servers in Kilo config:
- **Impeccable**: Used by Designer (visualization/shape) and Builder (audit/critique/optimize)
- **Google Stitch**: Used exclusively by Designer for visual brand direction and page layouts

---

## Prioritized Steps

### Step 1 — Output Isolation
- [x] Update `skills/agentic/builder_agent.py` to write to `sites/[site-slug]/`
- [x] Update `builder_specialist.md` "Code Output" section to reference `sites/[site-slug]/`
- [x] Move existing Merimee build to `sites/merimee-solutions/`
- [x] Update `memory/site_builds/` manifest to reference new `output_dir`
- [x] Add `output_dir` field to `BuildManifest` Pydantic model in `models/site_schemas.py`

### Step 2 — Register MCPs
- [x] Register Google Stitch MCP in Kilo config (`@_davideast/stitch-mcp`)
- [x] Register Impeccable via local install in `.kilo/node_modules` (not npx, since `impeccable` is a CLI tool, not an MCP server)
- [x] Verify Impeccable is working: `.kilo/node_modules/.bin/impeccable detect` runs successfully
- [ ] Verify Stitch MCP is accessible after Google auth (stitch server shows "Connection closed" — needs auth)
- [ ] Stitch requires Google Cloud auth: `gcloud auth login` or set `GOOGLE_APPLICATION_CREDENTIALS`

### Step 3 — Update UI Designer Persona
- [x] Updated `registry/personas/ui_designer.md` with Stitch MCP tool references
- [x] Added Impeccable usage instructions (`impeccable.detect`, `impeccable.skills`)
- [x] Added VisualDirection artifact schema (page_layouts, typography_hierarchy, motion_class_map)
- [x] Added Stitch MCP workflow section (when available)
- [x] Updated `registry/personas/builder_specialist.md` with Impeccable invocation instructions
- [x] Add `VisualDirection` Pydantic model to `models/site_schemas.py`
- [x] Create `skills/agentic/designer_agent.py` (thin glue for UI Designer)
- [x] Define lightweight `VisualDirection` schema (delta on BrandSpec only)

### Step 4 — Evolve Migration Orchestrator
- [x] Extend `registry/personas/migration_orchestrator.md` with Manager responsibilities (Gap Ledger, request-more-data, concurrent planning handoff)
- [x] Gap Ledger handling documented
- [x] Request-more-data protocol documented
- [x] Concurrent planning handoff logic documented (Designer + Architect + Marketing loop)

### Step 5 — Create quality_gate.py
- [x] Create `quality_gate.py` as standalone script
- [x] Runs: `npm run build` + Impeccable audit + token fidelity check + accessibility scan (skipped — requires Playwright)
- [x] Updates `BuildManifest` in place with `build_success`, `impeccable_report`, `quality_gates_passed`
- [x] Fail fast on hard gate failure

### Step 6 — Define VisualDirection Schema
- [x] Add `VisualDirection` model to `models/site_schemas.py`
- [x] Update `ui_designer.md` to produce it
- [x] Update `builder_specialist.md` to consume it as authoritative visual overlay

### Step 7 — Create Elyra Engineer
- [x] Create `registry/personas/elyra_engineer.md` (persona charter)
- [x] Create `elyra_engineer.py` (thin Python glue, calls Kilo)
- [x] Pattern: same as designer_agent.py / builder_agent.py
- [x] Aggregates Gap Ledger + BuildManifest patterns → persona improvement PRs

### Step 8 — Wire Gap Ledger
- [x] Create `memory/gap_ledger.py` with JSONL writer
- [x] Instrument `ui_designer` and `builder_specialist` to write Gap Ledger entries (on failure/request-more-data)
- [x] Elyra Engineer consumes Gap Ledger for pattern detection
- [x] `memory/gap_ledger/` directory created
- [x] Elyra Engineer creates GitHub PR for persona improvement candidates

---

## Key Files

### To Modify
| File | Change |
|------|--------|
| `skills/agentic/builder_agent.py` | Write to `sites/[site-slug]/`, accept `visual_spec_id` |
| `registry/personas/builder_specialist.md` | 4-artifact contract, hard gates, VisualDirection consumption |
| `registry/personas/ui_designer.md` | Stitch MCP + Impeccable usage, VisualDirection production |
| `registry/personas/migration_orchestrator.md` | Manager evolution (Gap Ledger, request-more-data, concurrent planning) |
| `models/site_schemas.py` | Add `VisualDirection` model |
| `kilo.json` / `.kilo/` config | Register Stitch + Impeccable MCPs |

### To Create
| File | Purpose |
|------|---------|
| `quality_gate.py` | Post-build deterministic gate runner |
| `skills/agentic/designer_agent.py` | Thin glue for UI Designer + Stitch |
| `registry/personas/ui_ux_designer.md` | NEW persona charter (or heavily update `ui_designer.md`) |
| `elyra_engineer.py` | Thin glue for Elyra Engineer |
| `memory/gap_ledger/` | Gap Ledger artifact storage |

### Reference (Read-Only)
| File | Purpose |
|------|---------|
| `models/site_schemas.py` | BrandSpec, BuildManifest, ContentRecommendation |
| `docs/NORTH_STAR.md` | Vision and phasing |
| `docs/ARCHITECTURE.md` | Detailed architecture reference |

---

## How to Resume a New Session

1. Read this file: `docs/TASKS_PHASE4_MULTISITE.md`
2. Read current `docs/ARCHITECTURE.md` for context
3. Check `.kilo/plans/` for any in-progress session plans
4. Check `memory/site_builds/` for existing build manifests
5. Run `python builder.py --list` to see available artifacts
6. Pick up from the nearest incomplete step above

---

## Success Criteria

- [ ] New site built with `python builder.py [site_id]` produces site in `sites/[site-slug]/`
- [ ] `npm run build` succeeds in generated site directory (hard gate)
- [ ] Impeccable audit passes with no high-severity violations
- [ ] 100% of colors, typography, spacing from BrandSpec tokens
- [ ] UI Designer produces `VisualDirection` for each site
- [ ] Builder consumes `VisualDirection` and implements faithfully
- [ ] Gap Ledger entries written on failures
- [ ] Elyra Engineer generates persona improvement PR from Gap Ledger + BuildManifest patterns
- [ ] Human reviews and merges/rejects persona PR
- [ ] Full pipeline tested on 2+ sites end-to-end

---

## Anti-Patterns to Avoid

- **No new Pydantic models** unless strictly necessary (prefer extending existing)
- **No hard gates inside Kilo LLM call** — keep LLM focused on generation
- **No new persona files** unless existing ones genuinely cannot be evolved
- **No auto-merge of persona changes** — always human review gate
- **No separate `impeccable.py` skill** — Impeccable is an MCP tool available to all personas, not a wrapped skill
