# Elyra AI Website Migration Engine

**Phase 0 MVP** — AI-powered website migration with guided dynamic orchestration.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/merimeesoftware/elyra.git
cd elyra

# Run the demo (requires OpenCode to be installed)
python conductor/demo.py

# Or use a specific URL
python conductor/demo.py https://example.wixsite.com
```

## Architecture

Elyra uses a **Conductor + Memory** pattern where:

1. **Conductor** (meta-agent) orchestrates the migration workflow
2. **Personas** (specialists) handle different aspects: onboarding, scraping, codegen, deploy
3. **Skills** (markdown + Python pairs) provide reusable capabilities
4. **Memory** persists learnings across migrations

## Directory Structure

```
elyra/
├── conductor/          # Conductor orchestrator, routing, state machine
├── registry/           # Persona, skill, tool definitions
│   └── personas/      # 4 MVP personas (markdown)
├── memory/            # SQLite + LanceDB (stubbed) memory layer
├── skills/            # Skill definitions
│   └── executable/    # 6 Phase 0 skill callables
├── tools/             # OpenCode interface + MCP clients
│   └── mcp/           # Playwright, Fetch, GitHub, Netlify stubs
├── onboarding/        # Adaptive onboarding flows
├── .github/workflows/  # CI/CD with GitHub Actions
├── examples/test_sites/ # Test site configurations
└── docs/              # Architecture docs
```

## Phase 0 Features

- [x] 4 Personas: migration_orchestrator, onboarding_specialist, scraper_specialist, deploy_specialist
- [x] 6 Skills: memory_query, platform_detector, routing_heuristics, lighthouse, npm_audit, seo_optimizer
- [x] Conductor with LangGraph state machine + heuristic routing
- [x] SQLite memory layer (vector stubbed until Phase 1)
- [x] OpenCode tool interface for heavy codegen
- [x] MCP client stubs: Playwright, Fetch, GitHub, Netlify
- [x] SecurityQualityGate (npm audit + lighthouse)
- [x] GitHub Actions CI/CD workflows
- [x] Adaptive onboarding (5 questions max)

## Status

**Phase 0 MVP** — Complete scaffolding, ready for testing on real sites.

## License

MIT