# TECH_STACK

**As of:** 2026-08-16
**Repo:** merimeesoftware/elyra
**Evidence:** committed files on `master` only. Gaps marked unknown.

## Universal target

Cursor + MCP + skills → GitHub Actions → Cloudflare (Pages/Workers) when practical.

## Current stack

| Layer | Current | Evidence | Alignment |
|-------|---------|----------|-----------|
| Agent surface | Python Phase 0 Conductor + Memory orchestration; 4 personas in `registry/personas/`; OpenCode subprocess for heavy codegen (`tools/opencode.py`); adaptive onboarding (`onboarding/flows/`) | `README.md`, `conductor/`, `registry/`, `tools/opencode.py`, `onboarding/` | partial |
| Source + CI | Python application tree (no `package.json`, no `requirements.txt`, no `pyproject.toml`); GitHub Actions: `ci.yml` (Node 20, `npm ci` / lint / typecheck / test / audit), `deploy-staging.yml` (npm build; deploy steps commented), `semgrep.yml` (`p/javascript` rules) | `.github/workflows/ci.yml`, `.github/workflows/deploy-staging.yml`, `.github/workflows/semgrep.yml`, `git ls-files` | mismatch |
| Runtime / deploy | Local Python process; no Dockerfile, `docker-compose.yml`, or `wrangler.toml` in repo; `deploy-staging.yml` Fly.io deploy block is commented; Lighthouse job falls back to `https://staging.fly.dev`; docs describe Fly.io (primary) and Render (alternative) as Phase 1+ targets | `docs/ARCHITECTURE.md`, `.github/workflows/deploy-staging.yml`, `tools/mcp/fly.py`, `README.md` | mismatch |
| Data / storage | SQLite metadata (`memory/sqlite/schema.sql`, `memory/sqlite/crud.py`, `memory/memory.py`); LanceDB vector layer stubbed (Phase 1 per `README.md`) | `memory/`, `README.md` | partial |
| Cursor / MCP / skills | 6 skills (markdown + Python in `skills/`); MCP client stubs in `tools/mcp/` (Playwright, GitHub, Fly.io = STUB; Fetch = partial urllib); no `.cursor/` config, no Cursor rules/skills integration, no Cloudflare bindings | `skills/`, `tools/mcp/`, `registry/registry.py` | mismatch |

## Target vs current

- **Alignment:** mismatch
- **Gaps:** No Cloudflare Pages/Workers or `wrangler.toml`; no live deploy workflow (Fly.io/Render steps commented only); CI assumes Node/npm but repo has no `package.json`; workflow triggers use branch `main` while default branch is `master`; MCP clients are Phase 0 stubs, not wired MCP servers; no Cursor IDE integration files; Python deps unpinned (no `requirements.txt` / `pyproject.toml`); Semgrep scans `p/javascript` against a Python-first tree.
- **Cutover notes:**
  - Add or restore a Node app manifest (`package.json`) before `ci.yml` / `deploy-staging.yml` npm steps can succeed, or replace those jobs with Python lint/test (unknown: intended test runner — no `pytest` config or `requirements.txt`).
  - Update `.github/workflows/*.yml` branch filters from `main` to `master` (or rename default branch) so CI runs on the actual default branch.
  - Uncomment and configure Fly.io deploy only when `FLY_API_TOKEN` and app config exist; do not document Fly.io as active hosting until deploy steps are live.
  - Replace `tools/mcp/*.py` stubs with real MCP SDK clients per `docs/ARCHITECTURE.md` before claiming MCP integration.
  - Add Cloudflare deploy workflow and `wrangler.toml` (or Pages config) to align runtime with universal target; none present today.

## Notes

- Phase 0 MVP scaffolding per `README.md`; Conductor runs via `python conductor/demo.py` (requires OpenCode installed — version unknown, not pinned in repo).
- README directory tree notes MCP stubs include "Netlify legacy" comment; no Netlify workflow or config in committed files.
- `lighthouse-budget.json` exists; Lighthouse CI runs in `deploy-staging.yml` against staging URL or hardcoded fallback.
- LangGraph referenced in docs/README; `conductor/state_machine.py` uses Python `TypedDict` + `Enum` (LangGraph-ready, not full LangGraph dependency in committed code — LangGraph package pin unknown, no `requirements.txt`).
