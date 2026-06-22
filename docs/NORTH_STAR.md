# Elyra — AI Website Creation & Migration Engine

**Version:** 1.0
**Last Updated:** 2026-05-01
**Status:** Planning

---

> **Start here for the agent vs. tool model:** [`AGENTS.md`](../AGENTS.md). This document is the *why*; `AGENTS.md` is the *what* (decision rule, directory layout, worked example). If they ever disagree, `AGENTS.md` wins.

## Executive Summary

Elyra is an AI-native website creation and migration engine that takes a fundamentally different approach from traditional automation: instead of a rigid pipeline, Elyra uses a **Guided Dynamic Orchestration** pattern where a meta-agent (Conductor) intelligently routes between specialized personas, learns from every interaction, and compounds in capability over time.

**Core Principle:** Memory is a first-class citizen. Every migration or site build produces lessons that make the next one better. Generic "give AI tools" doesn't have this. Elyra does.

**Why Elyra Wins:** Unlike CrewAI/AutoGen (rigid pipelines), Replit Agent (no memory), or v0/Bolt.new (one-shot), Elyra compounds. Each migration makes the next smarter. The Conductor doesn't just execute — it learns routing patterns, detects anti-patterns, and evolves. After 5 real migrations, the routing should visibly outperform any generic AI codegen approach on the same site.

**Target Users:** Anyone who needs to migrate legacy sites (Wix, Squarespace, WordPress) or build new sites, with the intelligence and quality of an expert web agency.

---

## Platform Vision

Elyra is currently focused on **site creation and modernization** — the "Site OS" layer. This is the foundation for a larger vision:

### Short-term (Phase 0-2): Site OS
- AI-native website migration and creation
- Compounding memory that improves every migration
- Unified Conductor + MCP layer for extensibility

### Long-term (Phase 3+): Business OS Platform
Elyra evolves into a family of specialized agents sharing:
- **Unified memory layer** (SQLite + LanceDB across all agents)
- **Shared MCP layer** (Playwright, Fetch, GitHub, fly.io, and more)
- **Cross-domain intelligence** (marketing agent learns from sales agent's learnings)

```
┌─────────────────────────────────────────────────────────────┐
│                    Elyra Business OS                        │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Site      │  │  Marketing  │  │   Sales     │        │
│  │   Agent     │  │   Agent     │  │   Agent     │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│         │                 │                 │              │
│         └─────────────────┴─────────────────┘                │
│                    Shared Memory + MCP Layer               │
└─────────────────────────────────────────────────────────────┘
```

**Note:** Phase 3+ remains aspirational. Phase 0-2 focus is fully on Site OS first.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Human User                              │
│              "Build a t-shirt shop site for my brand"         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Onboarding Specialist                        │
│           Adaptive interview (5-10 questions)                 │
│           Produces structured task context                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Conductor (Meta-Agent + State Machine)            │
│   - Queries memory for similar past sites                    │
│   - Applies heuristic routing + LLM override                │
│   - Dynamically selects personas and skills                  │
│   - Handles backward routing on failures                    │
│   - Invokes OpenCode for heavy codegen                     │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Scraper       │   │ Codegen Crew  │   │ Deploy        │
│ Specialist    │   │ Lead          │   │ Specialist    │
│               │   │               │   │               │
│ - Playwright │   │ - Frontend   │   │ - GitHub     │
│ - Fetch      │   │ - Backend    │   │ - Fly.io     │
│               │   │ - Content    │   │ - Render     │
└───────────────┘   └───────────────┘   └───────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Security + Quality Gates                     │
│         npm audit │ Semgrep │ Lighthouse │ Dependency         │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Human Approval Gate                          │
│        Review staging preview + summary → Approve/Reject       │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Debate Arena + Memory                        │
│    Reflection crew → Structured lessons → Memory update       │
│    Next migration starts smarter                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
elyra/
├── conductor/              # Meta-agent, state machine, routing logic
│   ├── orchestrator.py     # Main Conductor class
│   ├── state_machine.py    # LangGraph-ready state machine
│   ├── routing.py          # Heuristic routing + LLM override
│   ├── memory_client.py     # Memory layer interface
│   ├── trace.py            # Clean bullet-pointed trace output
│   └── security_gate.py    # Security + quality gate
│
├── registry/               # Single source of truth for personas, skills, tools
│   ├── registry.py         # Loader: load_persona, load_skill, load_tool
│   └── personas/           # Markdown persona definitions (only)
│       ├── migration_orchestrator.md
│       ├── onboarding_specialist.md
│       ├── scraper_specialist.md
│       └── deploy_specialist.md
│
├── skills/                  # Skill definitions
│   ├── memory_query.md      # Markdown guidance
│   ├── platform_detector.md
│   ├── routing_heuristics.md
│   ├── lighthouse.md
│   ├── npm_audit.md
│   ├── seo_optimizer.md
│   └── executable/          # Python callables
│       ├── memory_query.py
│       ├── platform_detector.py
│       ├── routing_heuristics.py
│       ├── lighthouse.py
│       ├── npm_audit.py
│       └── seo_optimizer.py
│
├── tools/                   # Tool interfaces
│   ├── opencode.py         # OpenCode subprocess interface
│   └── mcp/               # MCP client interfaces
│       ├── playwright.py   # STUB: Phase 1+ real MCP client
│       ├── fetch.py        # PARTIAL: urllib, Phase 1+ MCP
│       ├── github.py       # STUB: Phase 1+ real MCP client
│       └── fly.io.py      # STUB: Phase 1+ real MCP client
│
├── memory/                 # Persistent memory layer
│   ├── sqlite/             # Structured metadata (migrations, debates, heuristics)
│   │   ├── schema.sql
│   │   └── crud.py
│   ├── vector/            # LanceDB for semantic similarity (stubbed Phase 0)
│   └── memory.py          # Unified memory interface
│
├── onboarding/              # Onboarding flows
│   └── flows/
│       ├── adaptive.py    # AdaptiveOnboarding class
│       └── questions.py    # Question templates
│
├── debate/                 # Debate Arena (Phase 1+)
│   └── templates/         # Structured debate templates
│
├── infra/                   # Infrastructure
│   └── github/            # GitHub Actions templates
│
├── .github/workflows/      # CI/CD
│   ├── ci.yml
│   ├── deploy-staging.yml
│   └── semgrep.yml
│
├── examples/               # Examples
│   └── test_sites/       # Test site configurations
│
└── docs/                   # Documentation
    ├── NORTH_STAR.md       # This file - vision + phasing
    ├── ARCHITECTURE.md     # Detailed implementation guide
    ├── RETROSPECTIVE_PHASE0.md
    └── ...
```

**Note:** `personas/` root directory has been removed. All persona definitions live exclusively in `registry/personas/` (markdown definitions) + `registry/registry.py` (loader).

---

## Core Personas

| Persona | Responsibility | Skills It Can Call | MCP/Tools |
|---------|---------------|-------------------|-----------|
| **migration_orchestrator** (Conductor) | Decides flow, queries memory, routes, handles uncertainty | All (meta) | All |
| **onboarding_specialist** | Adaptive requirements gathering | stack_intelligence, memory_query | Fetch |
| **scraper_specialist** | Extracts structure + content | content_philosopher, seo_optimizer | Playwright, Fetch |
| **stack_intelligence** | Chooses optimal modern stack | memory_query, context7 (Phase 2) | Context7 (Phase 2) |
| **codegen_crew_lead** | Coordinates frontend/backend/content | frontend_dev, backend_dev, accessibility_auditor, ui_polish, seo_optimizer | OpenCode |
| **security_auditor** | Security + quality gates (MVP-mandatory) | npm_audit, semgrep_scan, dependency_review, lighthouse | GitHub, npm_audit |
| **deploy_specialist** | GitHub repo + CI/CD + hosting | github_actions_setup, fly_deploy, render_deploy | GitHub, Fly.io, Render |
| **ui_polish** (Phase 2) | Visual/UX quality pass | lighthouse, impeccable | Impeccable, Stitch |

---

## Skills System

Skills are pairs of **markdown guidance** + **executable code**.

| Skill | Markdown (Guidance) | Executable | Called By |
|-------|---------------------|-----------|-----------|
| `memory_query` | How to query memory for similar sites | Python | Conductor, all personas |
| `platform_detector` | Detect Wix/Squarespace/WordPress from URL | Python | scraper_specialist |
| `routing_heuristics` | Get/update routing rules | Python | Conductor |
| `lighthouse` | Run Lighthouse audits | CLI | security_auditor, ui_polish |
| `npm_audit` | Check dependency vulnerabilities | CLI | security_auditor |
| `semgrep_scan` | SAST security scan | GitHub Actions | security_auditor |
| `accessibility_auditor` | WCAG 2.1 AA audit | axe-cli | codegen_crew_lead |
| `seo_optimizer` | Optimize content for SEO + AI | LLM prompt | scraper_specialist, codegen_crew_lead |
| `content_philosopher` (Phase 2) | Understand site "soul", rewrite for web + AI | LLM | scraper_specialist, codegen_crew |

---

## MCP Servers

| MCP Server | Purpose | Wired MVP? |
|-----------|---------|-----------|
| **Playwright** | Site structure extraction | ✅ Yes |
| **Fetch** | Clean content extraction | ✅ Yes |
| **GitHub** | Repo creation, CI/CD | ✅ Yes |
| **fly.io** | Deploy hosting | ✅ Yes |
| **Render** | Deploy hosting | ✅ Yes |
| **npm_audit** | Dependency scanning | ✅ Yes |
| **Context7** | Self-healing code gen | Phase 2 |
| **Impeccable** | UI polish | Phase 2 |
| **Google Stitch** | AI UI design | Phase 2 |

---

## Memory Layer (Hybrid - Phase 1+)

Production-grade hybrid memory supporting 50-100+ migrations with semantic search.

### SQLite Schema (Extended)

```sql
-- Migration history (extended)
CREATE TABLE migrations (
    id TEXT PRIMARY KEY,
    url TEXT,
    platform TEXT,  -- wix, squarespace, wordpress, generic
    task_type TEXT,  -- e-commerce, blog, portfolio, business
    stack_chosen TEXT,  -- JSON of stack decision
    fidelity_score REAL,
    routing_used TEXT,  -- JSON array of personas invoked
    outcome TEXT,  -- success, partial, failed
    -- New Phase 1+ columns:
    stage_history TEXT,  -- JSON array of stage transitions
    fidelity_history TEXT,  -- JSON array of fidelity scores per stage
    persona_versions TEXT,  -- JSON map of persona → version used
    decisions TEXT,  -- JSON array of architectural decisions
    site_architecture_id TEXT,  -- FK to site_architectures
    content_recommendation_id TEXT,  -- FK to content_recommendations
    production_url TEXT,  -- set after production deploy
    github_repo TEXT,  -- e.g. "Alira-os/saint-joseph-the-worker-academy"
    preview_url TEXT,  -- temporary preview URL
    preview_expires_at DATETIME,
    created_at DATETIME
);

-- Site architectures
CREATE TABLE site_architectures (
    id TEXT PRIMARY KEY,
    migration_id TEXT,
    source_url TEXT,
    target_stack TEXT,  -- JSON
    deployment_spec TEXT,  -- JSON of DeploymentSpec
    pages_spec TEXT,  -- JSON array of PageSpec
    components_spec TEXT,  -- JSON array of ComponentSpec
    ...
);

-- Content recommendations
CREATE TABLE content_recommendations (
    id TEXT PRIMARY KEY,
    migration_id TEXT,
    site_name TEXT,
    tone_of_voice TEXT,  -- JSON of ToneOfVoice
    page_strategies TEXT,  -- JSON array
    ...
);

-- Structured artifacts (lessons, anti-patterns)
CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    migration_id TEXT,
    artifact_type TEXT,  -- lesson, anti_pattern, routing_insight, deploy_result
    content TEXT,  -- JSON
    embedding_vector_id TEXT,  -- reference to LanceDB
    tags TEXT,  -- JSON array for filtering
    ...
);
```

### Vector Store (LanceDB)

Stores lesson embeddings for semantic similarity search:
- Lesson summaries
- What worked for specific platform/task combinations
- Anti-patterns
- Site summaries for recall ("what worked for classical schools?")

```python
# Example queries:
memory.query_lessons("trades gallery wix", tags=["gallery", "wix"])
# Returns: semantically similar lessons across all past migrations

lessons.log_lesson(
    migration_id="abc-123",
    lesson={"description": "Trades gallery component works well for wix portfolios"},
    tags=["wix", "portfolio", "trades", "gallery"]
)
```

### Hybrid Storage Layers

| Layer | Purpose | Technology | Retention |
|-------|---------|------------|-----------|
| Metadata + Provenance | Migration IDs, stage history, fidelity, decisions | SQLite | Permanent |
| Structured Artifacts | SiteUnderstanding, SiteArchitecture, ContentRecommendations | JSON files (git-tracked) | Permanent |
| Code Artifacts | Generated site + CI/CD workflows | Per-site Git repos (Alira-os org) | Permanent |
| Semantic Search | "Find all trades gallery migrations" | LanceDB | Permanent |
| Large Media | Original images, videos, PDFs | Fly.io Volumes or R2 (URLs in metadata) | As needed |

---

## Promotion Pipeline (Phase 1+)

Hardened flow from local build to production live:

```
Builder + SEO Specialist finish → Code pushed to Alira-os per-site repo
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  Kilo Code Reviewer + Security Agent               │
│  (GitHub Action on PR)                            │
└────────────────────┬────────────────────────────────┘
                    │ FAIL → Block + report
                    │ PASS
                    ▼
┌─────────────────────────────────────────────────────┐
│  Elyra SecurityQualityGate (REQUIRED status check) │
│  • Lighthouse performance ≥ 95 (raised from 85)     │
│  • Lighthouse accessibility ≥ 90                   │
│  • Lighthouse best-practices ≥ 90                   │
│  • Lighthouse SEO ≥ 90                             │
│  • npm audit: 0 critical                           │
└────────────────────┬────────────────────────────────┘
                    │ FAIL → Block + fix instructions
                    │ PASS
                    ▼
┌─────────────────────────────────────────────────────┐
│  Preview Deployment (7-day TTL)                    │
│  Temporary public URL + banner                      │
│  "This is a preview of the new {site} website"     │
└────────────────────┬────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────┐
│  Human Approval Gate (ONLY mandatory touchpoint)    │
│  "Good to go?" — PR comment / CLI / Slack          │
└────────────────────┬────────────────────────────────┘
                    │ REJECT → Return to Builder
                    │ APPROVE
                    ▼
┌─────────────────────────────────────────────────────┐
│  Production Deploy (Deploy Specialist)              │
│  • Creates/updates Fly app (org/region)            │
│  • Custom domain + SSL                              │
│  • Env vars + secrets                              │
│  • DNS update                                      │
│  • Mark "Production Live" in SQLite ledger         │
└─────────────────────────────────────────────────────┘
```

### GitHub Strategy

```
Alira OS (GitHub Organization) ← https://github.com/Alira-os
├── elyra                          ← Elyra project itself
├── saint-joseph-the-worker-academy  ← Per-site repos (created post-local-build)
├── merimee-solutions
├── chesterton-academy-akron
└── ... (one repo per migration/client)
```

**Repo creation timing:** Per-site repos created ONLY after local build succeeds (not pre-provisioned).

**Kilo tie-in:**
- Auto-trigger Kilo Code Reviewer on every PR
- Client portal via GitHub Discussions
- Branch protection + required status checks

---

## Routing System

### Heuristic Routing Rules

```python
ROUTING_RULES = {
    ("wix", "e-commerce"): [
        "onboarding_specialist",
        "scraper_specialist",
        "stack_intelligence",
        "codegen_crew_lead",
        "security_auditor",
        "deploy_specialist"
    ],
    ("wix", "portfolio"): [
        "onboarding_specialist",
        "scraper_specialist",
        "stack_intelligence",
        "codegen_crew_lead",
        "ui_polish",
        "security_auditor",
        "deploy_specialist"
    ],
    ("squarespace", "blog"): [
        "onboarding_specialist",
        "scraper_specialist",
        "stack_intelligence",
        "codegen_crew_lead",
        "seo_optimizer",
        "security_auditor",
        "deploy_specialist"
    ],
    ("wordpress", "blog"): [
        "onboarding_specialist",
        "scraper_specialist",
        "stack_intelligence",
        "codegen_crew_lead",
        "security_auditor",
        "deploy_specialist"
    ],
    ("generic", "generic"): [
        "onboarding_specialist",
        "scraper_specialist",
        "stack_intelligence",
        "codegen_crew_lead",
        "security_auditor",
        "deploy_specialist"
    ]
}
```

### LLM Override

When routing confidence < 0.7, Conductor asks LLM to modify routing:
```
This site is unusual (novel platform detected). Current routing: [...]
Should I modify the routing? If so, what personas should I add/remove/reorder?
```

---

## Phase Roadmap

### Phase 0 — Foundation (MVP)

**Goal:** One successful end-to-end migration, human approval at start + end.

**Scope:** Phase 0 supports static + light CMS sites only (Wix, Squarespace, WordPress blogs/portfolios). Sites with large product databases or heavy backend logic (Shopify, custom apps) are explicitly out of scope until Phase 1.5.

**Success Criteria:**
- Conductor runs end-to-end with minimal code changes
- Output is visibly better than a raw OpenCode prompt on the same site
- Fidelity score ≥ 55%
- Human sees clean summary trace (not full step-by-step log)

**Conductor Trace (MVP):** Clean, bullet-pointed summary. No verbose step-by-step logging. Example:
```
✓ Routing: Wix portfolio → [onboarding, scraper, codegen_lead, deploy]
✓ Platform detected: Wix (confidence: 0.94)
✓ Stack chosen: Next.js + Tailwind + Contentlayer
✓ Security gate passed (npm audit, lighthouse ≥ 85)
✓ Deployed to: https://staging--michael-portfolio.fly.dev
→ Awaiting human approval
```

#### Deliverables

**Phase 0 Core (14 items):**
- [ ] Conductor: LangGraph state machine + heuristic routing + LLM override + backward routing
- [ ] 4 Personas: onboarding_specialist, scraper_specialist, codegen_crew_lead, deploy_specialist
- [ ] Registry: persona definitions (markdown), skill registry (6 skills), tool registry
- [ ] Memory: SQLite schema (migrations, debates, heuristics), memory_query interface (stubbed — returns "no prior lessons" initially)
- [ ] 6 Skills: memory_query (stubbed), platform_detector, routing_heuristics, lighthouse, npm_audit, seo_optimizer
- [ ] MCPs Wired: Playwright, Fetch, GitHub, fly.io
- [ ] CLI Tools: lighthouse, npm_audit
- [ ] SecurityQualityGate class (npm audit + lighthouse ≥ 85 required)
- [ ] OpenCode invoke interface (tools/opencode.py)
- [ ] Onboarding: adaptive questions (5 max), structured context output, platform detection
- [ ] GitHub repo + GitHub Actions workflows (from templates repo)
- [ ] Human gates: start (onboarding review) + end (staging preview approval)
- [ ] One real site migrated end-to-end → staging deploy → human approves → prod
- [ ] Fidelity score ≥ 55%

---

### Phase 1 — Compounding

**Goal:** Memory works, routing visibly improves, Debate Arena runs.

#### Deliverables

**Memory:**
- [ ] LanceDB fully wired — semantic search on lessons
- [ ] Memory queries on every routing decision
- [ ] Lesson embeddings from completed migrations

**Debate Arena:**
- [ ] Structured debate templates
- [ ] Hard fidelity thresholds (< 70% = failure case)
- [ ] Ground truth comparison (predicted vs actual)
- [ ] Human reviews first 10 debate outputs

**Routing:**
- [ ] Heuristics updated from debate outputs
- [ ] Routing visibly improves on 2nd/3rd similar sites

**Content:**
- [ ] content_philosopher skill implemented (Phase 2)

**Testing:**
- [ ] 5 diverse site migrations (Wix, Squarespace, WordPress, edge case)
- [ ] Proof: 3rd similar site shows faster/better routing

---

### Phase 2 — Self-Improving

**Goal:** System updates itself with minimal human involvement.

#### Deliverables

**Memory:**
- [ ] Vector similarity search fully operational
- [ ] Cross-migration pattern detection

**Debate Arena:**
- [ ] Structured outputs produce actionable changes
- [ ] Human reviews only high-impact changes
- [ ] >50% of debates produce approved system changes

**Evolution:**
- [ ] Routing heuristics auto-updated from debates
- [ ] Conductor can propose new skills/MCPs (human approves)
- [ ] Novelty detector flags unusual sites (>30% different from memory)

**Context7 Integration:**
- [ ] Self-healing code gen wired
- [ ] AI uses Context7 for edge case resolution

**UI Polish:**
- [ ] Impeccable MCP wired
- [ ] Stitch MCP (when available)

---

### Phase 3+ — Living OS

**Goal:** Persistent per-user Site Agents, multi-site orchestration.

#### Deliverables

- [ ] User can spawn persistent "Site Agent" for ongoing maintenance
- [ ] System monitors deployed sites, proposes improvements
- [ ] Proactive modernization suggestions
- [ ] Multi-site orchestration capability

---

## Success Metrics

| Phase | Metric | Target |
|-------|--------|--------|
| Phase 0 | Sites migrated successfully | 1 |
| Phase 0 | Fidelity score | ≥ 60% |
| Phase 1 | Sites migrated | 5-10 |
| Phase 1 | Routing improvement (3rd similar site) | Visible improvement |
| Phase 1 | Debate outputs → system changes | ≥ 1 per migration |
| Phase 2 | Autonomous changes approved | > 50% |
| Phase 2 | Novel site handling | Measurably better than Phase 1 |

---

## Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| **Conductor** | Custom Python + LangGraph | State machine for routing, checkpointing |
| **Memory (Structured)** | SQLite | Zero-ops, fast, sufficient for metadata |
| **Memory (Vector)** | LanceDB | Local-first, AI-native, minimal ops |
| **Codegen Tool** | OpenCode | Already configured, handles heavy lifting |
| **MCP Integration** | modelcontextprotocol Python SDK | Standard MCP client via unified gateway layer |
| **MCP Gateway** | TrueFoundry / Speakeasy / self-hosted | Unified MCP gateway (similar to OpenRouter for models) |

**MCP Integration Strategy:**
Elyra connects to MCP servers through a unified MCP client/gateway layer (modeled after OpenRouter for LLMs). Phase 1 uses direct SDK connections to individual MCP sidecars. Phase 2+ introduces a lightweight gateway (TrueFoundry or self-hosted aggregator) for centralized auth, rate limiting, audit logging, and tool discovery — keeping Elyra clean and extensible.

| **CLI Tools** | npx/npm | Playwright, axe-cli, semgrep |
| **CI/CD** | GitHub Actions | Already configured in templates repo |
| **Hosting** | Fly.io (primary), Render (alternative) | Elyra + client sites in unified platform |

**Hosting Strategy:**
- Elyra itself runs on **Fly.io** (primary) or **Render** (alternative)
  - Why Fly.io: Machines (lightweight on-demand VMs) enable the future Business OS vision. Elyra or companion agents can dynamically spin up environments, cut branches, preview changes, run security/quality gates, and promote to production — all within the same unified platform.
  - Why Render: Simpler DevOps, excellent secret management, generous free tier. Ideal if maximum VM flexibility is not immediately required.
- Client sites deploy exclusively to **Fly.io** and **Render** (same ecosystem, unified management)

---

## Deployment Strategy

### Unified Hosting Platform (2026 Recommendation)

**Primary: Fly.io**
- Chosen for its Machines (lightweight on-demand VMs), which enable the future Business OS vision
- Spin up environments dynamically, cut branches, preview changes, run security/quality gates, promote to production
- Global edge deployment + great secret management
- Scales to zero, generous free tier

**Strong Alternative: Render**
- Excellent for simplicity and consistent DevOps
- Secret management built-in
- Ideal if maximum VM flexibility is not immediately required

**Both support:** Static sites, dynamic backends, databases, background jobs — allowing Elyra + future agents + all client sites to live in one ecosystem.

### Site Deployment (Client Sites)

Generated sites deploy to the best-fit platform per site type:
- **fly.io:** Fast CDN, instant previews, excellent for static/site generators
- **Render:** Dynamic backends, serverless functions, databases

---

## What's NOT in MVP

These are intentionally deferred to later phases:

- **Content philosopher skill** — Phase 2
- **Context7 integration** — Phase 2
- **Impeccable MCP** — Phase 2
- **Google Stitch MCP** — Phase 2 (when available)
- **Vector similarity search** — Phase 1 (stubbed in Phase 0)
- **Debate Arena** — Phase 1
- **Lamarckian evolution loop** — Phase 1
- **Per-user Site Agents** — Phase 3+

---

## Open Questions

- [x] What's the fidelity scoring algorithm? **Defined below (v0.1)**
- [x] Hosting platforms? **Fly.io (primary) + Render (alternative), client sites → fly.io/Render**
- [x] MCP Gateway? **Phase 1: direct SDK, Phase 2+: TrueFoundry/self-hosted gateway**
- [ ] How to handle Shopify sites with large product databases? (API access vs scraping)
- [ ] How to handle sites that require database migrations?

---

## Fidelity Scoring (v0.1)

**Elyra Fidelity Score v0.1**

| Component | Weight | Measurement |
|-----------|--------|-------------|
| Content Coverage | 40% | % of original text/images preserved or semantically matched |
| Lighthouse Performance + Accessibility | 25% | Automated (performance ≥ 85, accessibility ≥ 90) |
| Structural Correctness | 20% | Human spot-check: navigation, forms, CTAs work |
| Visual/Brand Alignment | 15% | Human judgment: does it feel like the same brand? |

**Total:** Weighted average. Human can override ±10 points.

**Pass threshold:** ≥ 55% (Phase 0 target), ≥ 65% (Phase 1+)

**Hard rule:** Fidelity < 70% after human review = automatic failure case → Debate Arena

---

## Anti-Fragility Safeguards (Phase 2+)

- All auto-applied routing changes go through a canary period (tested on 2 synthetic sites first)
- Human can roll back any change within 48 hours
- Novelty detector prevents over-generalization from past patterns
- Human veto for first 15 debate outputs

---

## Phase Artifact Pattern

Elyra's development follows the **Phase Artifact Pattern** — every phase produces exactly two living documents:

### 1. NORTH_STAR.md (Updated Continuously)
- Full architecture and phasing
- Updated with phase learnings at end of each phase
- Single source of truth for where the system is going

### 2. PHASE_N_RETROSPECTIVE.md (End of Phase)
- What we built in this phase
- What we learned (real learnings, not theoretical)
- What changed the architecture
- Fidelity trends observed
- Routing improvements discovered
- What we'd do differently

**Pattern:**
```
End of Phase N:
1. Rename TASKS_PHASE_N.md → docs/RETROSPECTIVE_PHASE_N.md
2. Fill in retrospective section with real learnings
3. Move completed task table to appendix or delete
4. Update NORTH_STAR.md with phase learnings
5. Create TASKS_PHASE_N+1.md for next phase
```

**Benefits:**
- Sprint backlog lives only inside retrospective (no process debt)
- Long-term knowledge capture (every phase contributes to institutional memory)
- Repo stays clean — no stale task lists
- Meta powerful: Elyra demonstrates the compounding intelligence it promises to users

**This is meta and powerful:** The project itself demonstrates the compounding intelligence it promises to deliver.

---

## Agentic Specialist Pattern (Validated in Phase 1)

**Status:** ✅ Validated — Phase 1 scraper successfully proved this pattern works.

### The Pattern

Every specialist in Elyra is implemented as:

```
Python thin glue + Kilo CLI + Persona Charter + Strict Pydantic Schema
```

**Components:**
1. **Python glue** (`*_agent.py`) — Only orchestration: builds prompt, calls Kilo, parses JSON, validates Pydantic. ~50-100 lines. No business logic.
2. **Kilo CLI** — The reasoning engine. Loads the persona charter + schema + task prompt, runs a ReAct loop using available MCP tools, returns structured JSON.
3. **Persona charter** (`registry/personas/*.md`) — Defines what the specialist does, what tools it uses, anti-patterns to avoid, and output schema. Pure declarative — no imperative code.
4. **Pydantic schema** (`models/site_schemas.py`) — Strict validation. Catches LLM hallucinations early, filters bad output.

**Why this pattern:**
- Kilo handles all agentic complexity (ReAct loop, tool selection, reasoning, tool execution)
- Python stays clean — just glue, never becomes an implicit agent
- Personas are declarative — easy to audit, modify, or replace without touching code
- Pydantic schemas catch output quality issues before they propagate
- Elyra inherits Kilo's full tooling (MCP servers, personas, skills) without extra configuration

### Kilo as ReAct Agent vs Python as MCP Client

This is the critical architectural trade-off that must not regress in future phases:

| | **Kilo as ReAct Agent** ✅ | **Python as MCP Client** ❌ |
|--|--|--|
| **Who reasons?** | Kilo (LLM-powered ReAct loop) | Python code (imperative, brittle) |
| **Tool calls** | Kilo decides dynamically based on context | Python hard-codes the sequence |
| **Adaptability** | Handles unexpected site structures, can explore and backtrack | Breaks on anything not explicitly coded |
| **Complexity** | Kilo hides all complexity — prompt + schema | Python grows complexity with every edge case |
| **Reliability** | Schema validation catches bad output | No reasoning layer to catch subtle errors |
| **Code size** | ~50-100 lines per specialist | ~500+ lines for equivalent capability |

**The anti-pattern to avoid:** Python calling MCP tools directly in an imperative loop. This is how you build a fragile, 500-line scraper that breaks on the first unusual site. The Python-as-MCP-client approach was the original plan for Phase 0/1 — it was explicitly rejected after attempting it.

**The validated approach:** Python calls `kilo run --format json --auto -- <prompt>`. Kilo loads the persona, binds the MCP tools, runs its ReAct loop, returns structured JSON. Python parses and validates. That's it.

**Why Kilo as ReAct Agent wins for Elyra's domain:**
- Websites are wildly heterogeneous. An agentic approach handles novel structures without code changes.
- The LLM (Kilo) can discover pages, follow nav, extract content, and iterate until it has high confidence.
- The persona charter encodes domain expertise (anti-patterns, success criteria) without Python code.
- The Pydantic schema ensures output quality without Python validation logic.

### Pattern for New Specialists

To add a new specialist (Architect, Marketing, Builder, etc.):

1. **Create persona charter** (`registry/personas/<name>_specialist.md`) — defines role, tools, anti-patterns, output schema
2. **Add Pydantic schema** (`models/site_schemas.py`) — structured output type
3. **Create agent** (`skills/agentic/<name>_agent.py`) — thin Python glue (build prompt → kilo run → parse → validate)
4. **Create CLI entrypoint** (`<name>.py`) — `python <name>.py <input>` runs the agent

No new agent frameworks, no LangGraph, no LangChain. Kilo CLI is the execution engine for all agentic work.

### Phase 1 Validation

The scraper specialist validated this pattern end-to-end:
- `scrape.py` (40 lines) + `scraper_agent.py` (170 lines) + `scraper_specialist.md` persona + `SiteUnderstanding` Pydantic schema
- Successfully scraped: example.com (single-page), merimeesolutions.wixstudio.com (Wix single-page), saintjosephtheworkeracademy.org (Wix multi-page with blog posts)
- Key fixes discovered: NDJSON parsing, UTF-8 encoding, null image filtering, blog post innerText extraction
- Total Python: ~210 lines. Total agentic capability: equivalent to what would have been ~800+ lines of imperative scraping code.

---

## Phase 0 Completion

**Status:** ✅ Scaffolding Complete (2026-05-02)

All Phase 0 tasks completed. See `docs/RETROSPECTIVE_PHASE0.md` for full retrospective.

### GitHub Issues for Phase 1
- #1: End-to-end migration test
- #2: Platform detector real URL testing
- #3: Wire Playwright MCP
- #4: Wire GitHub + fly.io MCPs
- #5: Implement Memory (SQLite working + LanceDB stubbed)
- #6: Conductor LLM override + backward routing

---

## References

- [Anthropic Claude Code Skills Pattern](https://docs.anthropic.com/en/docs/claude-code/skills)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LanceDB](https://lancedb.github.io/lancedb/)
- [MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
