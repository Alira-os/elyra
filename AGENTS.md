# AGENTS.md

**Normative.** If anything in this file contradicts a casual reference elsewhere, this file wins. When in doubt, re-read this.

---

## The model

Elyra is built on four concepts. Keeping them straight is the difference between a clean codebase and a tangle of half-implemented proxies.

| Concept | What it is | Where it lives | How it runs |
|---|---|---|---|
| **Agent** | A persona `.md` charter defining a job, paired with a Pydantic schema that structures the response | `registry/personas/*.md` + `models/*.py` | Spawned by `tools/kilo.py:invoke_kilo_safe` — Kilo CLI subprocess receives the persona + a task prompt, the LLM reasons (ReAct), tools get called, output is parsed and validated |
| **Execution layer** | The Kilo CLI runtime and its Python glue | `tools/kilo.py` (`invoke_kilo_safe`, `invoke_kilo`) | Subprocess: `kilo run --auto --format json` → NDJSON → `ToolResult` |
| **Tool (MCP server)** | An external tool provider an agent can call during its ReAct loop | `kilocode/.mcp.json`, `~/.config/kilo/kilo.json` `mcp:` block | Connected to Kilo CLI; LLM picks the tool while reasoning |
| **Structured response** | A Pydantic model the agent's output is validated against | `models/*.py` | Python parser calls `Model(**data)`; lenient parse on failure with gap logged |

---

## The decision rule

**If it has a persona `.md` and produces a Pydantic artifact, it's an agent. If it exposes tools an LLM can call, it's an MCP server. Never both.**

Concrete test: if you find yourself wanting to add `<thing>-mcp` to `kilocode/.mcp.json` or the global `~/.config/kilo/kilo.json` `mcp:` block, ask first: *is `<thing>` a persona (in `registry/personas/`)?* If yes, it belongs in the agent row, not the tool row.

---

## Worked example: the scraper

The scraper is the canonical agent. It is **not** an MCP server.

| Layer | What it is | Concrete file |
|---|---|---|
| Agent | `scraper_specialist` persona | `registry/personas/scraper_specialist.md` |
| Execution layer | Thin Python glue that calls Kilo | `skills/agentic/scraper_agent.py` |
| Tools the agent calls | Playwright MCP, Fetch MCP | `kilocode/.mcp.json` (`playwright`, `fetch`) |
| Structured response | `SiteUnderstanding` Pydantic model | `models/site_schemas.py` |

Entry point: `python scrape.py https://example.com` → `SiteUnderstanding` JSON in `memory/site_understandings/`.

### What the scraper is NOT

- Not a `scraper-mcp` entry in any MCP config. There was one — it's gone.
- Not a Python "MCP client" wrapper in `tools/mcp/`. Those files (if any remain) are stubs from Phase 0 and should be replaced by either a real MCP SDK client or removed entirely.
- Not a separate HTTP gateway. There was a `localhost:8812/mcp` remote entry — that's also gone.

### Why this matters

The scraper is a *thing that thinks*. Its value comes from the LLM reading the persona, choosing which pages to navigate, deciding when it has enough signal, and producing a strategic synthesis. Wrapping it as an MCP server would mean dumbifying it down to a single tool call that returns a single scrape — losing the agentic loop entirely.

The MCP servers it uses (Playwright, Fetch) are *things that act*. They expose a fixed set of tools the LLM can call. They do not reason.

---

## Adding a new agent

1. Create the persona charter: `registry/personas/<name>.md`. Include role, charter, tools the agent may call, output contract (the Pydantic schema as an example object), and any quality rules.
2. Add or extend a Pydantic schema in `models/*.py`.
3. Create thin Python glue: `skills/agentic/<name>_agent.py`. Pattern: `scraper_agent.py` or `architect_agent.py`. Loads persona, builds prompt, calls `invoke_kilo_safe`, parses JSON, validates against schema.
4. Create the entry point: `<name>.py` at repo root if it should be invokable from the CLI.
5. Update `AGENTS.md` if you're establishing a new pattern.

Do **not** add an `<name>-mcp` entry to any MCP config.

## Adding a new tool (MCP server)

1. Decide if it really is a tool (exposes callable functions the LLM can pick during reasoning) and not an agent. See decision rule above.
2. Add it to `kilocode/.mcp.json` (project-local) or `~/.config/kilo/kilo.json` `mcp:` block (user-global).
3. Reference the tool by name in the relevant persona's `Tools You May Use` section.

Do **not** create a persona `.md` for it.

---

## Kilo session isolation

Elyra-spawned Kilo sessions do not pollute the user's normal TUI session list. `tools/kilo.py` redirects each migration's `kilo.db` and logs to `%LOCALAPPDATA%\kilo-elyra\<session_id>\` via `XDG_DATA_HOME` (see `tools/kilo_sandbox.py` for the contract). For forensics, inspect a sandbox with `XDG_DATA_HOME=%LOCALAPPDATA%\kilo-elyra\<session_id>\kilo kilo session list`. Set `ELYRA_KILO_NO_SANDBOX=1` to reproduce today's behaviour (sessions land in the user's normal DB) when debugging user-reported issues.

---

## Cross-references

- `docs/NORTH_STAR.md` — vision and phasing
- `docs/ARCHITECTURE.md` — detailed architecture reference (incl. MCP wiring)
- `docs/archive/RETROSPECTIVE_PHASE0.md` — history of the Phase 0 mistakes this doc prevents
