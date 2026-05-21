# TASKS_PHASE2_ARCHITECT.md

## Overview
Phase 2 is the **Technical Architect Specialist** — given a `SiteUnderstanding` (scraped site data), produce a technical architecture recommendation for the rebuild. The architect analyzes the scraped data and outputs a structured `SiteArchitecture` object that guides the builder agent.

## Context: How Phase 2 Connects

```
URL input
    │
    ▼
┌─────────────────────────────────────────┐
│  Phase 1: Scraper Specialist           │
│  Kilo CLI + Playwright/Fetch MCP      │
│  Output: SiteUnderstanding JSON        │
│  Saved to: memory/site_understandings │
└─────────────────────────────────────────┘
    │
    │ SiteUnderstanding
    ▼
┌─────────────────────────────────────────┐
│  Phase 2: Architect Specialist         │  ◄── we are here
│  Analyzes scraped data                 │
│  Output: SiteArchitecture JSON          │
└─────────────────────────────────────────┘
    │
    │ SiteArchitecture + SiteUnderstanding
    ▼
┌─────────────────────────────────────────┐
│  Phase 3: Marketing/Content Specialist │
│  Analyzes content quality              │
│  Output: ContentRecommendation JSON    │
└─────────────────────────────────────────┘
    │
    │ SiteArchitecture + ContentRecommendation + SiteUnderstanding
    ▼
┌─────────────────────────────────────────┐
│  Phase 4: Builder Specialist          │
│  Builds the actual site from specs     │
└─────────────────────────────────────────┘
```

## Phase 2 Goals

Given a `SiteUnderstanding` (scraped site data), produce:
1. **Technology stack recommendation** (Next.js vs Nuxt, Tailwind vs CSS Modules, etc.)
2. **Deployment architecture** (Fly.io app setup, GitHub repo structure, environment config)
3. **Component inventory** (which components to build, which are reusable)
4. **Page structure map** (how pages relate, template reuse opportunities)
5. **Data strategy** (headless CMS vs static, image CDN strategy, JSON-LD migration)
6. **SEO preservation plan** (url mapping, redirect strategy, canonical handling)
7. **Migration risk assessment** (what's easy/hard/risky to migrate)

## Output: SiteArchitecture Schema

```python
class ComponentSpec(BaseModel):
    component_id: str                          # e.g., "hero-home", "newsletter-form"
    component_type: ComponentType              # from SiteUnderstanding
    file_path: str                            # e.g., "components/hero/HomeHero.tsx"
    props_schema: dict                         # typed props interface
    is_reusable: bool                         # can this be used across pages?
    page_scope: list[str]                     # which pages use this
    complexity: Literal["simple", "medium", "complex"]
    notes: str

class PageSpec(BaseModel):
    url: str                                  # source URL
    route: str                                # target route, e.g., "/about" or "/blog/[slug]"
    component_ids: list[str]                   # ordered list of component_ids
    data_source: str                          # "static", "cms", "api"
    cms_content_type: str | None               # if cms, which content type
    template_id: str | None                  # source template_id this maps to
    priority: Literal["critical", "standard", "optional"]
    notes: str

class RedirectRule(BaseModel):
    from_url: str                             # original URL
    to_url: str                               # target URL
    type: Literal["permanent", "temporary"]   # 301 or 302

class SeoMigrationPlan(BaseModel):
    url_mapping: list[RedirectRule]
    canonical_strategy: str                  # how to handle canonicals
    og_image_strategy: str                    # what to do with og:image URLs
    json_ld_action: str                      # preserve | migrate-to-nextjs | drop

class ImageMigrationStrategy(BaseModel):
    source_pattern: str                      # e.g., "static.wixstatic.com/*"
    target_strategy: str                      # e.g., "upload to Fly Images, replace URLs"
    cdn_domain: str | None                  # target CDN domain if applicable

class DeploymentSpec(BaseModel):
    fly_app_name: str
    github_repo: str
    base_branch: str                         # "main" or "production"
    preview_branch_prefix: str               # e.g., "preview/"
    env_vars: list[dict]                     # [{"name": "FOO", "source": "wix env var X"}]
    secret_keys: list[str]                   # non-sensitive keys to copy from source
    fly_regions: list[str]                   # preferred Fly regions

class ArchitectureDecision(BaseModel):
    category: str                            # "routing", "styling", "cms", "forms", "media"
    decision: str                            # what we chose
    rationale: str                           # why based on scraped data
    alternatives_considered: list[str]      # what else was considered
    risk: str                                 # "low", "medium", "high"

class SiteArchitecture(BaseModel):
    source_url: str                          # the URL that was scraped
    target_stack: dict                       # {"framework": "next.js", "styling": "tailwind", ...}
    deployment: DeploymentSpec
    pages: list[PageSpec]
    components: list[ComponentSpec]
    image_strategy: ImageMigrationStrategy
    seo_migration: SeoMigrationPlan
    architecture_decisions: list[ArchitectureDecision]
    estimated_build_hours: float             # rough estimate
    confidence: float                        # how confident we are in this architecture
    warnings: list[str]
    reasoning_trace: list[str]
```

## Phase 2 Tasks

### Task 2.1: Create architect specialist persona
**File:** `registry/personas/architect_specialist.md`
- Role: Senior software architect analyzing scraped site data
- Reads SiteUnderstanding JSON from `memory/site_understandings/`
- Outputs SiteArchitecture JSON
- Considers all the dimensions in the schema above

### Task 2.2: Create architect agent
**File:** `skills/agentic/architect_agent.py`
- Thin glue: loads SiteUnderstanding, builds prompt, calls Kilo CLI, parses output, validates Pydantic
- Pattern matches scraper_agent.py structure
- Reads from `memory/site_understandings/<timestamp>.json`
- Saves to `memory/site_architectures/<timestamp>.json`

### Task 2.3: Create architect CLI entrypoint
**File:** `architect.py`
- `python architect.py <timestamp>` — runs architect on a saved site understanding
- `python architect.py --latest` — runs on most recent
- `python architect.py --list` — lists available site understandings

### Task 2.4: Wire into Kilo (optional: --agent flag)
- Add `--agent architect_specialist` option to kilo run calls for targeted persona use

### Task 2.5: Test end-to-end
- Run on saintjosephtheworkeracademy.org site understanding
- Verify SiteArchitecture output is complete and valid

## Open Questions / Blockers

1. **Should the architect agent run automatically after scraper?** Or be triggered manually? (Decision: manual trigger for now — simpler)
2. **Headless CMS choice** — Contentful, Sanity, or nothing (static export)? (Needs marketing/content phase input)
3. **Image CDN** — Should images be uploaded to Fly Images, Cloudflare R2, or just referenced from original CDN? (Cost/performance tradeoff)
4. **Forms** — Keep embedded forms (Donorbox, WixForms) or rebuild as native? (Preservation vs. modernization tradeoff)

## Files to Create

```
registry/personas/architect_specialist.md    # persona charter
skills/agentic/architect_agent.py           # thin Kilo CLI caller
architect.py                                # CLI entrypoint
memory/site_architectures/                  # output directory (add to gitignore)
```

## Files That Already Exist and Can Be Reused

```
skills/agentic/scraper_agent.py            # exact pattern to follow
skills/agentic/site_interpreter.py         # save-to-memory pattern
models/site_schemas.py                      # add SiteArchitecture, ComponentSpec, PageSpec, etc.
```

## Dependencies
- Same Kilo CLI subprocess approach as scraper_agent.py
- Same `--format json --auto` flags
- Same NDJSON parsing logic
- Pydantic models for SiteArchitecture schema (add to models/site_schemas.py)