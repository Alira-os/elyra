# Phase 0 — Tasks (MVP)

**Status:** Not started
**Goal:** One successful end-to-end migration. Fidelity ≥ 55%.
**Conductor trace:** Clean bullet summary, no verbose logs.

---

## How to Use This Doc

Work through tasks in order. Check off each item as completed. Dependencies are noted. If a task is blocked, note why and continue if possible.

---

## Phase 0 — Task List

### 1. Repository Setup

- [ ] **1.1** Initialize git in elyra (already done, skip)
- [ ] **1.2** Push to GitHub (already done, skip)
- [ ] **1.3** Create directory structure (already done, skip — verify with quick-system-scan)
- [ ] **1.4** Add `tests/` and `examples/test_sites/` directories

**Verify:** `ls` shows conductor/, registry/, memory/, debate/, tools/, personas/, skills/, onboarding/, infra/, docs/, tests/, examples/

---

### 2. Persona Definitions (4 MVP personas)

**Owner:** Agentic workflow design skill + new conversation agent

- [ ] **2.1** `registry/personas/migration_orchestrator.md` — Conductor persona
  - Role, responsibilities, skills it can call, edge case handling, what it passes to next persona
  - Include routing logic description, confidence thresholds, LLM override trigger

- [ ] **2.2** `registry/personas/onboarding_specialist.md` — Requirements gathering
  - 5 adaptive questions max, structured context output format, platform detection from URL

- [ ] **2.3** `registry/personas/scraper_specialist.md` — Content extraction
  - Playwright + Fetch usage, how it structures output for codegen, SEO considerations

- [ ] **2.4** `registry/personas/deploy_specialist.md` — GitHub + hosting
  - GitHub repo creation, Netlify deploy, CI/CD wiring, rollback approach

**Verify:** Each persona markdown is ≥ 200 words, has all required sections

---

### 3. Skill Definitions (6 Phase 0 skills)

**Owner:** Tool engineering skill + agent-memory-state skill

Each skill is a **pair**: markdown guidance + Python callable

- [ ] **3.1** `skills/memory_query.md` + `skills/executable/memory_query.py`
  - Stub: returns "no prior lessons found" + logs query for later LanceDB integration
  - Interface: `query_similar_sites(platform, task_type) -> list[dict]`

- [ ] **3.2** `skills/platform_detector.md` + `skills/executable/platform_detector.py`
  - Detect: Wix, Squarespace, WordPress, generic
  - Interface: `detect_platform(url) -> {platform, confidence}`

- [ ] **3.3** `skills/routing_heuristics.md` + `skills/executable/routing_heuristics.py`
  - Hard-coded routing rules for known (platform, task_type) pairs
  - Interface: `get_routing_sequence(platform, task_type, confidence_threshold) -> list[str]`

- [ ] **3.4** `skills/lighthouse.md` + `skills/executable/lighthouse.py`
  - Run Lighthouse CI, parse score
  - Interface: `run_lighthouse(url) -> {performance, accessibility, seo, final_score}`

- [ ] **3.5** `skills/npm_audit.md` + `skills/executable/npm_audit.py`
  - Run npm audit, parse vulnerabilities
  - Interface: `run_npm_audit(project_dir) -> {critical, high, medium, low, passed}`

- [ ] **3.6** `skills/seo_optimizer.md` + `skills/executable/seo_optimizer.py`
  - LLM prompt guidance for SEO optimization (no executable needed — guidance only)
  - Include: meta tags, heading hierarchy, image alt text, semantic HTML, schema markup

**Verify:** Each skill has both markdown and .py file. `python -c "from skills.executable import *"` succeeds.

---

### 4. Registry Query Interface

**Owner:** Tool engineering skill

- [ ] **4.1** `registry/registry.py`
  - `load_persona(name) -> dict`
  - `load_skill(name) -> {markdown, callable}`
  - `load_tool(name) -> dict`
  - `list_personas() -> list[str]`
  - `list_skills() -> list[str]`

**Verify:** `python registry/registry.py` runs without error

---

### 5. Tools — OpenCode Interface + MCP Clients

**Owner:** MCP integration specialist skill + tool engineering skill

- [ ] **5.1** `tools/opencode.py`
  - `invoke_opencode(prompt: str, context: dict, working_dir: str) -> str`
  - Subprocess call to opencode CLI
  - Graceful error handling, returns stdout or error message

- [ ] **5.2** `tools/mcp/playwright.py` — MCP client stub
  - Interface for site scraping, structure extraction
  - `scrape_site(url) -> {title, structure, content, images}`

- [ ] **5.3** `tools/mcp/fetch.py` — MCP client stub
  - Clean content extraction
  - `fetch_content(url) -> {clean_html, text, metadata}`

- [ ] **5.4** `tools/mcp/github.py` — MCP client stub
  - Repo creation, file push, Actions trigger
  - `create_repo(name) -> str` (repo URL)
  - `push_files(repo_url, files) -> bool`
  - `trigger_workflow(repo_url, workflow_name) -> bool`

- [ ] **5.5** `tools/mcp/netlify.py` — MCP client stub
  - Deploy site, get preview URL
  - `deploy_site(project_dir) -> str` (preview URL)

**Verify:** All `tools/mcp/*.py` files import without error (may not connect to real MCP servers yet — stub is fine for now)

---

### 6. Memory Layer — SQLite

**Owner:** Agent-memory-state skill

- [ ] **6.1** `memory/sqlite/schema.sql`
  - migrations table, debate_outputs table, routing_heuristics table

- [ ] **6.2** `memory/sqlite/migrations.py`
  - CRUD for migrations table
  - `create_migration(data) -> str` (returns id)
  - `get_migration(id) -> dict`
  - `update_fidelity(id, score) -> None`
  - `list_migrations() -> list[dict]`

- [ ] **6.3** `memory/sqlite/debates.py`
  - CRUD for debate_outputs table
  - `create_debate(migration_id, result) -> str`
  - `get_debate(id) -> dict`
  - `approve_debate(id) -> None`

- [ ] **6.4** `memory/sqlite/heuristics.py`
  - CRUD for routing_heuristics table
  - `get_heuristic(platform, task_type) -> dict`
  - `update_heuristic(platform, task_type, routing_sequence) -> None`

- [ ] **6.5** `memory/memory.py`
  - Unified interface: `Memory` class that wraps sqlite clients
  - `query_similar_sites(platform, task_type)` — returns empty for now (stub for LanceDB later)

**Verify:** `python -c "from memory.memory import Memory; m = Memory(); print(m.query_similar_sites('wix', 'portfolio'))"` returns `[]`

---

### 7. Conductor — Core Logic

**Owner:** Agentic-workflow-design skill

- [ ] **7.1** `conductor/orchestrator.py`
  - `Conductor` class
  - `run(task_context) -> MigrationResult`
  - Main entry point: takes structured task from onboarding, returns deploy result + trace

- [ ] **7.2** `conductor/state_machine.py`
  - LangGraph state machine
  - States: ONBOARDING → ROUTING → SCRAPING → CODEGEN → SECURITY_GATE → DEPLOY → APPROVAL → DEBATE
  - Transitions defined, checkpointing enabled

- [ ] **7.3** `conductor/routing.py`
  - `route(task_context) -> list[str]` (list of persona names)
  - Heuristic rules first, LLM override if confidence < 0.7
  - Backward routing on failure: if persona fails, try fallback or skip

- [ ] **7.4** `conductor/memory_client.py`
  - Wraps `Memory` class from memory layer
  - `query_and_update(migration_id, event)` — query memory, log results

- [ ] **7.5** `conductor/trace.py`
  - Clean bullet-pointed trace output
  - `Trace` class with `add(step)`, `summary() -> str`
  - Format: `✓ Routing: Wix portfolio → [persona1, persona2, ...]`

**Verify:** `python -c "from conductor.orchestrator import Conductor; c = Conductor(); print('Conductor loaded')"` succeeds

---

### 8. Onboarding — Adaptive Flows

**Owner:** New conversation agent (no skill needed — straightforward logic)

- [ ] **8.1** `onboarding/flows/adaptive.py`
  - `AdaptiveOnboarding` class
  - `run() -> TaskContext` — returns structured dict with url, platform, task_type, stack_preference, notes
  - Max 5 questions, adapts based on answers

- [ ] **8.2** `onboarding/flows/questions.py`
  - Question templates: URL, site type, stack preference, must-haves, timeline
  - `get_next_question(answers_so_far) -> str`

- [ ] **8.3** `onboarding/onboarding.py`
  - `OnboardingPersona` class — loads from registry, returns structured context

**Verify:** `python -c "from onboarding.flows.adaptive import AdaptiveOnboarding; a = AdaptiveOnboarding(); print(a.get_next_question({}))"` returns a question string

---

### 9. Security Quality Gate

**Owner:** New conversation agent (uses skill guidance from lighthouse + npm_audit skills)

- [ ] **9.1** `conductor/security_gate.py`
  - `SecurityQualityGate` class
  - `check(project_dir, staging_url) -> {passed, issues}`
  - Runs: npm_audit, lighthouse (performance ≥ 85, accessibility ≥ 90), basic dependency check
  - Blocks deploy if `passed == False`

**Verify:** `python -c "from conductor.security_gate import SecurityQualityGate; g = SecurityQualityGate(); print('Gate ready')"` succeeds

---

### 10. GitHub Actions CI/CD

**Owner:** Infra template from merimeesoftware/templates repo

- [ ] **10.1** `infra/github/semgrep.yml`
  - Pull from merimeesoftware/templates or create minimal version
  - Runs semgrep on PR

- [ ] **10.2** `infra/github/dependency-review.yml`
  - Pull from merimeesoftware/templates or create minimal version
  - Dependency review on PR

- [ ] **10.3** `infra/github/lighthouse.yml`
  - Lighthouse audit in CI (optional for Phase 0, but include template)
  - Runs on deploy to staging

- [ ] **10.4** `.github/workflows/ci.yml`
  - Main CI workflow: lint, test, security checks

**Verify:** GitHub Actions files are valid YAML (can use `actionlint` if available)

---

### 11. Phase 0 Demo — Hardcoded Test Run

**Owner:** New conversation agent

- [ ] **11.1** `examples/test_sites/` directory with at least 2 test site URLs + expected fidelity baseline

- [ ] **11.2** `conductor/demo.py` or `conductor/demo.sh`
  - Script that runs Conductor on a hardcoded test URL
  - Output: clean trace summary + staging URL or error

- [ ] **11.3** Run demo on real Wix or Squarespace site
  - Verify: trace output is clean bullet format, security gate runs, site deploys

**Verify:** Demo runs end-to-end without code changes (except config). Trace is human-readable.

---

## Task Dependencies

```
1.x → done (skip)
2.x → 1.x (needs directory structure)
3.x → 2.x (needs persona definitions for context)
4.x → 3.x (needs skill definitions)
5.x → 4.x (needs registry)
6.x → 1.x (independent — memory layer)
7.x → 4.x + 6.x (needs registry + memory)
8.x → 2.x (needs persona definitions)
9.x → 3.x + 5.x (needs skills + tools)
10.x → 1.x (independent)
11.x → 2-10 (needs everything wired)
```

---

## Definition of Done per Component

| Component | Done When |
|-----------|-----------|
| Persona markdown | ≥ 200 words, all sections filled, no TODOs |
| Skill pair | Markdown + .py both exist, .py imports without error |
| Registry | `load_persona/skill/tool` all return correct data |
| OpenCode interface | `invoke_opencode` can be called with prompt + context |
| MCP client stub | Imports without error, interface matches spec |
| Memory layer | SQLite CRUD works, `query_similar_sites` returns `[]` |
| Conductor | `Conductor().run(task_context)` completes without error |
| Onboarding | 5 questions max, returns structured TaskContext |
| Security gate | `check()` runs npm audit + lighthouse, blocks if failed |
| GitHub Actions | Valid YAML, references correct env vars |
| Demo | Runs end-to-end, output is clean bullet trace |

---

## Priority Order for Building

1. **First sprint:** Tasks 2.1–2.4 (personas) + 3.1–3.3 (core skills) + 6.x (memory — independent)
2. **Second sprint:** Tasks 4.x (registry) + 5.x (tools/opencode) + 7.x (conductor core)
3. **Third sprint:** Tasks 8.x (onboarding) + 9.x (security gate) + 10.x (CI/CD)
4. **Fourth sprint:** Task 11.x (demo end-to-end)

---

## Known Gaps to Solve Later

- Render MCP not in MVP (Netlify only for Phase 0)
- Semgrep via GitHub Actions only (CLI not required for MVP)
- Accessibility auditor skill not in MVP (deferred)
- Stack intelligence persona not in MVP (Conductor handles stack choice via heuristics)
- Content philosopher skill not in MVP (deferred to Phase 2)
- LanceDB vector store not in MVP (stubbed, returns empty)
- Debate Arena not in MVP (Phase 1)

---

## Reference

- North Star: `docs/NORTH_STAR.md`
- Local skills (use proactively):
  - `~/.config/opencode/skills/agentic-workflow-design/` — LangGraph state machine
  - `~/.config/opencode/skills/tool-engineering/` — Tool binding, MCP stubs
  - `~/.config/opencode/skills/mcp-integration-specialist/` — MCP wiring
  - `~/.config/opencode/skills/agent-memory-state/` — SQLite schema
  - `~/.config/opencode/skills/quick-system-scan/` — Verify structure
  - `~/.config/opencode/skills/standard-system-review/` — Review each component
- Local prompts:
  - `~/.config/opencode/prompts/task-decomposition.prompt.md` — Break down tasks
  - `~/.config/opencode/prompts/quality-gate.prompt.md` — Define done-ness