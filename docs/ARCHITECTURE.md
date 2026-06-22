# Elyra Architecture — Target State

**Version:** 1.1
**Status:** Planning (updated from Phase 0/1 learnings)
**Last Updated:** 2026-05-20

---

## Overview

This document describes the **target architecture** — where Elyra is headed.
Phase 0 scaffolding is correct for MVP but must evolve to this architecture.

**Relationship to NORTH_STAR:**
- NORTH_STAR.md = Vision, phasing, success criteria (stable)
- ARCHITECTURE.md = Detailed implementation guide (evolves as we learn)

---

## Deployment Topology

### Current State (Phase 0)

Elyra runs as a Python application with:
- Subprocess calls for OpenCode
- Stub MCP clients returning mock data
- SQLite for memory
- No containerization

```
┌─────────────────────────────────────┐
│          Local Machine              │
│                                     │
│  Python App (Elyra)                │
│  ├── conductor/                     │
│  ├── registry/                      │
│  ├── memory/                        │
│  ├── tools/ (stubs)                 │
│  │   └── mcp/ (mock)               │
│  └── skills/                        │
│                                     │
│  OpenCode (subprocess)             │
└─────────────────────────────────────┘
```

### Target State (Phase 1+)

Elyra runs in a containerized environment alongside MCP servers and OpenCode.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Compose / Kubernetes                   │
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐       │
│  │   Elyra      │   │ MCP Gateway  │   │   OpenCode   │       │
│  │  (Conductor) │◄──┤  (stdio/SSE) │   │   (Tool)     │       │
│  │   Python     │   │              │   │              │       │
│  └──────────────┘   └──────────────┘   └──────────────┘       │
│         │                  │                  │                │
│         └──────────────────┴──────────────────┘                │
│                        Shared Network                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    MCP Servers (Sidecars)                 │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │  │
│  │  │Playwright│ │  Fetch   │ │  GitHub  │ │  fly.io │    │  │
│  │  │   MCP    │ │   MCP    │ │   MCP    │ │   MCP    │    │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Data Layer                            │  │
│  │  ┌──────────┐                        ┌──────────┐        │  │
│  │  │ SQLite   │◄─────────────────────►│ LanceDB  │        │  │
│  │  │(metadata)│                        │ (vector) │        │  │
│  │  └──────────┘                        └──────────┘        │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## MCP Integration Pattern

> **Read `AGENTS.md` first.** This section is the long-form reference; `AGENTS.md` is the normative decision rule. The two must agree — if they don't, `AGENTS.md` wins.

### Principle

MCP servers are **tools** that Elyra's **agents** call. They are not agents themselves, and they are not a layer the agents route through. The clean separation:

- **Agent** = a persona (`.md`) that reasons. Lives in `registry/personas/`. The canonical example is `scraper_specialist.md`, which thinks about a site, decides what to navigate, and produces a `SiteUnderstanding`.
- **Tool (MCP server)** = a fixed set of callable functions the LLM picks during its ReAct loop. Connected to Kilo via `kilocode/.mcp.json` (project-local) or the `mcp:` block of `~/.config/kilo/kilo.json` (user-global).
- **Execution layer** = Kilo CLI, invoked from Python by `tools/kilo.py:invoke_kilo_safe`.

The earlier framing of this section ("Elyra is a client — it never implements MCP servers") was correct in spirit but easy to misread as "Elyra is *one* thing that connects to MCPs." It is not. Elyra *is* a fleet of agents, each of which uses MCPs as tools. Conflating the two is how we ended up with a `scraper-mcp` entry in the global config: someone treated the scraper as a tool, when it is an agent that uses Playwright + Fetch MCPs as its tools.

### What the scraper is — and is not

The scraper (`scraper_specialist` persona, `skills/agentic/scraper_agent.py` glue) is the worked example for the whole model. It:

- is an **agent**, defined by `registry/personas/scraper_specialist.md`
- runs as a Kilo CLI subprocess via `tools/kilo.py:invoke_kilo_safe`
- during its ReAct loop, calls the **Playwright MCP** and **Fetch MCP** tools declared in `kilocode/.mcp.json`
- emits a **structured response** validated against `SiteUnderstanding` in `models/site_schemas.py`

It is **not** an MCP server. There is no `scraper-mcp` entry in any config. There is no `localhost:8812` gateway. There is no Python "MCP client" wrapper that does the scraping. (The Phase 0 stubs in `tools/mcp/` are remnants and should be removed or replaced with real MCP SDK clients only when an actual client is needed — not as proxies for the agent.)

### Where MCPs are wired

| Scope | File | What lives there |
|---|---|---|
| Project-local | `kilocode/.mcp.json` | MCP servers that Elyra personas call directly. Current entries: `playwright`, `fetch`, `impeccable`, `stitch`. |
| User-global | `~/.config/kilo/kilo.json` `mcp:` block | MCP servers shared across all projects. Current entries: `docker-mcp`, `netlify`, `fly`, `cloudflare`, `stitch`. |
| Python SDK clients (rare) | `tools/mcp/<name>.py` | Only if some other system needs to call an MCP server outside the Kilo ReAct loop. Phase 0 left stubs here — they are not part of the canonical flow. |

### MCP servers currently in use

| Server | Purpose | Used by (agent) |
|---|---|---|
| Playwright | JS rendering, DOM extraction | `scraper_specialist` |
| Fetch | Clean HTTP content fetching | `scraper_specialist` |
| Impeccable | Visual audit / critique | `ui_designer`, `builder_specialist` |
| Stitch | Visual brand direction (Google) | `ui_designer` |
| Netlify | Deploy / site management | deploy flows |
| Fly.io | Client site deployment | `deploy_engineer` |
| Cloudflare | DNS / Workers / R2 | deploy flows |
| docker-mcp (gateway) | Aggregated tool gateway for the main session | used by interactive Kilo session, not by a specific persona |

If you are adding a new MCP server, it must be a tool — i.e. a fixed set of callable functions, not a thing that thinks. Add it to the right `.mcp.json` and reference it by name in the relevant persona's "Tools You May Use" section.

---

## Data Flow

### Migration Request Flow

```
User Input
    │
    ▼
┌─────────────────┐
│   Onboarding    │ ← Adaptive questions via CLI/UI
│  Specialist    │
└────────┬────────┘
         │ TaskContext
         ▼
┌─────────────────┐
│    Conductor    │ ← Main orchestrator
│  (Meta-Agent)   │
└────────┬────────┘
         │
         ├──→ Memory Query ──► SQLite + LanceDB
         │
         ├──→ Routing ──► Heuristics + LLM Override
         │
         ├──→ Personas ──► Specialization delegation
         │     │
         │     ├──→ Playwright MCP ──► Site Scrape
         │     ├──→ OpenCode ──► Codegen
         │     ├──→ GitHub MCP ──► Repo Creation
         │     ├──→ fly.io MCP ──► Deploy
         │     └──→ Security Gate ──► npm audit + Lighthouse
         │
         ▼
┌─────────────────┐
│  Human Approval  │ ← Review staging, approve/reject
│     Gate        │
└────────┬────────┘
         │
         ▼ (if approved)
    Production Deploy
```

### Memory Flow

```
Every Migration produces:
    ├── Structured metadata → SQLite (migrations, debates, heuristics)
    └── Lesson embeddings → LanceDB (semantic similarity search)

On routing decision:
    ├── Check SQLite for similar past migrations
    ├── Check LanceDB for semantic matches
    └── Adjust routing confidence + sequence
```

---

## LangGraph Evolution Path

### Phase 0 — Lightweight State Machine

Current implementation uses Python `TypedDict` + `Enum` for phases.

```python
class WorkflowPhase(str, Enum):
    ONBOARDING = "onboarding"
    ROUTING = "routing"
    SCRAPING = "scraping"
    CODEGEN = "codegen"
    SECURITY_GATE = "security_gate"
    DEPLOY = "deploy"
    ...

class ConductorState(TypedDict):
    session_id: str
    current_phase: WorkflowPhase
    ...
```

**Why:** Simple, no extra dependencies, easy to understand.

### Phase 1 — Checkpointing + Error Recovery

Add LangGraph checkpointer for crash recovery.

```python
from langgraph.checkpoint import CheckpointSaver
from langgraph.graph import StateGraph

class SqliteCheckpointer(CheckpointSaver):
    """Checkpoint to SQLite for resume on crash."""
    def __init__(self, db_path: str):
        self.db_path = db_path

    def save(self, checkpoint: dict, config: dict):
        thread_id = config["configurable"]["thread_id"]
        save_checkpoint(thread_id, checkpoint)

    def load(self, config: dict) -> dict | None:
        thread_id = config["configurable"]["thread_id"]
        return load_checkpoint(thread_id)
```

**Phase 1 transitions:** Uses simple linear transitions. State machine transitions on success, aborts on failure.

### Phase 2 — Conditional Routing + Subgraphs

Full LangGraph with conditional edges + subgraph composition.

**Nodes (atomic operations):**
- `onboarding_node` — Collect task context
- `platform_detection_node` — Detect platform from URL
- `routing_decision_node` — Decide routing sequence
- `security_gate_node` — Run quality gates
- `human_approval_node` — Wait for human review

**Subgraphs (complex workflows):**
- `scraper_subgraph` — Playwright + Fetch + content processing
- `codegen_subgraph` — OpenCode + code validation + refinement
- `deploy_subgraph` — GitHub + fly.io + CI/CD

**Conditional routing:**
```python
def routing_function(state: ConductorState) -> str:
    platform = state["task_context"]["platform"]
    task_type = state["task_context"]["task_type"]

    if platform == "unknown" or state["routing_confidence"] < 0.7:
        return "llm_override_path"

    if task_type == "e-commerce":
        return "ecommerce_subgraph"
    elif task_type == "blog":
        return "blog_subgraph"
    else:
        return "default_subgraph"

graph.add_conditional_edges(
    "routing_decision_node",
    routing_function,
    {
        "llm_override_path": "llm_override_node",
        "ecommerce_subgraph": "ecommerce_subgraph",
        "blog_subgraph": "blog_subgraph",
        "default_subgraph": "default_subgraph"
    }
)
```

**Why subgraphs:** Complex platform-specific flows (e.g., Wix scraping differs from WordPress) are encapsulated. Easier to test and modify platform-specific logic.

---

## Security Architecture

### Phase 0 Guardrails (Implemented)

- SecurityQualityGate blocks deploy on:
  - Critical npm vulnerabilities
  - Lighthouse performance < 85
  - Lighthouse accessibility < 90
- No credentials persisted to memory
- Human approval gate before production

### Phase 1+ Concrete Security Measures

**Secrets Management:**
- Docker secrets for sensitive tokens (FLY_AUTH_TOKEN, GITHUB_TOKEN)
- Or use Doppler/Vault for external secret management
- Never commit secrets to git (add to .gitignore)

**Network Security:**
- TLS between containers (in production)
- MCP servers run on internal network, not exposed publicly
- Elyra only accessible via authenticated API or CLI

**Audit Logging:**
- Structured JSON logs of all MCP calls
- Log format: `{timestamp, level, service, action, duration_ms, success, error}`
- Retention: 90 days for debugging, 1 year for compliance

**Circuit Breakers:**
- If MCP server fails 3 times in a row, circuit breaker opens
- Stop calling failing service for 60 seconds
- Log and alert on circuit breaker events
- Prevents cascade failures

**Rate Limiting:**
- Max 10 GitHub API calls per minute (respect GitHub rate limits)
- Max 5 fly.io API calls per minute
- Queue excess requests with exponential backoff

### Observability & Resilience

**Tracing:**
- OpenTelemetry for distributed tracing across all services
- Trace ID propagated through all MCP calls
- User-facing trace (for CLI output) is separate from internal tracing

**Metrics (Prometheus):**
- `elyra_migrations_total` (counter)
- `elyra_migration_duration_seconds` (histogram)
- `elyra_mcp_call_duration_seconds` (histogram by MCP server)
- `elyra_security_gate_passed` (counter with labels: passed/failed)
- `elyra_routing_confidence` (gauge)

**Retry Patterns:**
- MCP calls retry 3 times with exponential backoff (1s, 2s, 4s)
- Idempotent operations only (safe to retry)
- Non-idempotent operations require custom handling

**Health Checks:**
- `/health` endpoint on Elyra returns service status
- Docker health checks for all MCP sidecars
- Liveness vs readiness: liveness = can accept requests, readiness = ready to do work

---

## Directory Structure (Target State)

```
elyra/
├── conductor/              # Conductor orchestrator
│   ├── orchestrator.py     # Main Conductor class
│   ├── state_machine.py    # LangGraph-ready state machine
│   ├── routing.py          # Heuristic routing + LLM override
│   ├── memory_client.py    # Memory layer interface
│   ├── trace.py            # Clean trace output
│   └── security_gate.py    # Security + quality gate
│
├── registry/               # Single source of truth
│   ├── registry.py         # Loader (load_persona, load_skill, etc.)
│   ├── personas/           # Markdown persona definitions
│   │   ├── migration_orchestrator.md
│   │   ├── onboarding_specialist.md
│   │   ├── scraper_specialist.md
│   │   ├── deploy_specialist.md
│   │   └── ... (future: codegen_crew_lead, etc.)
│   └── skills/             # Markdown skill definitions
│       ├── memory_query.md
│       ├── platform_detector.md
│       └── ...
│
├── skills/                 # Executable skill implementations
│   └── executable/         # Python callables
│       ├── memory_query.py
│       ├── platform_detector.py
│       ├── routing_heuristics.py
│       ├── lighthouse.py
│       ├── npm_audit.py
│       └── seo_optimizer.py
│
├── tools/                  # Tool interfaces
│   ├── opencode.py        # OpenCode subprocess interface
│   └── mcp/              # MCP client interfaces (stubs in Phase 0)
│       ├── playwright.py  # STUB: Replace in Phase 1
│       ├── fetch.py        # STUB: Replace in Phase 1
│       ├── github.py       # STUB: Replace in Phase 1
│       └── fly.io.py      # STUB: Replace in Phase 1
│
├── memory/                 # Memory layer
│   ├── sqlite/            # Structured metadata
│   │   ├── schema.sql
│   │   └── crud.py
│   ├── vector/            # LanceDB for semantic search
│   │   └── lessons.py     # STUB: Implement in Phase 1.5
│   └── memory.py          # Unified interface
│
├── onboarding/            # Onboarding flows
│   └── flows/
│       ├── adaptive.py    # AdaptiveOnboarding class
│       └── questions.py   # Question templates
│
├── infra/                 # Infrastructure
│   └── github/           # GitHub Actions templates
│
├── .github/workflows/     # CI/CD (GitHub Actions)
│   ├── ci.yml
│   ├── deploy-staging.yml
│   └── semgrep.yml
│
├── examples/              # Examples
│   └── test_sites/       # Test site configurations
│
└── docs/                 # Documentation
    ├── NORTH_STAR.md     # Vision + phasing (stable)
    ├── ARCHITECTURE.md   # This file (evolves)
    ├── RETROSPECTIVE_PHASE0.md
    └── ... (future phase retrospectives)
```

**Note:** `personas/` root directory removed — single source of truth is `registry/personas/`.

---

## Component Responsibilities

### Conductor
- **Does:** Route, checkpoint state, enforce gates, produce trace
- **Does NOT:** Write code, scrape sites, deploy (delegates to personas/tools)

### Personas (in registry/personas/)
- **Does:** Provides guidance for specialized tasks
- **Implementation:** Loaded by registry, executable logic in skills/

### Skills (in skills/)
- **Does:** Executable implementations of specialized capabilities
- **Pairs:** Markdown (guidance) + Python (executable)

### Tools (in tools/)
- **Does:** Interfaces to external services (OpenCode, MCP servers)
- **Phase 0:** Stubs with mock data
- **Phase 1+:** Real MCP clients via official SDK

### Memory (in memory/)
- **Does:** Persist migration history, routing heuristics, lessons
- **Phase 0:** SQLite only (LanceDB stubbed)
- **Phase 1+:** SQLite + LanceDB for semantic search

---

## Deployment Configuration

### Elyra Self-Hosting (Fly.io Primary)

**Primary: Fly.io**
- Machines (lightweight on-demand VMs) enable future Business OS vision
- Spin up environments dynamically, cut branches, preview changes, run security/quality gates, promote to production
- Global edge deployment + great secret management
- Scales to zero, generous free tier

**Strong Alternative: Render**
- Simpler DevOps, excellent secret management
- Ideal if maximum VM flexibility is not immediately required
- Built-in health checks, easy scaling

**Why these over AWS/K8s:**
- Too much ops overhead for MVP
- Elyra + future agents need fast VM spawn, not enterprise-scale
- Revisit when multiple tenants need isolation

### docker-compose.yml (Phase 1 Target)

```yaml
version: '3.8'

services:
  elyra:
    build:
      context: .
      dockerfile: Dockerfile
    depends_on:
      playwright-mcp:
        condition: service_healthy
      github-mcp:
        condition: service_healthy
      fly-mcp:
        condition: service_healthy
    environment:
      - GITHUB_TOKEN_FILE=/run/secrets/github_token
      - FLY_API_TOKEN_FILE=/run/secrets/fly_token
    volumes:
      - elyra_output:/app/output
      - elyra_memory:/app/memory
    secrets:
      - github_token
      - fly_token
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped

  playwright-mcp:
    image: ghcr.io/modelcontextprotocol/playwright-mcp:latest
    healthcheck:
      test: ["CMD", "npx", "-y", "@playwright/mcp-server", "--version"]
      interval: 30s
      timeout: 5s
      retries: 2
    restart: unless-stopped

  github-mcp:
    image: ghcr.io/modelcontextprotocol/github-mcp:latest
    environment:
      - GITHUB_TOKEN_FILE=/run/secrets/github_token
    healthcheck:
      test: ["CMD", "npx", "-y", "@github/mcp-server", "--version"]
      interval: 30s
      timeout: 5s
      retries: 2
    restart: unless-stopped

  fly-mcp:
    image: ghcr.io/modelcontextprotocol/fly-mcp:latest
    environment:
      - FLY_API_TOKEN_FILE=/run/secrets/fly_token
    healthcheck:
      test: ["CMD", "npx", "-y", "@flyio/mcp-server", "--version"]
      interval: 30s
      timeout: 5s
      retries: 2
    restart: unless-stopped

volumes:
  elyra_output:
  elyra_memory:

secrets:
  github_token:
    file: ./secrets/github_token.txt
  fly_token:
    file: ./secrets/fly_token.txt
```

**Note:** MCP server images (`ghcr.io/modelcontextprotocol/*`) are illustrative. Verify actual image paths before deployment. Individual sidecars (not gateway) for Phase 1. Client sites deploy to Fly.io + Render.

---

## Phase 1 Upgrade Checklist

When upgrading from Phase 0 scaffolding to Phase 1 architecture:

- [ ] Replace `tools/mcp/playwright.py` stub with real MCP client
- [ ] Replace `tools/mcp/github.py` stub with real MCP client
- [ ] Create `tools/mcp/fly.py` stub with Fly.io MCP client
- [ ] Add LangGraph checkpointer for state persistence
- [ ] Wire SQLite memory queries to return real past migrations
- [ ] Add individual MCP server containers (not gateway) for Phase 1
- [ ] Update docker-compose.yml with all services
- [ ] Test end-to-end flow with real MCP calls

---

## Broader Ecosystem (Phase 3+ Vision)

Elyra is currently focused on Site OS — website creation and migration. Long-term vision is a unified Business OS platform with specialized agents sharing memory and MCP layer:

```
┌─────────────────────────────────────────────────────────────┐
│                    Elyra Business OS                        │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Site      │  │  Marketing  │  │   Sales     │        │
│  │   Agent     │  │   Agent     │  │   Agent     │        │
│  │             │  │             │  │             │        │
│  │ - Migration │  │ - SEO audit │  │ - Lead qual │        │
│  │ - Creation  │  │ - Content   │  │ - Outreach  │        │
│  │ - Updates   │  │ - Social    │  │ - Follow-up │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│         │                 │                 │              │
│         └─────────────────┴─────────────────┘              │
│                    Shared Infrastructure                   │
│         ┌─────────────────────────────────────┐           │
│         │  Memory Layer (SQLite + LanceDB)    │           │
│         │  MCP Layer (Shared tool access)      │           │
│         │  Conductor (Orchestration)          │           │
│         └─────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

**Shared components:**
- **Memory:** Cross-agent learning. Site Agent learns something → Marketing Agent benefits.
- **MCP Layer:** Single MCP server deployment serves all agents. Add new MCP = available to all agents.
- **Conductor:** Each agent has its own Conductor, but they share the memory/MCP infrastructure.

**This is aspirational.** Phase 0-2 fully focused on Site OS. Ecosystem vision guides architecture decisions (keep memory layer generic, MCP layer extensible).

---

## Branching Strategy

Elyra uses a **trunk-based development** approach with phase-based stabilization:

```
main          ──────────────────── (production, stable)
                             ↑
develop       ──────────────────── (integration, work here)
              ↑
phase-1       ──────────────────── (Phase 1 work)
              ↑
phase-2       ──────────────────── (Phase 2 work)
```

### Branch Structure

| Branch | Purpose | Stability |
|--------|---------|-----------|
| `main` | Production-ready code | Highest — only merged from `develop` when phase is complete |
| `develop` | Integration branch for current phase | Medium — all work merges here |
| `phase-N` | Phase-specific work (created as needed) | Lower — rebase onto `develop` when ready |

### Phase Completion Flow

```
1. Work happens on develop (or feature branches)
2. When Phase N is complete and verified on develop:
   - Review the retrospective: docs/RETROSPECTIVE_PHASE_N.md
   - Update NORTH_STAR.md with learnings
   - Merge develop → main
   - Tag: v1.0.0, v1.1.0, etc.
3. main always reflects the last completed phase
```

### Current State (Phase 0 Complete)

- `main` — Phase 0 scaffolding complete
- `develop` — Merged from Phase 0 completion

### Rules

1. **Never commit directly to `main`** — only merges from `develop`
2. **develop must remain in a releasable state at all times** — if it's broken, fix it before starting new work
3. **Feature branches** — short-lived, merged via PR to `develop`
4. **Phase branches** — created when starting new phase, rebased onto `develop` when phase completes

### GitHub Actions Integration

CI runs on all PRs to `develop` and `main`:
- `ci.yml` — Lint, typecheck, test
- Security scans on every PR

Deploy to staging happens on merge to `develop`:
- `deploy-staging.yml` — Builds and deploys to staging

Production deploy happens on merge to `main`:
- After phase completion, `main` is deployed to production

---

## Hybrid Storage Architecture (Phase 1+)

Production-grade hybrid memory system for 50-100+ migrations:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Hybrid Memory Architecture                    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 1: Metadata + Provenance (SQLite)                 │   │
│  │  • Migration ledger (stage_history, fidelity_scores)  │   │
│  │  • Routing heuristics                                   │   │
│  │  • Debate outputs + human approvals                     │   │
│  │  • Persona versions used per stage                       │   │
│  │  • Production URLs, GitHub repos, preview URLs + TTLs   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 2: Structured Artifacts (git-tracked JSON)       │   │
│  │  memory/site_understandings/<id>.json                 │   │
│  │  memory/site_architectures/<id>.json                  │   │
│  │  memory/marketing_recommendations/<id>.json          │   │
│  │  memory/artifacts/<id>.json (lessons, anti-patterns) │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 3: Code Artifacts (Git repos)                    │   │
│  │  Alira-os/<site-repo> per migration/client             │   │
│  │  Permanent immutable history                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 4: Semantic Search (LanceDB)                     │   │
│  │  • Vector embeddings of lessons, site summaries        │   │
│  │  • Query: "Find all trades gallery migrations"        │   │
│  │  • Query: "What worked for classical schools?"         │   │
│  │  • Phase 0/1: hash-based fallback until real embeddings │  │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 5: Large Media (external, URL-referenced only)   │   │
│  │  • Fly.io Volumes or Cloudflare R2                    │   │
│  │  • URLs stored in metadata; media NOT in git           │   │
│  │  • Retention: "as needed"                             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### SQLite Schema Extensions

New tables:
- `site_architectures`: Architect Specialist output per migration
- `content_recommendations`: Marketing Specialist output per migration
- `artifacts`: Lessons, anti-patterns, routing insights with vector references

New columns on `migrations`:
- `stage_history`, `fidelity_history`, `persona_versions`, `decisions`
- `production_url`, `github_repo`, `preview_url`, `preview_expires_at`

### LanceDB Integration (`memory/vector/lessons.py`)

```python
# Semantic search over lessons
results = memory.query_lessons("trades gallery wix", tags=["gallery", "wix"])

# Log a lesson from a migration
lessons.log_lesson(
    migration_id="abc-123",
    lesson={"description": "Trades gallery works well for wix portfolios"},
    tags=["wix", "portfolio", "gallery"]
)

# Search for site patterns
results = lessons.search_site_summaries("classical academy education religious")
```

---

## Promotion Pipeline (Phase 1+)

Hardened multi-stage promotion flow with automated gates + single human approval:

```
Builder + SEO finish
        │
        ▼
┌───────────────────────┐
│  GitHub Repo Created │  ← github_strategy_agent (Alira-os org, per-site)
│  (post-local-build)   │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│  Kilo Code Reviewer   │  ← GitHub Action (kilo-review.yml)
│  + Security Agent     │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────────────────────────────────┐
│  Elyra SecurityQualityGate (REQUIRED)             │
│  • Lighthouse perf ≥ 95 (raised from 85)          │
│  • Lighthouse a11y ≥ 90                          │
│  • Lighthouse best-practices ≥ 90 (raised from 85)│
│  • Lighthouse SEO ≥ 90 (raised from 85)          │
│  • npm audit: 0 critical                          │
└──────────┬────────────────────────────────────────┘
           │ FAIL → Block + report issues
           │ PASS
           ▼
┌───────────────────────┐
│  Preview Deployment   │  ← Fly.io preview app (7-day TTL)
│  Temporary public URL │  + banner: "Preview of new {site} website"
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│  Human Approval Gate  │  ← ONLY mandatory human touchpoint
│  "Good to go?"       │    PR comment / CLI / Slack
└──────────┬────────────┘
           │ REJECT → Return to Builder
           │ APPROVE
           ▼
┌───────────────────────────────────────────────────┐
│  Production Deploy (Deploy Specialist)             │
│  • Creates/updates Fly app (org/region)           │
│  • Custom domain + SSL                           │
│  • Env vars + secrets                            │
│  • DNS update                                    │
│  • Mark "Production Live" in SQLite ledger        │
└───────────────────────────────────────────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `promotion_pipeline.py` | Orchestrator: build→review→preview→approval→deploy |
| `.github/workflows/kilo-review.yml` | Auto-trigger Kilo on PRs |
| `conductor/security_gate.py` | Hardened thresholds (perf ≥ 95, etc.) |
| `skills/agentic/github_strategy_agent.py` | Repo creation under Alira-os org |

### Preview Banner (Creative Enhancement)

Time-limited public preview (7 days) with excitement banner injected into pages:

```html
<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); ...">
  ⚠️ Preview Mode — This is a preview of the new {site_name} website
  — This is NOT the live site
  Preview expires in 7 days
</div>
```

---

## GitHub Strategy (Alira-os Org + Per-Site Repos)

### Org Structure

```
Alira OS (GitHub Organization) ← https://github.com/Alira-os
├── elyra                          ← Elyra project itself
├── saint-joseph-the-worker-academy  ← Per-site repos (created post-local-build)
├── merimee-solutions
├── chesterton-academy-akron
├── holy-rollers
└── ... (one repo per migration/client)
```

### Repo Creation Timing

Per-site repos are created **ONLY** when:
1. Site migration completes (scraper → architect → marketing → builder)
2. Site has been built locally
3. Builder + SEO signals "ready for deploy"

### Kilo Integration

- **Auto-trigger Kilo Code Reviewer** on every PR via `.github/workflows/kilo-review.yml`
- **Client portal** via GitHub Discussions (clients can ask for updates)
- **Branch protection** + required status checks (CI + security gate)
- **Ownership transfer**: `gh repo transfer` as final human-approved step

---

## Reference

- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- LangGraph Checkpointing: https://langchain-ai.github.io/langgraph/how-tos/persistence/
- NORTH_STAR.md: Vision and phasing (stable)
- RETROSPECTIVE_PHASE0.md: Phase 0 learnings