# Elyra CLI (`elyra`)

The `elyra` command is the single, unified entry point for the Elyra product.
It prints a dynamic greeting, asks for a URL and a task, hands control to
`MigrationManager`, and exits with a summary.

> **Scope.** This CLI is the *only* new root-level command. The existing
> `scrape.py`, `marketing.py`, `architect.py`, `elyra_engineer.py`, and
> `run_orchestrator.py` root CLIs remain as debug entrypoints and are not
> the supported user surface.

---

## Installation

### From a checkout (development)

```bash
git clone <repo-url> elyra
cd elyra
pip install -e .
```

`pip install -e .` exposes an `elyra` console script on `PATH` (via the
`[project.scripts]` entry in `pyproject.toml`).

### Run without installing

You can also invoke the package directly:

```bash
python -m elyra                        # interactive greeting
python -m elyra https://example.com migrate
python -m elyra --help
```

---

## Usage

```
python -m elyra <url> [migrate|edit|refine|optimize]
python -m elyra                       # interactive greeting
python -m elyra --help
```

| Argument        | Required            | Description                              |
|-----------------|---------------------|------------------------------------------|
| `url`           | yes (or prompted)   | The site URL to operate on               |
| `task`          | yes (or prompted)   | One of `migrate`, `edit`, `refine`, `optimize` |
| `--help`, `-h`  | —                   | Print help and exit 0                    |

### Task types

| Task       | What it does                                                                 |
|------------|------------------------------------------------------------------------------|
| `migrate`  | Reconstruct a site on a modern stack (the full Planning + Forge room loop).  |
| `edit`     | Apply targeted edits to an existing site already in memory.                  |
| `refine`   | Improve visual / UX / content quality of an existing built site.             |
| `optimize` | Boost SEO, GEO-for-LLMs, performance, and accessibility.                     |

The four tasks map to the same `MigrationManager.run(...)` entry point; the
manager reads `task_type` from `task_context` and routes accordingly.

---

## Environment variables

| Variable          | Default  | Values           | Purpose                                                                 |
|-------------------|----------|------------------|-------------------------------------------------------------------------|
| `ELYRA_BACKEND`   | `kilo`   | `kilo`, `mock`   | Selects the execution backend. `mock` returns deterministic fixtures and is intended for unit tests and offline runs. |

When `kilo` is selected, the existing `kilo.json` and `kilocode/.mcp.json`
config in the checkout are used (sandboxed per session — see
`tools/kilo_sandbox.py`).

---

## Exit codes

| Code | Meaning                                                            |
|------|--------------------------------------------------------------------|
| `0`  | Migration reached a `complete` state (the Manager finished cleanly). |
| `1`  | Migration did **not** complete — see `phase_reached` in the printed summary. |
| `2`  | Bad CLI input (e.g. unknown task name).                            |

The summary block printed before exit is stable and greppable:

```
[Elyra] phase_reached : <state>
[Elyra] site_slug     : <slug>
[Elyra] success       : <bool>
```

---

## Example transcript (mock backend, interactive)

```
$ ELYRA_BACKEND=mock python -m elyra

Hello! I'm Elyra — your AI site engineer.
What would you like to work on today?
  - migrate   reconstruct a site on a modern stack
  - edit      refine an existing site
  - refine    improve visual/UX/content quality
  - optimize  boost SEO, GEO, performance, accessibility

URL: https://example.com
Task (migrate/edit/refine/optimize): optimize

[Elyra] optimize -> https://example.com

... (manager runs the planning + forge room loop) ...

[Elyra] phase_reached : complete
[Elyra] site_slug     : example
[Elyra] success       : True
$ echo $?
0
```

The mock backend is deterministic and returns immediately, so the transcript
above completes in seconds; the `kilo` backend drives real subprocess
LLM invocations and takes minutes.

---

## Architecture notes

- The CLI is intentionally thin. The greeting is the only logic that lives
  outside `MigrationManager`. Per `AGENTS.md`, no orchestration logic lives
  in this entrypoint.
- The Manager accepts an optional `backend` kwarg (defaulting to
  `tools.execution.get_backend()`). Phase 1 wires that backend into
  every persona invocation; until Phase 1 lands, the Manager retains its
  legacy `tools.kilo.invoke_kilo` calls but already stores and exposes
  `self.backend` for callers and tests.
- The `task_context` built by `elyra.build_context(url, task)` is the same
  shape that `python conductor/orchestrator.py <url>` produces, so the
  legacy debug entrypoint and the new CLI are behaviorally equivalent.
