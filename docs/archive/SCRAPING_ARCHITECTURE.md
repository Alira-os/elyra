# Scraping Architecture - Detailed Process Graph

**Date:** 2026-05-05
**Purpose:** Document how scraping works end-to-end, from Conductor orchestration through the scraper_specialist persona to MCP tools

---

## High-Level Process Flow

```mermaid
graph TD
    subgraph User_Input
        A["task_context<br/>{url, platform, task_type}"]
    end

    subgraph Conductor["Conductor.run()"]
        B["_run_onboarding()<br/>Platform Detection"]
        C["_run_routing()<br/>Router.route()"]
        D["_run_scraping()<br/>scraper_specialist"]
        E["_run_codegen()<br/>codegen_crew_lead"]
        F["_run_security_gate()<br/>security_auditor"]
        G["_run_deploy()<br/>deploy_specialist"]
    end

    subgraph Routing["Router + Routing Heuristics"]
        H["ROUTING_RULES lookup<br/>exact → partial → fallback"]
        I["FAILURE_HANDLING<br/>retry/fallback/skip/abort"]
    end

    subgraph Scraping["Scraper Specialist Persona"]
        J["registry/personas/<br/>scraper_specialist.md"]
        K["Playwright MCP<br/>tools/mcp/playwright.py"]
        L["Fetch MCP<br/>tools/mcp/fetch.py"]
        M["Skills:<br/>platform_detector, seo_optimizer"]
    end

    A --> B
    B --> C
    C --> H
    H --> D
    D --> J
    J --> K
    J --> L
    J --> M
    D --> E
    E --> F
    F --> G

    style D fill:#f96
    style K fill:#bbf
    style L fill:#bbf
```

---

## Conductor Orchestration Detail

### Phase Execution Order

```mermaid
sequenceDiagram
    participant User
    participant Conductor
    participant Router
    participant Scraper
    participant Codegen
    participant Security
    participant Deploy

    User->>Conductor: run(task_context)
    Conductor->>Conductor: _run_onboarding()
    Note over Conductor: Detect platform if not set
    Conductor->>Router: route(task_context)
    Router-->>Conductor: {routing_sequence, confidence, stack_chosen}

    alt "scraper_specialist" in routing_sequence
        Conductor->>Scraper: _run_scraping(state, trace)
        Scraper->>Scraper: scrape_site(url)
        Scraper->>Playwright: browser_navigate + snapshot
        Scraper->>Fetch: fetch_content (backup)
        Scraper-->>Conductor: ScrapedSite object
    else
        Conductor->>Conductor: Skip scraping, go to codegen
    end

    Conductor->>Codegen: _run_codegen()
    Note over Codegen: Uses scraped_content + mutation_seed
    Codegen-->>Conductor: codegen_output

    Conductor->>Security: _run_security_gate()
    Note over Security: npm audit + lighthouse
    Security-->>Conductor: security_gate_passed

    Conductor->>Deploy: _run_deploy()
    Deploy-->>Conductor: deploy_url

    Conductor-->>User: MigrationResult
```

---

## Scraping Process Detail

### How `scrape_site()` Works

```mermaid
graph TD
    A["scrape_site(url) called"]
    B["Health probe:<br/>npx @playwright/mcp@latest --version"]
    C{"MCP healthy?"}
    D["Call Playwright MCP via stdio_client"]
    E["browser_navigate(url)"]
    F["browser_snapshot()"]
    G["Extract content[0].text"]
    H["Parse snapshot into pages"]
    I["Extract global site data"]
    J["Detect platform from content"]
    K{"Parse success?"}
    L["Mark MCP degraded"]
    M["Return fallback ScrapedSite"]
    N["Return ScrapedSite<br/>platform, pages, global_data"]

    A --> B --> C
    C -->|Yes| D
    C -->|No| L
    D --> E --> F --> G
    G --> H --> I --> J --> K
    K -->|Yes| N
    K -->|No| L
    L --> M

    style D fill:#9f9
    style L fill:#f99
```

### Two-Phase Scraping: Playwright + Fetch

```mermaid
graph LR
    subgraph Phase1_Playwright["Phase 1: Playwright (JS Rendering)"]
        A1["browser_navigate(url)"]
        A2["Wait for JS rendering"]
        A3["browser_snapshot()"]
        A4["Accessibility tree YAML"]
    end

    subgraph Phase2_Fetch["Phase 2: Fetch (Clean Content)"]
        B1["fetch_content(url)"]
        B2["urllib Request"]
        B3["HTMLParser removes scripts/styles"]
        B4["Clean text extraction"]
    end

    subgraph Phase3_Synthesis["Phase 3: Synthesis"]
        C1["Merge Playwright structure"]
        C2["Merge Fetch text content"]
        C3["Generate ScrapedSite"]
    end

    A1 --> A2 --> A3 --> A4
    A4 --> C1
    B1 --> B2 --> B3 --> B4
    B4 --> C2
    C1 --> C3
    C2 --> C3

    style Phase1_Playwright fill:#d4efdf
    style Phase2_Fetch fill:#d4efdf
    style Phase3_Synthesis fill:#f9e79f
```

---

## Scraper Specialist Persona

### Persona Definition (`registry/personas/scraper_specialist.md`)

```mermaid
graph TD
    subgraph Persona_Definition
        A["scraper_specialist.md"]
        B1["Responsibilities"]
        B2["Content Format"]
        B3["Tools Used"]
        B4["Skills Called"]
    end

    subgraph Responsibilities
        C1["Site Structure Discovery"]
        C2["Content Scraping"]
        C3["SEO Metadata Extraction"]
    end

    subgraph Content_Format
        D1["pages: {url: {title, headings, content_blocks, images, links}}"]
        D2["global: {site_name, logo_url, social_links}"]
        D3["discovered_pages: [{url, title, priority}]"]
    end

    subgraph Tools
        E1["Playwright MCP"]
        E2["Fetch MCP"]
    end

    subgraph Skills
        F1["platform_detector"]
        F2["seo_optimizer"]
    end

    A --> B1 --> C1 & C2 & C3
    A --> B2 --> D1 & D2 & D3
    A --> B3 --> E1 & E2
    A --> B4 --> F1 & F2
```

### Scraping Phases (A, B, C)

```mermaid
flowchart LR
    subgraph Phase_A["Phase A: Structure Extraction"]
        A1["Playwright browser_navigate"]
        A2["Wait for DOM ready"]
        A3["browser_snapshot"]
        A4["Parse accessibility tree"]
        A5["Extract nav, links, headings"]
    end

    subgraph Phase_B["Phase B: Content Extraction"]
        B1["Fetch MCP fetch_content"]
        B2["Parse HTML structure"]
        B3["Remove scripts/styles"]
        B4["Extract clean text"]
    end

    subgraph Phase_C["Phase C: SEO Metadata"]
        C1["Extract OpenGraph tags"]
        C2["Extract Twitter cards"]
        C3["Parse JSON-LD schema"]
        C4["Generate SEO guidance"]
    end

    A1 --> A2 --> A3 --> A4 --> A5
    B1 --> B2 --> B3 --> B4
    A5 --> C1
    C1 --> C2 --> C3 --> C4

    style Phase_A fill:#e8f4f8
    style Phase_B fill:#e8f8e8
    style Phase_C fill:#fef9e7
```

---

## Data Flow: task_context → ScrapedSite

```mermaid
flowchart TD
    subgraph Input
        TC["task_context<br/>{url: str, platform: str, task_type: str}"]
    end

    subgraph Playwright_MCP["Playwright MCP"]
        NAV["browser_navigate(url)"]
        SNAP["browser_snapshot()"]
        YAML["YAML accessibility tree"]
        PARSE["_parse_snapshot_to_pages()"]
        PAGE["page: {url, title, content, links, images}"]
    end

    subgraph Fetch_MCP["Fetch MCP (backup)"]
        FETCH["fetch_content(url)"]
        HTML["Raw HTML"]
        TEXT["Clean text via HTMLParser"]
    end

    subgraph Platform_Detection["Platform Detection"]
        CONTENT["snapshot text content"]
        PLATFORM["_detect_platform_from_content()"]
        RESULT["platform: wix (0.9)"]
    end

    subgraph Output
        SS["ScrapedSite<br/>url, platform, platform_confidence<br/>pages: {}, global_data: {}<br/>errors: [], using_fallback: bool"]
    end

    TC --> NAV
    NAV --> SNAP
    SNAP --> YAML
    YAML --> PARSE
    PARSE --> PAGE
    PAGE --> SS
    TC --> FETCH
    FETCH --> HTML --> TEXT --> SS
    YAML --> CONTENT
    CONTENT --> PLATFORM --> RESULT --> SS

    style SS fill:#9b59b6,color:#fff
```

---

## Routing Integration

### How Router Decides to Invoke Scraper

```mermaid
flowchart TD
    A["Router.route(task_context)"]
    B["Extract platform + task_type"]
    C{"Exact match in<br/>ROUTING_RULES?"}
    D["platform='wix', task_type='portfolio'"]
    E{"Partial match?<br/>(platform, 'generic')?"}
    F["fallback:<br/>(generic, generic)"]
    G["Set confidence = 0.5"]
    H["requires_override = True"]
    I["Return routing_sequence<br/>with scraper_specialist"]

    A --> B --> C
    C -->|Yes| D --> I
    C -->|No| E
    E -->|Yes| G --> I
    E -->|No| F --> G --> H --> I

    style D fill:#27ae60,color:#fff
    style F fill:#e74c3c,color:#fff
```

### Routing Rules Table

| Platform | Task Type | Routing Sequence | Confidence |
|----------|-----------|------------------|-------------|
| wix | portfolio | onboarding → scraper → stack_intel → codegen → ui_polish → security → deploy | 1.0 |
| wix | blog | onboarding → scraper → stack_intel → codegen → seo → deploy | 0.95 |
| squarespace | portfolio | onboarding → scraper → stack_intel → codegen → ui_polish → security → deploy | 1.0 |
| wordpress | business | onboarding → scraper → stack_intel → codegen → security → deploy | 0.9 |
| generic | generic | LLM override required | 0.5 |

---

## Failure Handling

### FAILURE_HANDLING Configuration

```mermaid
flowchart TD
    A["scraper_specialist fails"]
    B["Check FAILURE_HANDLING"]
    C{"retry count < 2?"}
    D["Retry with same URL"]
    E["fallback to minimal_scrape"]
    F["Log error to memory"]
    G["Skip to next phase?<br/>scraper_specialist"]

    A --> B --> C
    C -->|Yes| D
    C -->|No| E
    E --> G
    D --> G
    G --> F
```

### Failure Actions

| Persona | Retry | Fallback | Action on Abort |
|---------|-------|----------|-----------------|
| scraper_specialist | 2 | minimal_scrape | Skip to codegen with empty pages |
| codegen_crew_lead | 1 | simplified_codegen | Abort migration |
| security_auditor | 0 | - | Always abort |
| deploy_specialist | 2 | staging_only | Deploy with warning |

---

## Current Implementation Status

### What Works (Phase 1)

| Component | Status | Notes |
|-----------|--------|-------|
| Conductor orchestration | ✅ | Linear phase execution |
| Router + routing rules | ✅ | Table-based lookup |
| Playwright MCP scraping | ✅ | browser_navigate + snapshot |
| Self-healing fallback | ✅ | Health probe + stub return |
| Platform detection from content | ✅ | wix (0.9) for wixstudio.com |

### What Needs Wiring (Current Session)

| Component | Status | Notes |
|-----------|--------|-------|
| `_run_scraping` calls Playwright | ✅ | Now uses real scrape_site() |
| Fetch MCP integrated | ❌ | Not used in scrape_site yet |
| Conductor wired to Playwright | ❌ | Orchestrator still uses stub |
| Conductor wired to Fetch | ❌ | Not connected |

### Missing Wiring

```
conductor/orchestrator.py _run_scraping():
    CURRENT: state["scraped_content"] = {pages: {}, errors: ["stub"]}
    NEEDED:  state["scraped_content"] = await scrape_site(url)
```

---

## Tools Available to Scraper Specialist

### Playwright MCP (`tools/mcp/playwright.py`)

```python
async def scrape_site(url: str, use_mcp: bool = True) -> ScrapedSite:
    """Main scraping function"""

async def get_page_content(url: str) -> PageContent:
    """Get content from single page"""

async def render_js(url: str) -> str:
    """Render JS-heavy page, fallback to Fetch"""
```

### Fetch MCP (`tools/mcp/fetch.py`)

```python
def fetch_content(url: str, timeout: int = 30) -> FetchResult:
    """HTTP fetch with HTML parsing"""

@dataclass
class FetchResult:
    url: str
    status_code: int
    html: str
    text: str
    metadata: dict
    error: Optional[str]
```

---

## Skills Available to Scraper Specialist

### platform_detector (`skills/executable/platform_detector.py`)

```python
def detect_platform(url: str, html=None, fetch_on_low_confidence=True) -> dict:
    """Multi-stage: URL pattern → HTML markers → LLM fallback"""
    # Returns: {platform, confidence, indicators, error}
```

### seo_optimizer (`skills/executable/seo_optimizer.py`)

```python
def get_seo_guidance(scraped_site: ScrapedSite) -> dict:
    """Generate SEO recommendations from scraped content"""
    # Returns: {title_template, meta_description_template, recommendations, ...}
```

---

## Next Steps: Wire Fetch MCP into Scraping

### Current Flow (One-Phase)

```
scrape_site(url)
    → Playwright MCP only
    → _parse_snapshot_to_pages() extracts structure
    → Returns ScrapedSite
```

### Target Flow (Two-Phase)

```
scrape_site(url)
    → Playwright MCP (structure + JS content)
    → Fetch MCP (clean text backup)
    → Combine results
    → Returns richer ScrapedSite
```

### Implementation Changes

1. **In `scrape_site()`**: After Playwright snapshot, call `fetch_content(url)` as backup
2. **In `_run_scraping()`**: Call both Playwright + Fetch, merge results
3. **Add `_merge_scraping_results()`**: Combine Playwright structure with Fetch text

---

## Questions/Open Items

1. **Scraping depth**: How many pages should we follow? Home/About/Portfolio only or all discovered pages?
2. **Fetch fallback timing**: Should we try Fetch first if Playwright is degraded, or always try Playwright first?
3. **Conductor integration**: Should `_run_scraping` directly call `scrape_site()` or go through the persona system?
4. **Persona vs direct MCP**: The scraper_specialist persona definition says it uses Playwright + Fetch tools, but the orchestrator doesn't invoke personas - it directly calls methods. How should this work?