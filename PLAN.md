# Elyra Architecture & Implementation Plan (Updated 2026-07-20)

## Vision
Elyra is a packaged AI CLI tool (`elyra`) that:
- Greets the user with a dynamic prompt ("Hello, what site would you like to migrate, edit, refine, or optimize today?")
- Hands control to `MigrationManager` (the "thin veil")
- The Manager orchestrates personas via a **pluggable `ExecutionBackend`**
- End users never see or care which backend (Kilo, Codex, Claude Code, Copilot CLI, …) is underneath

## Canonical Three-Layer Model

| Layer | Location | Purpose | Ships with package? |
|---|---|---|---|
| **A. Execution runtime** | `tools/execution/` (`backend_kilo.py`, `backend_mock.py`, …) | Pluggable subprocess LLM invocation + structured output | Yes (as dependency) |
| **B. Elyra product** | `registry/personas/*.md`, `models/*.py`, `conductor/orchestrator.py:MigrationManager`, `memory/`, `registry/registry.py` | Personas, Pydantic contracts, orchestrator loop | **Yes – the product** |
| **C. Dev shell** | `.kilo/`, `AGENTS.md`, `kilo.json` | Your local Kilo config while editing Elyra | No (gitignored) |

`.kilo/plans/` has been removed from git (Layer C scratch).

## Conductor Status
Dead. Only `MigrationManager` exists. `AGENTS.md:141` and all references confirm: do not instantiate `Conductor`. The old `conductor/state_machine.py` types and `run_orchestrator.py` are legacy scaffolding.

## Directory Layout (Final)
- `registry/personas/*.md` — human-readable charters (role, tools, output contract example)
- `models/*.py` — Pydantic output schemas (the contract)
- `skills/agentic/` — **deleted entirely** (see below)
- `skills/executable/` — deterministic helpers (lighthouse, npm_audit, …) — kept
- `tools/execution/` — the only place that knows how to turn `(persona, prompt, output_model)` into a typed result
- `conductor/orchestrator.py` — `MigrationManager` only

## The Agent Definition (No Thin Glue)
An agent is now defined by the triple:

```
(persona.md charter) + (Pydantic output model) + (backend.invoke)
```

There are **no** `*_agent.py` files. The Manager (and direct CLI entrypoints like `scrape.py`, `marketing.py`, `architect.py`) call the backend directly:

```python
from tools.execution import get_backend
from models.site_schemas import SiteUnderstanding
from registry import load_persona

backend = get_backend()
persona = load_persona("scraper_specialist")
site: SiteUnderstanding = backend.invoke(
    persona=persona,
    prompt=f"Scrape {url} and produce a SiteUnderstanding",
    output_model=SiteUnderstanding
)
```

All the internal `load_site_understanding`, `build_*_prompt`, and circular imports that currently live inside the `*_agent.py` files are removed. The Manager constructs artifact paths itself or uses small helpers in `memory/`.

## Implementation Phases

### Phase 0 – Backend Abstraction (30–60 min)
- Create `tools/execution/__init__.py` with `ExecutionBackend` protocol + `get_backend()` factory (env var / `kilo.json` driven).
- Move `tools/kilo.py` into `tools/execution/backend_kilo.py` as `class KiloBackend(ExecutionBackend)`.
- Add `class MockBackend(ExecutionBackend)` for fast deterministic tests.
- `invoke(self, persona: str|Path, prompt: str, output_model: Type[BaseModel]) -> BaseModel`

### Phase 1 – Remove Thin Glue (1–2 days)
- Delete every file in `skills/agentic/*_agent.py` (scraper, architect, marketing, designer, builder, seo, geo, github_strategy, …).
- Update every caller (`conductor/orchestrator.py`, `scrape.py`, `marketing.py`, `architect.py`, tests) to call `backend.invoke(...)` directly.
- Move any shared prompt-building or loading helpers into `memory/` or `registry/` if truly needed; otherwise inline in the Manager.
- Update `AGENTS.md` to reflect the new definition of an agent.

### Phase 2 – CLI Entry Point & Greeting
- New root `elyra.py` (or `cli.py` + `__main__.py`):
  ```python
  def main():
      print(dynamic_greeting())          # small LLM turn or templated
      url = input("URL: ")
      task = input("Task (migrate/edit/refine/optimize): ")
      ctx = {"url": url, "task_type": task, ...}
      manager = MigrationManager(backend=get_backend())
      result = manager.run(ctx)
  ```
- The greeting can be a tiny first-turn `MigrationManager` invocation with a "greeter" persona or a static + dynamic prompt.
- `pyproject.toml` exposes `elyra` console script.

### Phase 3 – Packaging, Docs, Testing
- Unit tests use `MockBackend`.
- Integration tests use real `KiloBackend` + sandboxed sessions (`tools/kilo_sandbox.py`).
- E2E via the `elyra` CLI against fixtures in `memory/site_understandings/`.
- Add `docs/CLI.md`.
- Update `AGENTS.md` with the backend contract and the "no thin glue" rule.

## Why This Pattern Is Better
- Removes ~10 files of repetitive glue and circular imports.
- The persona + schema + backend call is the complete, minimal agent definition.
- Matches 2025–2026 industry direction (Pydantic AI, Instructor, LangGraph `with_structured_output`).
- The Manager remains the single source of truth for orchestration.
- Execution runtime is fully pluggable without touching any persona or model code.

## Current State vs Target
- ✅ `.kilo/plans/` untracked
- ✅ Conductor eliminated
- ❌ `skills/agentic/*_agent.py` still exist and are imported everywhere
- ❌ No `tools/execution/` abstraction yet
- ❌ No `elyra` CLI entrypoint with greeting

Next concrete step: implement Phase 0 (the backend seam) and then Phase 1 (delete the glue).

This plan supersedes all previous versions.
