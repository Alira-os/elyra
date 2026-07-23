# Stitch Workflow

Stitch is the design surface for every site Elyra builds. The
`ui_designer` persona owns Stitch project creation; the
`frontend_architect` persona consumes the screens as its design
reference when building code.

This document is the human-facing guide. It explains the contract, the
edit conventions, and the re-invocation flow.

---

## Overview

Humans can edit Stitch projects directly between planning and forge
runs. The contract is:

- One Stitch project per `site_slug`.
- Project title: `<site_name> Migration`.
- Screens correspond to routes in the architect's
  `SiteArchitecture.pages`.
- The `stitch_project_id` and `stitch_project_url` are captured by
  the `ui_designer` persona and persisted on the VisualDirection
  artifact in `memory/visual_specs/<slug>/<timestamp>.json`.

When the orchestrator hands off from Planning to Forge, the
`HandoffBundle.visual_direction_id` points at that artifact, and the
frontend_architect reads `stitch_project_id` / `stitch_project_url`
from the loaded VisualDirection.

---

## Re-invocation flow

When a human edits the Stitch project after a migration has run and
the Manager is re-invoked:

1. The orchestrator compares the Stitch project's `updated_at`
   (fetched via `stitch.getProject`) against the VisualDirection
   artifact's mtime on disk.
2. If the Stitch project is newer than the artifact, log a
   `stitch_changed` trace event and disable the planning-room
   skip-check for `designer` for this run (forcing `ui_designer` to
   re-run and refresh the VisualDirection).
3. The frontend_architect then picks up the refreshed
   `visual_direction_id` and re-pulls the updated screens.

### Phase D implementation status

Phase D wires the **contract** for this flow (the fields, the
charter, the prompt instruction). The actual timestamp poll is
stubbed via `TODO` in the orchestrator — it will be implemented in
Phase E once the Stitch MCP supports `getProject` reliably.

The wiring that DOES exist today:

- `VisualDirection.stitch_project_id` / `stitch_project_url` capture
  the Stitch handle at design time.
- `HandoffBundle.visual_direction_id` is the cross-room pointer.
- `frontend_architect`'s prompt injects a "Design Reference (Stitch)"
  section when `stitch_project_id` is present, telling the LLM to use
  `stitch.listScreens` / `stitch.getScreen` to fetch the screens.
- The designer_agent prints `[TRACE] stitch_project_created {...}`
  after the VisualDirection is saved.

---

## Editing conventions

When editing a Stitch project manually (between migrations):

- **Name screens consistently.** Use the route as the screen name:
  `/`, `/services`, `/about`, `/blog`, `/blog/[slug]`, `/contact`.
  Don't rename screens the architect already added — the
  `frontend_architect` looks them up by name.
- **Don't delete architect-added screens.** If a screen is wrong,
  annotate it in the Stitch project's description field rather than
  removing it; the design rationale is in the description.
- **Apply the BrandSpec.** Color, font, and spacing tokens must come
  from `BrandSpec` (the marketing_specialist's artifact), not
  invented in Stitch. The frontend_architect will warn on drift.
- **Keep `stitch_status` honest.** If you change screens significantly,
  re-run the migration so the VisualDirection stays current.

---

## Failure modes

- **Stitch MCP unreachable.** The `ui_designer` falls back gracefully:
  `stitch_status="unavailable"`, IDs are null, the VisualDirection is
  emitted with `primary_change="No visual evolution — BrandSpec
  fidelity only"`. The pipeline never blocks on Stitch.
- **Project exists but screens missing.** The `frontend_architect`
  will emit a `medium`-severity gap and proceed with the BrandSpec
  alone (no Stitch layouts to reference).
- **Timestamp drift.** The orchestrator's `TODO` poll catches this
  case in Phase E; today, humans must manually re-run `ui_designer`
  (delete `memory/visual_specs/<slug>/<timestamp>.json` or bump the
  timestamp) to force a refresh.

---

## Cross-references

- `registry/personas/ui_designer.md` — section 5 (Stitch Project Lifecycle).
- `models/site_schemas.py:VisualDirection` — `stitch_project_id`,
  `stitch_project_url`, `stitch_status`, `schema_version="1.2"`.
- `skills/agentic/frontend_architect.py` — `stitch_project_id` /
  `stitch_project_url` kwargs and the "Design Reference (Stitch)"
  prompt section.
- `conductor/orchestrator.py:_invoke_persona` — frontend branch that
  forwards `stitch_project_id` / `stitch_project_url` into
  `design_frontend(...)`.