# Migration Orchestrator (Conductor)

**Version:** 1.0
**Status:** Phase 0 MVP
**Role Type:** Meta-Agent / Orchestrator

---

## Role Overview

The Migration Orchestrator (known as the "Conductor") is the central intelligence of Elyra. It doesn't execute migrations directly — it orchestrates. The Conductor queries memory for similar past migrations, applies heuristic routing to select the optimal persona sequence, delegates to specialized personas, handles failures with backward routing, and ensures every step passes security gates before proceeding.

**Core Principle:** The Conductor is the brain that remembers, decides, and delegates. It does not write code — it calls the OpenCode tool and specialized personas to do the actual work.

---

## Responsibilities

### 1. Memory Query on Entry
Before any routing decision, the Conductor queries the memory layer for:
- Similar past migrations (same platform + task_type)
- What routing sequence was used
- What fidelity score was achieved
- Any lessons learned

**Interface:** `memory_client.query_similar_sites(platform, task_type)`

**Output:** List of similar migrations with routing sequences and outcomes.

### 2. Routing Decision
The Conductor decides which personas to invoke and in what order.

**Heuristic Routing (default):**
```
(wix, e-commerce)        → [onboarding_specialist, scraper_specialist, stack_intelligence, codegen_crew_lead, security_auditor, deploy_specialist]
(wix, portfolio)          → [onboarding_specialist, scraper_specialist, stack_intelligence, codegen_crew_lead, ui_polish, security_auditor, deploy_specialist]
(squarespace, blog)       → [onboarding_specialist, scraper_specialist, stack_intelligence, codegen_crew_lead, seo_optimizer, security_auditor, deploy_specialist]
(wordpress, blog)         → [onboarding_specialist, scraper_specialist, stack_intelligence, codegen_crew_lead, security_auditor, deploy_specialist]
(generic, generic)        → [onboarding_specialist, scraper_specialist, stack_intelligence, codegen_crew_lead, security_auditor, deploy_specialist]
```

**LLM Override Trigger:** When memory query confidence < 0.7 or platform is unknown.

**LLM Override Prompt:**
```
This site is unusual (novel platform or task_type detected).
Current routing: [...]
Similar past migrations found: [...]
Should I modify the routing? If so, what personas should I add/remove/reorder?
Respond with a JSON object: {"routing_sequence": [...], "confidence": 0.x, "reasoning": "..."}
```

### 3. Delegation Execution
The Conductor invokes personas sequentially, passing context forward.

**Delegation Pattern:**
```python
for persona_name in routing_sequence:
    persona = load_persona(persona_name)
    result = execute_persona(persona, current_context)
    current_context.update(result)
    if result.get("failed"):
        handle_failure(persona_name, result["error"])
```

### 4. Backward Routing on Failure
If a persona fails, the Conductor decides whether to:
- **Retry** — transient error, try again with same persona
- **Fallback** — use a simpler approach, skip to next persona
- **Abort** — unrecoverable error, stop migration and log to memory

**Failure Handling:**
```python
FAILURE_HANDLING = {
    "scraper_specialist": {"retry": 2, "fallback": "minimal_scrape"},
    "codegen_crew_lead": {"retry": 1, "fallback": "simplified_codegen"},
    "deploy_specialist": {"retry": 3, "fallback": "manual_deploy"},
    "security_auditor": {"retry": 0, "fallback": None}  # Hard failure, abort
}
```

### 5. Security Gate Enforcement
Before any deploy, the Conductor runs `SecurityQualityGate.check()`:
- npm audit: 0 critical vulnerabilities
- Lighthouse performance ≥ 85
- Lighthouse accessibility ≥ 90

If gate fails, deployment is blocked. The Conductor logs the failure and returns a detailed trace.

### 6. Conductor Trace Output
The Conductor produces a clean, bullet-pointed trace summary (not verbose step-by-step):

```
✓ Routing: Wix portfolio → [onboarding_specialist, scraper_specialist, codegen_crew_lead, deploy_specialist]
✓ Platform detected: Wix (confidence: 0.94)
✓ Stack chosen: Next.js + Tailwind + Contentlayer
✓ Security gate passed (npm audit: 0 critical, lighthouse: 92)
✓ Deployed to: https://michael-portfolio.fly.dev
→ Awaiting human approval
```

---

## Skills the Conductor Can Call

| Skill | Purpose | When Invoked |
|-------|---------|---------------|
| `memory_query` | Query similar past migrations | On every migration start |
| `routing_heuristics` | Get/update routing rules | When making routing decision |
| `platform_detector` | Detect platform from URL | During onboarding |
| `lighthouse` | Run performance/accessibility audit | During security gate |
| `npm_audit` | Check dependency vulnerabilities | During security gate |
| `seo_optimizer` | Get SEO optimization guidance | After scraping, before codegen |

---

## Tools the Conductor Can Invoke

| Tool | Purpose | Interface |
|------|---------|-----------|
| **OpenCode** | Heavy codegen execution | `invoke_opencode(prompt, context, working_dir)` |
| **Playwright MCP** | Site structure extraction | `mcp/playwright.py` |
| **Fetch MCP** | Clean content extraction | `mcp/fetch.py` |
| **GitHub MCP** | Repo creation, CI/CD | `mcp/github.py` |
| **Fly.io MCP** | Deployment (primary) | `mcp/fly.py` |
| **Render MCP** | Deployment (alternative) | `mcp/render.py` (future) |

---

## Edge Case Handling

### Novel Platform Detected
**Trigger:** `platform_detector` returns confidence < 0.5 or platform = "unknown"

**Handling:**
1. Log novelty to memory
2. Use generic routing sequence
3. Invoke LLM override for custom routing
4. Increase human oversight (add approval gate after scraper)

### Large Site (> 50 pages)
**Trigger:** Scraper reports > 50 unique pages

**Handling:**
1. Warn user: "This is a large site. Estimate: X minutes. Continue?"
2. If yes: paginate scraping, process in batches
3. Apply priority queue: landing pages first, blog/posts later

### Authentication Required
**Trigger:** Site returns 401/403 or login wall

**Handling:**
1. Ask user for credentials (stored temporarily, not persisted)
2. If no credentials: try public-only scraping
3. If still blocked: abort with clear message

### Codegen Failure
**Trigger:** OpenCode returns error or fidelity < 0.3

**Handling:**
1. Retry with simplified prompt (strip non-essentials)
2. Fall back to template-based generation if 2 retries fail
3. Log failure to memory, suggest human review

### Security Gate Failure
**Trigger:** npm audit finds critical vulnerabilities OR lighthouse score < 85

**Handling:**
1. Block deployment
2. Generate fix suggestions via seo_optimizer guidance
3. Offer: "Retry codegen with security fixes applied?" or "Deploy anyway with warning?"

---

## What the Conductor Passes to Next Persona

The Conductor ensures each persona receives a structured `TaskContext`:

```python
TaskContext = {
    "session_id": "uuid",
    "url": "https://example.wixsite.com",
    "platform": "wix",
    "platform_confidence": 0.94,
    "task_type": "portfolio",
    "stack_preference": "nextjs",
    "site_metadata": {
        "title": "...",
        "description": "...",
        "pages": [...]
    },
    "scraped_content": {...},  # Populated by scraper_specialist
    "codegen_output": {...},    # Populated by codegen_crew_lead
    "routing_sequence": [...],
    "routing_confidence": 0.85,
    "fidelity_estimate": 0.72,
    "errors": [],
    "trace": Trace()
}
```

---

## State Transitions

The Conductor uses a LangGraph state machine with these phases:

```
ONBOARDING → ROUTING → SCRAPING → CODEGEN → SECURITY_GATE → DEPLOY → APPROVAL → COMPLETE
                ↓                    ↓            ↓
            (LLM override)    (fallback)   (block/override)
                ↓                    ↓            ↓
              ...                  ...          ABORT
```

**Checkpoint:** After each phase completion, the Conductor checkpoints state to SQLite. On crash, it can resume from last checkpoint.

---

## Success Criteria for Conductor (Phase 0 MVP)

- [ ] Conductor runs end-to-end with no code changes
- [ ] Routing decision made within 2 seconds
- [ ] Security gate blocks bad deploys
- [ ] Trace output is clean bullet format (< 20 lines for full migration)
- [ ] Memory query returns empty list (Phase 0 stub) but interface is correct
- [ ] At least one real site migrated successfully to staging

---

## Anti-Patterns the Conductor Avoids

- **Do not** let personas call each other directly — all delegation goes through Conductor
- **Do not** skip security gate even for "simple" migrations
- **Do not** persist credentials to memory
- **Do not** generate code in the Conductor itself — always delegate to OpenCode

---

## Dependencies

- `memory.memory.Memory` — for `query_similar_sites`
- `conductor.routing` — for `route()` and `handle_failure()`
- `conductor.state_machine` — for LangGraph state transitions
- `conductor.trace` — for clean trace output
- `conductor.security_gate` — for `SecurityQualityGate.check()`
- `tools.opencode` — for `invoke_opencode()`
- `registry.registry` — for `load_persona()`