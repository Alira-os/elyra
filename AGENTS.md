# AGENTS.md

**Normative.** If anything in this file contradicts a casual reference elsewhere, this file wins. When in doubt, re-read this.

---

## The model

Elyra is built on four concepts. Keeping them straight is the difference between a clean codebase and a tangle of half-implemented proxies.

| Concept | What it is | Where it lives | How it runs |
|---|---|---|---|
| **Agent** | A persona `.md` charter defining a job, paired with a Pydantic schema that structures the response | `registry/personas/*.md` + `models/*.py` | Invoked by `backend.invoke(persona, prompt, output_model)`. The runtime contract is `(persona.md charter) + (Pydantic model) + (backend.invoke)` — no thin-glue required. |
| **Execution layer** | The pluggable `ExecutionBackend` abstraction (Kilo CLI or mock) | `tools/execution/backend_kilo.py`, `tools/execution/backend_mock.py` | Implements `invoke(persona, prompt, output_model)`; production uses `KiloBackend`, tests use `MockBackend` via `ELYRA_BACKEND` env var |
| **Tool (MCP server)** | An external tool provider an agent can call during its ReAct loop | `kilocode/.mcp.json`, `~/.config/kilo/kilo.json` `mcp:` block | Connected to Kilo CLI; LLM picks the tool while reasoning |
| **Structured response** | A Pydantic model the agent's output is validated against | `models/*.py` | Python parser calls `Model(**data)`; lenient parse on failure with gap logged |

### Routing brain

The Manager persona (`registry/personas/migration_orchestrator.md`) is the
single routing brain for the Planning Room. PLANNING_ROOM and FORGE_ROOM
are containers of personas (`models/site_schemas.py:Room`); PLANNING_ROOM.
`preflight_order` is a *recommended* initial order passed to the Manager
on its first turn, not a hard-coded sequence. The Planning Coherence
Gate (`_run_planning_coherence_gate`) produces structured `GateBlock`
records (persona + reason + gap_id + severity) that the manager
dispatches on — the manager decides *who* fixes a gate failure, not a
procedural fallback. Phase C collapsed the dual routing (procedural
preflight + LLM manager loop) into this single LLM-driven manager loop;
the Forge Room's layered preflight is unchanged.

---

## The decision rule

**If it has a persona `.md` and produces a Pydantic artifact, it's an agent. If it exposes tools an LLM can call, it's an MCP server. Never both.**

Concrete test: if you find yourself wanting to add `<thing>-mcp` to `kilocode/.mcp.json` or the global `~/.config/kilo/kilo.json` `mcp:` block, ask first: *is `<thing>` a persona (in `registry/personas/`)?* If yes, it belongs in the agent row, not the tool row.

---

## Worked example: the scraper

The scraper is the canonical agent. It is **not** an MCP server.

| Layer | What it is | Concrete file |
|---|---|---|
| Agent | `scraper_specialist` persona (~50 lines) | `registry/personas/scraper_specialist.md` |
| Execution layer | Manager dispatch table calls `backend.invoke` directly | `conductor/orchestrator.py:_persona_scraper` |
| Tools the agent calls | Playwright MCP, Fetch MCP, Kilo's own file-writing tools | `kilocode/.mcp.json` (`playwright`, `fetch`) |
| Recon artifact | Directory on disk: `site.json` + `sitemap.md` + `pages/<slug>.md` + `catalog.json` + `visual/` + `content-essence.md` | `memory/site_understandings/<site_id>/` |
| Wire-format | `SiteUnderstanding` (slim — `pages[]` is `List[PageRef]` with file refs) | `models/site_schemas.py` |

Entry point: `python scrape.py https://example.com` → recon directory under `memory/site_understandings/<site_id>/`. Downstream code calls `load_site_understanding(site_id)` which returns the slim `SiteUnderstanding` built via `SiteUnderstanding.from_directory()`. Rich per-page data is read on demand via `read_page(site, slug)`.

### What the scraper is NOT

- Not a `scraper-mcp` entry in any MCP config. There was one — it's gone.
- Not a Python "MCP client" wrapper in `tools/mcp/`. Those files (if any remain) are stubs from Phase 0 and should be replaced by either a real MCP SDK client or removed entirely.
- Not a separate HTTP gateway. There was a `localhost:8812/mcp` remote entry — that's also gone.
- Not a giant Pydantic output contract that the LLM has to fill in one shot. The recon agent writes files during its loop; the only structured output it must emit at the end is the 8-field `site.json`. Per-page content lives in `pages/<slug>.md`. Dynamic catalogs live in `catalog.json`.
- Not a Python "extract and repair JSON from a 2000-char-truncated stdout" defensive pipeline. The agent writes files; we just check that the files exist.

### Why this matters

The scraper is a *thing that thinks*. Its value comes from the LLM reading the persona, choosing which pages to navigate, deciding when it has enough signal, and producing a strategic synthesis. Wrapping it as an MCP server would mean dumbifying it down to a single tool call that returns a single scrape — losing the agentic loop entirely.

The MCP servers it uses (Playwright, Fetch) are *things that act*. They expose a fixed set of tools the LLM can call. They do not reason. Kilo's built-in file-writing tools are also *things that act* — the agent's value is the strategic synthesis it produces by combining them.

### Skills (abstract) vs tools (concrete)

The persona does not enumerate every Playwright or Fetch tool call. It says what the agent is *able to do*:

> You have Playwright (browser automation) and Fetch (HTTP + clean text). You can use any capability these tools expose. Common patterns: use Playwright to navigate JS-heavy sites and capture DOM state; use Fetch for clean text from static pages; use Playwright's `evaluate` to read `__NEXT_DATA__` / `window.__INITIAL_STATE__` / inline JSON for SPA data sources.

The "skill" is the *named pattern* (recon a site, capture the data source, walk a sitemap). The "tools" are the *callable functions* (`browser_navigate`, `fetch_http_get`, etc.). Kilo knows the tool surfaces; the persona teaches the agent which patterns to apply.

---

## Adding a new agent

An Elyra agent is the triple `(persona.md charter) + (Pydantic output model) + (backend.invoke(...))`. No thin-glue `*_agent.py` file is required.

To add a new agent:
1. Create the persona charter: `registry/personas/<name>.md` (role, tools it may call, output contract as an example object, quality rules).
2. Add or extend a Pydantic schema in `models/*.py` defining the agent's output contract.
3. Register the agent in the Manager's dispatch table (`conductor/orchestrator.py:_invoke_persona._DISPATCH`) and write a per-persona handler method (`_persona_<name>`) that:
   - Loads upstream artifacts via `memory.artifacts.load_*`
   - Builds the prompt via `registry.prompts.build_<name>_prompt`
   - Calls `backend.invoke(persona=path, prompt=..., output_model=<Model>)`
   - Persists the artifact to disk
4. The Manager calls `backend.invoke` directly — no separate Python glue file is created.

Do **not** add an `<name>-mcp` entry to any MCP config.

### Execution backend (Layer A)

Elyra is execution-runtime-agnostic. Persona invocations go through an `ExecutionBackend` (Protocol in `tools/execution/__init__.py`) with one method:
```python
def invoke(self, persona: str | Path, prompt: str, output_model: Type[BaseModel]) -> BaseModel
```

Implementations live in `tools/execution/backend_<name>.py`:
- `KiloBackend` — production. Spawns a sandboxed Kilo CLI subprocess and validates the output against `output_model`.
- `MockBackend` — for unit tests. Records calls, returns registered or dummy `BaseModel` instances.

Selection is via the `ELYRA_BACKEND` env var (`kilo` | `mock`) or `kilo.json` `backend` field. Default is `KiloBackend`. The Manager accepts an injected backend via `MigrationManager(backend=...)` — production callers leave it default, tests inject `MockBackend`.

### Packaged CLI (`elyra`)

Elyra ships as a CLI tool. After `pip install -e .`, the user runs:
```
$ elyra https://example.com migrate
```
or interactively:
```
$ elyra
Hello! I'm Elyra — your AI site engineer.
What would you like to work on today?
  • migrate   — reconstruct a site on a modern stack
  • edit      — refine an existing site
  • refine    — improve visual/UX/content quality
  • optimize  — boost SEO, GEO, performance, accessibility
URL:
Task:
```

Source: `elyra/__init__.py` (entrypoint `main()`), `elyra/__main__.py` (`python -m elyra`).
See `docs/CLI.md` for the full reference.

### Discoverability specialists (Phase E)

`seo_specialist` and `geo_specialist` follow the standard pattern but
have one extra wrinkle:

- `seo_specialist` is **planning-only**. It appears in `PLANNING_ROOM.personas`
  and `PLANNING_ROOM.preflight_order` between `marketing_specialist` and
  `ui_designer`.
- `geo_specialist` appears in **both** rooms under the same long name.
  In the Planning Room it produces `GeoStrategy`; in the Forge Room it
  produces `GeoBuildArtifacts` (the actual `llms.txt`, `robots.txt` AI
  stanza, `sitemap.xml` extras, and JSON-LD blocks). The orchestrator
  dispatches based on whether the built site directory exists. See
  `conductor/orchestrator.py:PLANNING_ROOM`, `FORGE_ROOM`, and
  `_invoke_persona` (`elif persona == "geo":`).

`MigrationManager.LOCKED_AI_CRAWLERS` (11 entries) is the canonical
allowlist for `GeoBuildArtifacts.ai_crawler_allowlist`. The human-facing
source of truth is `docs/GEO_FOR_LLMS.md`; keep them in sync.

## Adding a new tool (MCP server)

1. Decide if it really is a tool (exposes callable functions the LLM can pick during reasoning) and not an agent. See decision rule above.
2. Add it to `kilocode/.mcp.json` (project-local) or `~/.config/kilo/kilo.json` `mcp:` block (user-global).
3. Reference the tool by name in the relevant persona's `Tools You May Use` section.

Do **not** create a persona `.md` for it.

---

## What this codebase is NOT

Phase A deleted the following dead code and legacy patterns. **Do not reintroduce them.**

| Deleted file / pattern | Why it was removed | Replacement |
|---|---|---|
| `Conductor` class (`conductor/orchestrator.py`, legacy) | Phase-0 monolithic linear pipeline. The Manager / Room-based `MigrationManager` (in the same module) is the live loop. | `from conductor.orchestrator import MigrationManager` |
| `tools/opencode.py` | OpenCode was replaced by Kilo in Phase 1. All invocation goes through `tools/kilo.py:invoke_kilo_safe`. | `from tools.kilo import invoke_kilo_safe` |
| `tools/mcp/fly.py`, `tools/mcp/github.py` | Phase-0 stubs. Real Fly and GitHub integrations are MCP servers wired in `kilocode/.mcp.json`. | `kilocode/.mcp.json` (`fly`, `github`) |
| `promotion_pipeline.py` (repo root) | 24KB human-approval-gate script. The pattern now lives on `HandoffBundle.requires_human_review`; Phase C wires the GitHub-issue loop. | `HandoffBundle.requires_human_review` field |
| `quick_test_orch.py` (repo root) | Scratch timing instrument. Timing wrappers live in `tests/performance/test_orchestrator_timing.py`. | `tests/performance/test_orchestrator_timing.py` |
| `scratch_fix.py` (repo root) | 158 bytes of debug junk. | Nothing |
| `builder.py` (repo root) | Redundant debug CLI. The Forge Room's `builder_specialist` persona (via `MigrationManager`) is the live path. | `MigrationManager` |
| `registry/personas/ux_architect.md` | Dead persona (not referenced by any Room). | Use `ui_designer` instead |
| Root `elyra_engineer.py` 15KB monolith | Replaced by thin `skills/agentic/elyra_engineer.py` + 50-line root CLI. | `from skills.agentic.elyra_engineer import analyze` |
| `skills/agentic/*_agent.py` (thin glue) | Replaced by direct `backend.invoke(...)` calls in `conductor/orchestrator.py:_invoke_persona` dispatch table | `conductor/orchestrator.py:_invoke_persona` + `registry/prompts.py` |
| `tools/kilo.py` (legacy execution module) | Replaced by pluggable `tools/execution/backend_kilo.py` (one of several backends) | `from tools.execution import get_backend` |

Deprecated patterns to avoid:

- **Do not** import `from tools.opencode import invoke_opencode`. Always use `invoke_kilo_safe`.
- **Do not** instantiate the legacy `Conductor()` class. Use `MigrationManager()`.
- **Do not** write root-level orchestration files (`<thing>_pipeline.py`, `<thing>_orchestrator.py`, etc.). Glue belongs in `skills/agentic/` or `conductor/`.
- **Do not** re-introduce a `promotion_pipeline` module. Promotion flows through `HandoffBundle.requires_human_review` → Manager-emitted `github_issue_created` action.
- **Do not** create `skills/agentic/<name>_agent.py` thin-glue files. The Manager calls the backend directly.
- **Do not** `from tools.kilo import …`. Use `from tools.execution import get_backend` (or inject the backend via `MigrationManager(backend=...)`).

---

## Kilo session isolation

Elyra-spawned Kilo sessions do not pollute the user's normal TUI session list. `tools/execution/backend_kilo.py` redirects each migration's `kilo.db` and logs to `%LOCALAPPDATA%\kilo-elyra\<session_id>\` via `XDG_DATA_HOME` (see `tools/kilo_sandbox.py` for the contract). For forensics, inspect a sandbox with `XDG_DATA_HOME=%LOCALAPPDATA%\kilo-elyra\<session_id>\kilo kilo session list`. Set `ELYRA_KILO_NO_SANDBOX=1` to reproduce today's behaviour (sessions land in the user's normal DB) when debugging user-reported issues.

---

## Cross-references

- `docs/NORTH_STAR.md` — vision and phasing
- `docs/ARCHITECTURE.md` — detailed architecture reference (incl. MCP wiring)
- `docs/archive/RETROSPECTIVE_PHASE0.md` — history of the Phase 0 mistakes this doc prevents
