# Elyra — AI Website Creation & Migration Engine

**Version:** 1.0
**Last Updated:** 2026-05-01
**Status:** Planning

---

## Executive Summary

Elyra is an AI-native website creation and migration engine that takes a fundamentally different approach from traditional automation: instead of a rigid pipeline, Elyra uses a **Guided Dynamic Orchestration** pattern where a meta-agent (Conductor) intelligently routes between specialized personas, learns from every interaction, and compounds in capability over time.

**Core Principle:** Memory is a first-class citizen. Every migration or site build produces lessons that make the next one better. Generic "give AI tools" doesn't have this. Elyra does.

**Why Elyra Wins:** Unlike CrewAI/AutoGen (rigid pipelines), Replit Agent (no memory), or v0/Bolt.new (one-shot), Elyra compounds. Each migration makes the next smarter. The Conductor doesn't just execute — it learns routing patterns, detects anti-patterns, and evolves. After 5 real migrations, the routing should visibly outperform any generic AI codegen approach on the same site.

**Target Users:** Anyone who needs to migrate legacy sites (Wix, Squarespace, WordPress) or build new sites, with the intelligence and quality of an expert web agency.

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
│ - Fetch      │   │ - Backend    │   │ - Netlify    │
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
│   ├── state_machine.py    # LangGraph state machine for Conductor
│   ├── routing.py         # Heuristic routing + LLM override
│   ├── memory_client.py    # Memory layer interface
│   └── orchestrator.py     # Main Conductor class
│
├── registry/               # Persona, skill, tool registry
│   ├── personas/           # Core persona definitions (markdown)
│   ├── skills/            # Skill definitions (markdown + callable)
│   ├── tools/             # Tool definitions
│   └── registry.py        # Query and resolve registry
│
├── memory/                 # Persistent memory layer
│   ├── sqlite/             # Structured metadata store
│   │   ├── migrations.py  # Migration history
│   │   ├── debates.py     # Debate outputs
│   │   └── heuristics.py  # Routing rules
│   ├── vector/            # LanceDB for semantic similarity
│   │   └── lessons.py    # Lesson embeddings
│   └── memory.py          # Unified memory interface
│
├── debate/                 # Debate Arena + Lamarckian loop
│   ├── templates/         # Structured debate templates
│   ├── arena.py           # Debate orchestration
│   ├── lamarckian.py      # Evolution loop
│   └── extractors.py      # Lesson extraction
│
├── tools/                  # MCP clients, executables
│   ├── mcp/              # MCP server clients
│   │   ├── playwright.py
│   │   ├── fetch.py
│   │   ├── github.py
│   │   ├── netlify.py
│   │   ├── render.py
│   │   └── npm_audit.py
│   ├── executables/       # CLI tools
│   │   ├── lighthouse.py
│   │   └── semgrep.py
│   └── tools.py           # Unified tool interface
│
├── personas/               # Core persona implementations
│   ├── core/              # 8 core personas (markdown)
│   └── personas.py         # Persona loader
│
├── skills/                  # Skill definitions
│   ├── executable/        # Python callables
│   │   ├── memory_query.py
│   │   ├── platform_detector.py
│   │   ├── routing_heuristics.py
│   │   ├── accessibility_audit.py
│   │   ├── lighthouse.py
│   │   └── seo_optimizer.py
│   └── skills.md           # Skill registry markdown
│
├── onboarding/              # Onboarding flows
│   ├── flows/              # Onboarding question flows
│   │   ├── adaptive.py    # Adaptive interview logic
│   │   └── questions.py    # Question templates
│   └── onboarding.py      # Onboarding persona
│
├── infra/                   # Infrastructure
│   ├── github/            # GitHub Actions templates (pulled from merimeesoftware/templates)
│   ├── docker/            # Docker configuration
│   └── config.py         # Configuration management
│
├── tests/                  # Test suite (empty, to be populated)
│
├── examples/               # Example inputs and expected outputs
│   └── test_sites/        # Real test site URLs + fidelity baselines
│
└── docs/                   # Documentation
    ├── NORTH_STAR.md       # This file
    ├── ARCHITECTURE.md     # Detailed architecture
    ├── PERSONAS.md        # Persona descriptions
    ├── SKILLS.md          # Skill descriptions
    ├── ROUTING.md         # Routing heuristics
    └── MEMORY.md          # Memory layer design
```

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
| **deploy_specialist** | GitHub repo + CI/CD + hosting | github_actions_setup, netlify_deploy, render_deploy | GitHub, Netlify, Render |
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
| **Netlify** | Deploy hosting | ✅ Yes |
| **Render** | Deploy hosting | ✅ Yes |
| **npm_audit** | Dependency scanning | ✅ Yes |
| **Context7** | Self-healing code gen | Phase 2 |
| **Impeccable** | UI polish | Phase 2 |
| **Google Stitch** | AI UI design | Phase 2 |

---

## Memory Layer

### SQLite Schema

```sql
-- Migration history
CREATE TABLE migrations (
    id TEXT PRIMARY KEY,
    url TEXT,
    platform TEXT,  -- wix, squarespace, wordpress, generic
    task_type TEXT,  -- e-commerce, blog, portfolio, business
    stack_chosen TEXT,  -- JSON of stack decision
    fidelity_score REAL,
    routing_used TEXT,  -- JSON array of personas invoked
    outcome TEXT,  -- success, partial, failed
    created_at DATETIME
);

-- Debate outputs
CREATE TABLE debate_outputs (
    id TEXT PRIMARY KEY,
    migration_id TEXT,
    debate_result TEXT,  -- JSON
    human_approved BOOLEAN,
    changes_proposed TEXT,  -- JSON
    changes_applied BOOLEAN,
    created_at DATETIME
);

-- Routing heuristics
CREATE TABLE routing_heuristics (
    platform TEXT,
    task_type TEXT,
    routing_sequence TEXT,  -- JSON array
    success_count INTEGER,
    failure_count INTEGER,
    last_updated DATETIME,
    PRIMARY KEY (platform, task_type)
);
```

### Vector Store (LanceDB)

Stores lesson embeddings for semantic similarity search:
- Lesson summaries
- What worked for specific platform/task combinations
- Anti-patterns

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
✓ Deployed to: https://staging--michael-portfolio.netlify.app
→ Awaiting human approval
```

#### Deliverables

**Phase 0 Core (14 items):**
- [ ] Conductor: LangGraph state machine + heuristic routing + LLM override + backward routing
- [ ] 4 Personas: onboarding_specialist, scraper_specialist, codegen_crew_lead, deploy_specialist
- [ ] Registry: persona definitions (markdown), skill registry (6 skills), tool registry
- [ ] Memory: SQLite schema (migrations, debates, heuristics), memory_query interface (stubbed — returns "no prior lessons" initially)
- [ ] 6 Skills: memory_query (stubbed), platform_detector, routing_heuristics, lighthouse, npm_audit, seo_optimizer
- [ ] MCPs Wired: Playwright, Fetch, GitHub, Netlify
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
| **MCP Clients** | modelcontextprotocol Python SDK | Standard MCP integration |
| **CLI Tools** | npx/npm | Playwright, axe-cli, semgrep |
| **CI/CD** | GitHub Actions | Already configured in templates repo |
| **Hosting** | Netlify + Render | Already have MCP access |

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
- [ ] How to handle Shopify sites with large product databases? (API access vs scraping)
- [ ] Should we support more hosting platforms beyond Netlify/Render?
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

## References

- [Anthropic Claude Code Skills Pattern](https://docs.anthropic.com/en/docs/claude-code/skills)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LanceDB](https://lancedb.github.io/lancedb/)
- [MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
