# Phase 1.2: Real Scraping, Security & Deploy Wiring

**Date:** 2026-05-05
**Goal:** Wire real MCP clients into orchestrator phases so the system can do end-to-end migrations

---

## Problem Statement

Current orchestrator has stubbed phases:
- `_run_scraping` → returns `{"pages": {}, "errors": ["Scraper stub - Phase 0"]}`
- `_run_security_gate` → returns `{"passed": True}` (hardcoded)
- `_run_deploy` → returns fake URL `"https://elyra-migration.fly.dev"`

These stubs prevent real migrations. The system can detect platforms and generate code, but can't scrape content or deploy.

---

## Architecture

```
Conductor.run()
├── _run_onboarding()     ✅ Real (platform detection via Router)
├── _run_routing()        ✅ Real (persona sequence + confidence)
├── _run_scraping()       🔴 Stub → needs Playwright MCP
├── _run_codegen()        ✅ Real (OpenCode + mutation seed)
├── _run_security_gate()  🔴 Stub → needs npm audit + Lighthouse
└── _run_deploy()         🔴 Stub → needs Fly.io MCP
```

---

## Phase 1: Real Scraping via Playwright MCP

### Current Code (`orchestrator.py:_run_scraping`)
```python
def _run_scraping(self, state, trace):
    trace.add_persona_invoked("scraper_specialist")
    state["scraped_content"] = {
        "pages": {},
        "global": {},
        "platform": state["task_context"].get("platform", "generic"),
        "errors": ["Scraper stub - Phase 0"]
    }
    trace.add("Scraping", "Complete (stub)")
    return transition_to_phase(state, WorkflowPhase.CODEGEN)
```

### Target: Wire Playwright MCP

```python
async def _run_scraping(self, state, trace) -> ConductorState:
    """
    Scrape site content using Playwright MCP.
    Falls back to stub if MCP unavailable (self-healing).
    """
    trace.add_persona_invoked("scraper_specialist")

    url = state["task_context"].get("url")
    platform = state["task_context"].get("platform", "generic")

    if not url:
        state["scraped_content"] = {"pages": {}, "global": {}, "errors": ["No URL provided"]}
        state = transition_to_phase(state, WorkflowPhase.CODEGEN)
        return state

    # Use Playwright MCP if healthy
    if self.playwright_mcp.is_healthy():
        try:
            pages = await self.playwright_mcp.scrape_pages(url, platform)
            state["scraped_content"] = {
                "pages": pages,
                "global": extract_global_content(pages),
                "platform": platform,
                "errors": []
            }
            trace.add("Scraping", f"Complete via Playwright MCP - {len(pages)} pages")
        except Exception as e:
            self.playwright_mcp.mark_degraded()
            state["scraped_content"] = self._scraping_fallback(url, platform)
            trace.add_warning("Scraping", f"MCP failed, using fallback: {e}")
    else:
        state["scraped_content"] = self._scraping_fallback(url, platform)
        trace.add("Scraping", "Complete (fallback mode)")

    return transition_to_phase(state, WorkflowPhase.CODEGEN)

def _scraping_fallback(self, url, platform):
    """Stub fallback when Playwright MCP is unavailable."""
    return {
        "pages": {},
        "global": {},
        "platform": platform,
        "errors": ["Playwright MCP unavailable - using empty scrape"]
    }
```

### Playwright MCP Interface Needed

```python
class PlaywrightMCP:
    def is_healthy(self) -> bool:
        """Check if MCP server is responsive."""

    async def scrape_pages(self, url: str, platform: str) -> dict[str, PageContent]:
        """Scrape all pages starting from URL."""
        # Returns: {"home": {"url": "...", "title": "...", "content": "...", "links": [...]}, ...}

    def mark_degraded(self):
        """Log degradation event to memory."""
```

### Data Contract: `scraped_content`

```python
{
    "pages": {
        "home": {
            "url": "https://example.wixsite.com/",
            "title": "Home | My Site",
            "content": "<html>...</html>",  # or structured text
            "links": ["/about", "/portfolio", ...],
            "images": [{"src": "...", "alt": "..."}],
        },
        "about": {...},
        ...
    },
    "global": {
        "site_name": "My Site",
        "theme": {"primary_color": "#...", "font": "..."},
        "navigation": [{"label": "Home", "url": "/"}, ...],
    },
    "platform": "wix",
    "errors": []  # Empty if successful
}
```

---

## Phase 2: Real Security Gate

### Current Code (`orchestrator.py:_run_security_gate`)
```python
def _run_security_gate(self, state, trace):
    trace.add_persona_invoked("security_auditor")
    state["security_gate_passed"] = True
    state["security_gate_results"] = {
        "npm_audit": {"passed": True, "critical": 0},
        "lighthouse": {"passed": True, "score": 85}
    }
    trace.add_security_gate(True, "(npm audit: 0 critical, lighthouse: 85+)")
    return transition_to_phase(state, WorkflowPhase.DEPLOY)
```

### Target: Real Security Checks

```python
async def _run_security_gate(self, state, trace) -> ConductorState:
    """
    Run security checks:
    1. npm audit (vulnerabilities)
    2. Lighthouse (performance/accessibility/SEO)
    3. Optional: Playwright accessibility scan
    """
    trace.add_persona_invoked("security_auditor")

    project_path = state.get("codegen_output", {}).get("project_path", ".")

    results = {
        "npm_audit": None,
        "lighthouse": None,
    }

    # Run npm audit
    try:
        audit_result = await self._run_npm_audit(project_path)
        results["npm_audit"] = audit_result
    except Exception as e:
        results["npm_audit"] = {"passed": False, "error": str(e)}

    # Run Lighthouse if we have a deployed preview URL
    if state.get("preview_url"):
        try:
            lighthouse_result = await self._run_lighthouse(state["preview_url"])
            results["lighthouse"] = lighthouse_result
        except Exception as e:
            results["lighthouse"] = {"passed": False, "error": str(e)}

    # Determine pass/fail
    npm_passed = results["npm_audit"].get("critical", 1) == 0
    lighthouse_passed = results["lighthouse"].get("score", 0) >= 70 if results["lighthouse"] else True

    state["security_gate_passed"] = npm_passed and lighthouse_passed
    state["security_gate_results"] = results

    gate_status = f"npm_audit: {results['npm_audit'].get('critical', '?')} critical, lighthouse: {results['lighthouse'].get('score', 'N/A')}"
    trace.add_security_gate(state["security_gate_passed"], f"({gate_status})")

    if not state["security_gate_passed"]:
        state = transition_to_phase(state, WorkflowPhase.ABORT)

    return transition_to_phase(state, WorkflowPhase.DEPLOY)

async def _run_npm_audit(self, project_path: str) -> dict:
    """Run npm audit in project directory."""
    # Implementation: spawn npm audit process, parse JSON output
    # Returns: {"passed": bool, "critical": int, "high": int, "moderate": int}

async def _run_lighthouse(self, url: str) -> dict:
    """Run Lighthouse via Playwright MCP or CLI."""
    # Returns: {"passed": bool, "score": int, "performance": int, "accessibility": int}
```

### Security Gate Thresholds

```python
SECURITY_GATE_THRESHOLDS = {
    "npm_audit": {
        "critical": 0,      # Must have 0 critical vulnerabilities
        "high": 0,          # Target 0 high vulnerabilities
    },
    "lighthouse": {
        "score": 70,        # Minimum overall score
        "performance": 50,   # Minimum performance score
        "accessibility": 70, # Minimum accessibility score
    }
}
```

---

## Phase 3: Real Deploy via Fly.io MCP

### Current Code (`orchestrator.py:_run_deploy`)
```python
def _run_deploy(self, state, trace):
    trace.add_persona_invoked("deploy_specialist")
    state["deploy_url"] = "https://elyra-migration.fly.dev"
    trace.add_deployed(state["deploy_url"])
    return transition_to_phase(state, WorkflowPhase.APPROVAL)
```

### Target: Real Fly.io Deployment

```python
async def _run_deploy(self, state, trace) -> ConductorState:
    """
    Deploy built application to Fly.io.
    Uses Fly.io MCP if healthy, falls back to Vercel/Netlify stub.
    """
    trace.add_persona_invoked("deploy_specialist")

    project_path = state.get("codegen_output", {}).get("project_path", ".")
    app_name = state["task_context"].get("app_name", f"elyra-{state['session_id'][:8]}")

    if self.fly_mcp.is_healthy():
        try:
            # 1. Create Fly app
            app = await self.fly_mcp.create_app(
                name=app_name,
                org=state["task_context"].get("org_slug"),
                region=state["task_context"].get("region", "iad")
            )

            # 2. Deploy from Dockerfile
            deployment = await self.fly_mcp.deploy_app(
                app_name=app.name,
                dockerfile_path=f"{project_path}/Dockerfile"
            )

            state["deploy_url"] = deployment.url
            state["fly_app_id"] = app.id
            state["deployment_id"] = deployment.id

            trace.add_deployed(deployment.url)

        except Exception as e:
            self.fly_mcp.mark_degraded()
            state["deploy_url"] = self._deploy_fallback(project_path, app_name)
            trace.add_warning("Deploy", f"Fly.io failed, using fallback: {e}")
    else:
        state["deploy_url"] = self._deploy_fallback(project_path, app_name)
        trace.add("Deploy", "Complete (fallback mode)")

    return transition_to_phase(state, WorkflowPhase.APPROVAL)

def _deploy_fallback(self, project_path: str, app_name: str) -> str:
    """
    Fallback deployment when Fly.io MCP unavailable.
    Could deploy to Vercel, Netlify, or return instructions.
    """
    return f"https://{app_name}.vercel.app"
```

### Deploy Flow

```
1. Build completed (OpenCode output)
         ↓
2. Create Fly.io app (if not exists)
         ↓
3. Upload Dockerfile + app files
         ↓
4. Deploy via Fly.io MCP `deploy_app()`
         ↓
5. Get public URL
         ↓
6. (Optional) Run Lighthouse against preview
         ↓
7. Proceed to approval phase
```

---

## Data Flow Between Phases

```
task_context
    ├── url: "https://merimeesolutions.wixstudio.com/my-site-2"
    ├── platform: "wix"
    ├── task_type: "portfolio"
    └── ...
         ↓
_run_routing()
    ├── routing_sequence: ["scraper_specialist", "codegen_crew_lead", ...]
    ├── stack_chosen: "nextjs+tailwind+contentlayer"
    └── routing_confidence: 0.95
         ↓
_run_scraping()
    └── scraped_content
         ├── pages: {home: {content: "...", title: "...", links: [...]}, ...}
         ├── global: {site_name: "...", theme: {...}, navigation: [...]}
         └── platform: "wix"
         ↓
_run_codegen()
    ├── codegen_prompt includes: scraped_content, mutation_seed
    └── codegen_output
         ├── project_path: "./output/elyra-abc123"
         ├── files_created: ["package.json", "app/page.tsx", ...]
         └── build_status: "success"
         ↓
_run_security_gate()
    ├── npm_audit: {critical: 0, high: 2}
    └── lighthouse: {score: 85, performance: 88}
         ↓
_run_deploy()
    └── deploy_url: "https://elyra-abc123.fly.dev"
         ↓
MigrationResult
    ├── success: true
    ├── deploy_url: "https://elyra-abc123.fly.dev"
    ├── fidelity_score: null  # Set by human review
    └── trace: {...}
```

---

## Implementation Order

### Step 1: Add Playwright MCP to Conductor `__init__`

```python
def __init__(self, db_path: str = "elyra_memory.db"):
    self.router = Router()
    self.memory_client = MemoryClient(db_path)
    self.session_id = str(uuid.uuid4())

    # Wire MCP clients (self-healing)
    from tools.mcp.playwright import PlaywrightMCP
    self.playwright_mcp = PlaywrightMCP()

    from tools.mcp.fly import FlyMCP
    self.fly_mcp = FlyMCP()
```

### Step 2: Make `_run_scraping` async

Current orchestrator uses synchronous phases. Need to:
1. Make `_run_scraping` async
2. Make `run()` handle async properly

### Step 3: Implement Playwright MCP `scrape_pages()`

The MCP client already exists but needs a real `scrape_pages()` method that:
1. Launches browser via Playwright MCP
2. Navigates to URL
3. Extracts page content
4. Follows navigation links
5. Returns structured `pages` dict

### Step 4: Wire Fly.io MCP `create_app()` + `deploy_app()`

### Step 5: Add npm audit + lighthouse CLI calls

Can use subprocess for npm audit. Lighthouse can use Playwright MCP or CLI.

---

## Testing Approach

### Unit Tests
- `test_scraping_fallback()` — When MCP unhealthy, returns stub
- `test_security_gate_thresholds()` — Correct pass/fail at boundaries
- `test_deploy_fallback()` — Fallback URL generated correctly

### Integration Tests (require real MCP servers)
- `test_playwright_scrape_wix()` — Real scrape of wixstudio.com
- `test_fly_deploy()` — Real Fly.io deployment (requires `FLY_API_TOKEN`)

### Smoke Test
```bash
python -c "
from conductor.orchestrator import Conductor
c = Conductor()
result = c.run({
    'url': 'https://merimeesolutions.wixstudio.com/my-site-2',
    'platform': 'wix',
    'task_type': 'portfolio'
})
print('Success:', result.success)
print('Phase reached:', result.phase_reached)
print('Deploy URL:', result.deploy_url)
"
```

---

## Files to Modify

| File | Change |
|------|--------|
| `conductor/orchestrator.py` | Wire MCP clients, make phases async, real implementations |
| `tools/mcp/playwright.py` | Add `scrape_pages()` method with real Playwright MCP call |
| `tools/mcp/fly.py` | Already has `create_app()` + `deploy_app()` — verify they work |
| `conductor/state_machine.py` | May need `WorkflowPhase.SCRAPING` async handling |
| `conductor/trace.py` | Ensure `add_deployed()` signature matches |

---

## Estimated Effort

| Component | Complexity | Time |
|-----------|------------|------|
| Playwright MCP `scrape_pages()` | Medium | 2-3 hours |
| Orchestrator async refactor | Low | 1 hour |
| Security gate (npm audit + lighthouse) | Low | 1-2 hours |
| Fly.io MCP `deploy_app()` | Medium | 1-2 hours |
| Integration tests | Medium | 2 hours |

**Total: ~7-10 hours**

---

## Open Questions

1. **Scraping depth**: How many pages should we scrape? All pages or just key ones (home, about, contact)?
2. **Lighthouse timing**: Should Lighthouse run before deploy (preview URL) or after (deployed URL)?
3. **Deployment targets**: Fly.io primary, but should we have Vercel/Netlify as fallback?
4. **Authentication**: How do we handle `FLY_API_TOKEN` — require env var or prompt user?