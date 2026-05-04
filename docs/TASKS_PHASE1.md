# Phase 1 Tasks — Compounding

**Status:** In Progress
**Started:** 2026-05-04
**Goal:** Memory works, routing visibly improves, Debate Arena groundwork laid

---

## Phase 1 Thesis (Refined)

Memory must stop being a database and become a learning organism. The Conductor must stop being a state machine and become a meta-reasoner that can birth new micro-personas or spawn internal debates when patterns break.

Every migration is no longer an output — it is **training data** that mutates the system itself.

### What Phase 1 Is NOT
- NOT just "wiring stubs" — we are installing the first nervous system that lets Elyra feel its own failures and grow new reflexes
- NOT incremental improvement — Phase 1 is the moment Elyra acquires agency

---

## Four Milestones

### M1: Detection & Routing as Self-Aware Systems (P0)

**Completed in prior session:**
- [x] #7 Platform Detector v2 — Multi-stage detection with HTML fetch
- [x] #8 Routing Confidence Adjustment — "Ignorance-Aware Confidence"

**Pending from thesis:**
- [ ] Meta-detector LLM call (Stage 2) when confidence < 0.6
  - This becomes the first true LLM override in the system
  - Trace output: `[LOW CONFIDENCE] Platform detection inconclusive → LLM review triggered`

---

### M2: OpenCode as First-Class Tool + Real MCP Wiring (P0/P1 overlap)

**Completed:**
- [x] #10 OpenCode as LangGraph Tool — Structured output, retries, LangGraph `@tool`

**This session (P1):**
- [ ] #9 Wire Playwright MCP (highest leverage)
- [ ] Wire GitHub MCP
- [ ] Wire Fly.io MCP

**From thesis — Codegen as Evolutionary Operator:**
- [ ] Every OpenCode invocation carries "mutation seed" from memory
  - "The last 3 similar sites used contentlayer for MDX blogs and achieved 0.91 fidelity"
  - First tiny step toward memory-driven codegen bias

---

### M3: Real Migrations + Memory Population (P1)

**Goals:**
- Run 3-5 diverse real migrations (Wix custom domain, Squarespace, WordPress, edge case)
- Every migration writes:
  - Full routing trace + confidence history
  - Fidelity score (human + automated)
  - "Lesson vector" (summary embedding + structured tags)

**From thesis — Memory as Evolutionary Pressure:**
- After 5th migration: first Pattern Weaver job
  - Cluster successful vs. failed migrations
  - Propose 1-2 new default routing sequences
  - Proposals go to "Canary Debate" before promotion to routing_heuristics.py

**Issues:**
- [ ] #11 End-to-end real migration harness + memory write pipeline
- [ ] #12 Pattern Weaver v0.1 (cross-migration synthesis) — Phase 1.5

---

### M4: Debate Arena Groundwork + Preview as First-Class (P2/parallel)

**From thesis:**
- Ephemeral Preview Machines on Fly.io
  - Spins up ephemeral Fly Machine (not final app)
  - Runs Review Agent (Playwright + accessibility narrator)
  - Human approval becomes: "Explore this living preview" not "view static screenshot"
- Debate Arena template v0.1 (structured failure reflection)

**Issues:**
- [ ] #13 Ephemeral Preview Machines + Review Agent — Phase 2
- [ ] #14 Debate Arena template v0.1 — Phase 2

---

## Memory Crystallization Layer (Future)

After every debate or low-fidelity migration, LLM call distills event into micro-skill fragment:
- "When migrating Wix e-commerce with >50 products, always add ProductGrid with infinite scroll"
- Fragments stored as versioned, queryable objects
- Injected into future codegen_crew_lead prompts

**Trade-off:** Slight increase in latency + token cost per migration vs. massive long-term compounding.
**Decision:** Accept — this is how Elyra becomes antifragile.

---

## Conductor as Meta-Reasoner (Future)

Introduce "Recursive Sub-Conductors":
- Main Conductor can spawn temporary sub-Conductor for: "resolve scraping ambiguity", "debate stack options"
- Sub-Conductor returns: decision + confidence delta + rationale vector

**Trade-off:** More complex state management
**Mitigation:** LangGraph subgraphs (already in ARCHITECTURE.md target state)

**Decision:** Phase 2 — requires LangGraph subgraph pattern properly designed

---

## GitHub Issues Status

| # | Title | Priority | Status |
|---|-------|----------|--------|
| 7 | Platform Detection v2 — Multi-Stage Detection | P0 | CLOSED ✅ |
| 8 | Routing Confidence Adjustment | P0 | CLOSED ✅ |
| 10 | OpenCode as LangGraph Tool | P0 | CLOSED ✅ |
| 9 | Wire Real MCP Clients (Playwright, GitHub, Fly.io) | P1 | OPEN |
| 11 | Memory Population — Run 3-5 Real Migrations | P1 | OPEN |
| 12 | Pattern Weaver v0.1 | P1 | Not created — Phase 1.5 |
| 13 | Ephemeral Preview Machines + Review Agent | P2 | Not created — Phase 2 |
| 14 | Debate Arena template v0.1 | P2 | Not created — Phase 2 |

---

## Verification Commands

```bash
# Platform detection (wixstudio.com)
python -c "from skills.executable.platform_detector import detect_platform; r = detect_platform('https://merimeesolutions.wixstudio.com/my-site-2'); print(r['platform'] + ' (' + str(r['confidence']) + ')')"

# Routing confidence (generic with low detection)
python -c "from conductor.routing import Router; r = Router(); result = r.route({'platform': 'generic', 'task_type': 'generic', 'platform_confidence': 0.0}); print('conf=' + str(result['confidence']) + ', override=' + str(result['requires_override']))"

# OpenCode tool
python -c "from tools.opencode import invoke_opencode_simple; r = invoke_opencode_simple('Create hello world'); print('success=' + str(r.success))"
```

---

## Files Modified This Phase

| File | Change |
|------|--------|
| `skills/executable/platform_detector.py` | Multi-stage detection, wixstudio.com, HTML fetch |
| `skills/platform_detector.md` | Updated documentation |
| `conductor/routing.py` | Ignorance-aware confidence adjustment |
| `tools/opencode.py` | ToolResult dataclass, LangGraph tool factory |
| `conductor/orchestrator.py` | Updated to use ToolResult |

---

## Next Steps (This Session)

1. Create feature branch for Phase 1
2. Wire Playwright MCP (Phase 1.1)
3. Wire GitHub MCP (Phase 1.2)
4. Wire Fly.io MCP (Phase 1.3)
5. Run test migration with new platform detection
6. Verify memory writes correctly

---

## Reference
- NORTH_STAR.md — Vision + phasing
- ARCHITECTURE.md — Implementation details
- Phase 0 Retrospective: docs/RETROSPECTIVE_PHASE0.md