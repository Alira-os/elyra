# Elyra — AI Website Creation & Migration Engine

**Version:** 1.0
**Last Updated:** 2026-05-01
**Status:** Planning

---

## Executive Summary

Elyra is an AI-native website creation and migration engine that takes a fundamentally different approach from traditional automation: instead of a rigid pipeline, Elyra uses a **Guided Dynamic Orchestration** pattern where a meta-agent (Conductor) intelligently routes between specialized personas, learns from every interaction, and compounds in capability over time.

**Core Principle:** Memory is a first-class citizen. Every migration or site build produces lessons that make the next one better. Generic "give AI tools" doesn't have this. Elyra does.

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
│   ├── github/            # GitHub Actions templates (from templates repo)
│   ├── docker/            # Docker configuration
│   └── config.py         # Configuration management
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

#### Deliverables

**Core Infrastructure:**
- [ ] New repo with clean directory structure
- [ ] Git initialized, pushed to GitHub

**Conductor:**
- [ ] LangGraph state machine for Conductor
- [ ] Basic routing with heuristic rules
- [ ] LLM override on low confidence
- [ ] Backward routing on failures

**Registry:**
- [ ] 8 core persona definitions (markdown)
- [ ] Skill registry with 10 skills
- [ ] Tool registry (MCP + executables)
- [ ] Registry query interface

**Memory:**
- [ ] SQLite schema (migrations, debates, heuristics)
- [ ] LanceDB vector store (stubbed)
- [ ] Memory query interface

**Tools Wired:**
- [ ] Playwright MCP
- [ ] Fetch MCP
- [ ] GitHub MCP
- [ ] Netlify MCP
- [ ] Render MCP
- [ ] npm_audit CLI

**Personas Implemented:**
- [ ] migration_orchestrator
- [ ] onboarding_specialist
- [ ] scraper_specialist
- [ ] stack_intelligence
- [ ] codegen_crew_lead
- [ ] security_auditor
- [ ] deploy_specialist

**Skills Implemented:**
- [ ] memory_query (stubbed, returns empty initially)
- [ ] platform_detector
- [ ] routing_heuristics
- [ ] lighthouse
- [ ] npm_audit
- [ ] semgrep_scan (via GitHub Actions)
- [ ] accessibility_auditor
- [ ] seo_optimizer

**Quality/Security (MVP-mandatory):**
- [ ] SecurityQualityGate class
- [ ] All security checks run before deploy
- [ ] Fidelity scoring on verify

**Onboarding:**
- [ ] 5-10 adaptive questions
- [ ] Structured context output
- [ ] Platform detection from URL

**CI/CD (from templates repo):**
- [ ] GitHub Actions workflows wired
- [ ] Semgrep, Trivy, Dependency Review
- [ ] Lighthouse in CI

**Human Gates:**
- [ ] Start: Onboarding answers reviewed
- [ ] End: Staging preview + approval

**Test:**
- [ ] One real Wix or Squarespace site migrated
- [ ] Deployed to staging
- [ ] Human approves → prod deploy
- [ ] Fidelity ≥ 60%

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

- [ ] How to handle Shopify sites with large product databases? (API access vs scraping)
- [ ] Should we support more hosting platforms beyond Netlify/Render?
- [ ] What's the fidelity scoring algorithm? (needs definition)
- [ ] How to handle sites that require database migrations?

---

## References

- [Anthropic Claude Code Skills Pattern](https://docs.anthropic.com/en/docs/claude-code/skills)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LanceDB](https://lancedb.github.io/lancedb/)
- [MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
