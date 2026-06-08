"""
Pydantic Schemas for Agentic Scraper Phase 1

SiteUnderstanding: High-level strategic overview of the entire site.
PageStructure: Detailed per-page artifact for builder personas to consume.
NavNode: Typed hierarchy for navigation trees.
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import List, Dict, Optional, Any, Literal
from enum import Enum
from datetime import datetime


class PlatformType(str, Enum):
    WIX = "wix"
    SQUARESPACE = "squarespace"
    WORDPRESS = "wordpress"
    SHOPIFY = "shopify"
    GENERIC = "generic"
    UNKNOWN = "unknown"


class PageType(str, Enum):
    HOME = "home"
    ABOUT = "about"
    SERVICES = "services"
    PORTFOLIO = "portfolio"
    BLOG = "blog"
    BLOG_POST = "blog_post"
    CONTACT = "contact"
    GALLERY = "gallery"
    LEGAL = "legal"
    OTHER = "other"


class ComponentType(str, Enum):
    HERO = "hero"
    TEXT_BLOCK = "text_block"
    GALLERY = "gallery"
    CARDS = "cards"
    FORM = "form"
    NAV = "nav"
    FOOTER = "footer"
    TESTIMONIALS = "testimonials"
    CTA = "cta"
    PRICING = "pricing"
    FAQ = "faq"
    TEAM = "team"
    UNKNOWN = "unknown"


class ImageAsset(BaseModel):
    src: str
    alt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    role: Optional[str] = None  # hero, thumbnail, icon, logo, etc.


class Link(BaseModel):
    href: str
    text: Optional[str] = None
    is_internal: bool = False
    is_external: bool = False


class FormField(BaseModel):
    name: str
    label: Optional[str] = None
    type: str  # text, email, textarea, select, checkbox, etc.
    required: bool = False
    placeholder: Optional[str] = None
    options: List[str] = Field(default_factory=list)  # for select fields


class Component(BaseModel):
    type: ComponentType
    order: int
    content: Dict[str, Any] = Field(default_factory=dict)
    assets: List[ImageAsset] = Field(default_factory=list)
    layout: Optional[Dict[str, Any]] = None  # grid columns, flex direction, spacing
    text_content: Optional[str] = None  # text content specific to this component


class JsonLdSchema(BaseModel):
    """Structured data found on the page (JSON-LD schema.org data)."""
    schema_type: str  # Organization, LocalBusiness, Product, Article, etc.
    raw: Dict[str, Any] = Field(default_factory=dict)


class PageStructure(BaseModel):
    """Detailed structure of a single page. Rich artifact for downstream builders."""
    url: HttpUrl
    canonical_url: Optional[HttpUrl] = None
    title: str
    page_type: List[PageType]  # pages can serve multiple types
    template_id: Optional[str] = None  # shared template ID if this page uses same template as others
    meta_description: Optional[str] = None
    headings: Dict[str, List[str]] = Field(default_factory=dict)  # h1, h2, h3...
    components: List[Component] = Field(default_factory=list)
    images: List[ImageAsset] = Field(default_factory=list)
    links: List[Link] = Field(default_factory=list)
    forms: List[List[FormField]] = Field(default_factory=list)
    text_content: str = ""  # Full semantic text content (primary content for rebuild)
    text_word_count: Optional[int] = None  # word count for effort estimation
    seo: Dict[str, Any] = Field(default_factory=dict)  # og:title, og:description, twitter:card
    json_ld: List[JsonLdSchema] = Field(default_factory=list)  # schema.org structured data
    breadcrumb_path: List[str] = Field(default_factory=list)  # ["Home", "Services", "SEO"]
    cta_text: List[str] = Field(default_factory=list)  # call-to-action phrases
    notes: List[str] = Field(default_factory=list)  # LLM observations
    navigation_from_page: List[str] = Field(default_factory=list)  # discovered links from this page


class NavNode(BaseModel):
    """A node in the site navigation hierarchy."""
    label: str
    url: Optional[str] = None  # None for dropdown-only labels
    page_url: Optional[HttpUrl] = None  # tied to a PageStructure
    children: List["NavNode"] = Field(default_factory=list)
    is_dropdown: bool = False
    is_cta_button: bool = False  # e.g. "Get Started" button in nav


NavNode.model_rebuild()


class SiteUnderstanding(BaseModel):
    """High-level map and strategic understanding of the entire site."""
    url: HttpUrl
    platform: PlatformType
    platform_confidence: float = Field(ge=0.0, le=1.0)
    site_name: str
    total_pages_discovered: int
    pages: List[PageStructure]  # Detailed per-page structures
    global_assets: Dict[str, Any] = Field(default_factory=dict)  # logo, favicon, social
    contact_info: Dict[str, str] = Field(default_factory=dict)
    navigation_structure: List[NavNode] = Field(default_factory=list)  # typed nav hierarchy
    estimated_fidelity: float = Field(ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    reasoning_trace: List[str] = Field(default_factory=list)  # LLM's step-by-step reasoning
    raw_artifacts: Dict[str, Any] = Field(default_factory=dict)  # For debugging / replay


class ScraperConfig(BaseModel):
    """Configuration for scraper orchestrator (used by LLM agent internally)."""
    max_iterations: int = 30
    timeout_ms: int = 30000
    respect_robots_txt: bool = True


class ComponentSpec(BaseModel):
    component_id: str
    component_type: ComponentType
    file_path: str
    props_schema: Dict[str, Any] = Field(default_factory=dict)
    is_reusable: bool = True
    page_scope: List[str] = Field(default_factory=list)
    complexity: Literal["simple", "medium", "complex"] = "simple"
    notes: str = ""


class PageSpec(BaseModel):
    url: str
    route: str
    component_ids: List[str] = Field(default_factory=list)
    data_source: Literal["static", "cms", "api"] = "static"
    cms_content_type: Optional[str] = None
    template_id: Optional[str] = None
    priority: Literal["critical", "standard", "optional"] = "standard"
    notes: str = ""


class RedirectRule(BaseModel):
    from_url: str
    to_url: str
    redirect_type: Literal["permanent", "temporary"] = "permanent"


class SeoMigrationPlan(BaseModel):
    url_mapping: List[RedirectRule] = Field(default_factory=list)
    canonical_strategy: str = "preserve"
    og_image_strategy: str = "migrate"
    json_ld_action: Literal["preserve", "migrate-to-nextjs", "drop"] = "preserve"


class ImageMigrationStrategy(BaseModel):
    source_pattern: str = ""
    target_strategy: str = "preserve-cdn"
    cdn_domain: Optional[str] = None


class DeploymentSpec(BaseModel):
    fly_app_name: str = ""
    github_repo: str = ""
    base_branch: Literal["main", "production"] = "main"
    preview_branch_prefix: str = "preview/"
    env_vars: List[Dict[str, str]] = Field(default_factory=list)
    secret_keys: List[str] = Field(default_factory=list)
    fly_regions: List[str] = Field(default_factory=lambda: ["lax"])


class ArchitectureDecision(BaseModel):
    category: str
    decision: str
    rationale: str
    alternatives_considered: List[str] = Field(default_factory=list)
    risk: Literal["low", "medium", "high"] = "low"


class SiteArchitecture(BaseModel):
    source_url: str
    source_understanding_id: Optional[str] = None
    target_stack: Dict[str, str] = Field(default_factory=dict)
    deployment: DeploymentSpec = Field(default_factory=DeploymentSpec)
    pages: List[PageSpec] = Field(default_factory=list)
    components: List[ComponentSpec] = Field(default_factory=list)
    image_strategy: ImageMigrationStrategy = Field(default_factory=ImageMigrationStrategy)
    seo_migration: SeoMigrationPlan = Field(default_factory=SeoMigrationPlan)
    architecture_decisions: List[ArchitectureDecision] = Field(default_factory=list)
    estimated_build_hours: float = 0.0
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    warnings: List[str] = Field(default_factory=list)
    reasoning_trace: List[str] = Field(default_factory=list)


class ToneOfVoice(BaseModel):
    voice: Literal["professional", "warm", "authoritative", "playful", "inspirational"] = "professional"
    pitch: str = ""
    example_phrases: List[str] = Field(default_factory=list)


class PageContentStrategy(BaseModel):
    route: str
    page_type: str
    content_approach: Literal["preserve", "modernize", "rewrite", "expand", "condense"]
    headline_recommendation: str = ""
    body_recommendation: str = ""
    cta_recommendation: str = ""
    seo_enhancement: str = ""
    notes: str = ""


class ContentVariant(BaseModel):
    variant_id: str
    tone_of_voice: ToneOfVoice
    content_approaches: List[str]
    recommended_pages: List[str]
    headline_templates: List[str]
    body_templates: List[str]
    cta_variations: List[str]
    competitive_positioning: str
    differentiation_points: List[str]
    rationale: str


class BrandSpec(BaseModel):
    primary_color: str = "#0F172A"
    secondary_color: str = "#475569"
    accent_color: str = "#6366F1"
    background_color: str = "#FFFFFF"
    text_color: str = "#1E293B"
    semantic_tokens: Dict[str, str] = Field(default_factory=dict)
    font_family_heading: str = "Inter, system-ui, sans-serif"
    font_family_body: str = "Inter, system-ui, sans-serif"
    font_size_base: str = "16px"
    type_scale: Dict[str, str] = Field(default_factory=dict)
    spacing_scale: Dict[str, str] = Field(default_factory=dict)
    border_radius: str = "0.375rem"
    shadow_scale: Dict[str, str] = Field(default_factory=dict)
    motion_philosophy: Literal["subtle", "energetic", "classical", "monastic"] = "subtle"
    motion_duration: str = "200ms"
    motion_easing: str = "ease-out"
    component_variants: Dict[str, List[str]] = Field(default_factory=dict)
    dark_mode_strategy: Literal["full_tokens", "auto_invert", "none"] = "full_tokens"
    notes: str = ""


class PolishChange(BaseModel):
    file: str
    change: str
    reason: str
    brand_spec_reference: str = ""


class SelfCritique(BaseModel):
    visual_weight_issues: List[str] = Field(default_factory=list)
    typography_hierarchy_suggestions: List[str] = Field(default_factory=list)
    emotional_resonance_gaps: List[str] = Field(default_factory=list)
    brand_token_violations: List[str] = Field(default_factory=list)
    motion_philosophy_alignment: str = "aligned"
    severity: Literal["high", "medium", "low"] = "low"
    recommended_action: str = "None - acceptable trade-off"


class VisualDirection(BaseModel):
    """Lightweight STRICT DELTA on BrandSpec — captures design evolution decisions.

    Used by UI Designer persona to record direction changes, reasoning, and impact.
    NOT a replacement for BrandSpec — composes on top of it.
    VisualDirection must NEVER duplicate fields already in BrandSpec. Only add
    page-specific or layout-specific overrides. Deltas are applied AFTER BrandSpec.
    """
    delta_id: str = ""
    parent_brand_spec_version: str = ""
    primary_change: str = ""  # "Shift from minimalist to bold editorial"
    rationale: str = ""  # "Source site uses heavy typography to convey authority"
    impacted_components: List[str] = Field(default_factory=list)  # component_ids affected
    impacted_pages: List[str] = Field(default_factory=list)  # route paths affected
    color_delta: Optional[Dict[str, str]] = None  # {primary_color: "#E63946"} delta ONLY — never repeat BrandSpec fields
    typography_delta: Optional[Dict[str, Any]] = None  # {font_family_heading: "Playfair Display"} delta ONLY
    motion_delta: Optional[Dict[str, Any]] = None  # {motion_philosophy: "energetic"} delta ONLY
    designer_notes: List[str] = Field(default_factory=list)
    created_by: str = "ui_designer"
    created_at: str = ""
    stitch_status: str = "available"  # "available" | "unavailable" | "partial"
    schema_version: str = "1.1"
    page_layouts: Optional[Dict[str, Dict[str, Any]]] = None  # {"/": {grid_system, spacing_philosophy, section_order, ...}}
    typography_hierarchy: Optional[Dict[str, Dict[str, Any]]] = None  # {"/": {h1: {size, weight, tracking}, ...}}
    motion_class_map: Optional[Dict[str, str]] = None  # {card_hover: "motion-classical", ...}
    reference_images: List[str] = Field(default_factory=list)  # local paths or URLs to reference images

    def validate_delta_no_duplication(self, brand_spec: Optional["BrandSpec"] = None) -> List[str]:
        """Check for fields in delta that duplicate BrandSpec. Returns list of warnings."""
        if not brand_spec:
            return []
        warnings = []
        brand_fields = {k: v for k, v in brand_spec.model_dump().items() if v and k not in ("notes",)}
        if self.color_delta:
            for key in self.color_delta:
                if key in brand_fields:
                    warnings.append(f"color_delta.{key} duplicates BrandSpec.{key} — applying BrandSpec value")
        if self.typography_delta:
            for key in self.typography_delta:
                if key in brand_fields:
                    warnings.append(f"typography_delta.{key} duplicates BrandSpec.{key} — applying BrandSpec value")
        if self.motion_delta:
            for key in self.motion_delta:
                if key in brand_fields:
                    warnings.append(f"motion_delta.{key} duplicates BrandSpec.{key} — applying BrandSpec value")
        return warnings


class BuildManifest(BaseModel):
    migration_id: str = ""
    source_url: str = ""
    source_understanding_id: Optional[str] = None
    source_architecture_id: Optional[str] = None
    source_recommendation_id: Optional[str] = None
    chosen_variant: Optional[str] = None
    brand_spec: Optional[BrandSpec] = None
    visual_direction: Optional[VisualDirection] = None
    output_dir: str = ""  # e.g., "sites/merimee-solutions/"
    ui_polish_version: str = "v1"
    ui_polish_changes: List[PolishChange] = Field(default_factory=list)
    self_critique: SelfCritique = Field(default_factory=SelfCritique)
    lighthouse_scores: Dict[str, Any] = Field(default_factory=dict)
    overall_quality_score: float = Field(ge=0.0, le=100.0, default=0.0)
    build_timestamp: str = ""
    personas_used: List[str] = Field(default_factory=list)
    deployment_readiness: Dict[str, Any] = Field(default_factory=dict)

    # Closed-loop migration fields
    rework_log: List[Dict[str, Any]] = Field(default_factory=list)  # [{persona, iteration, artifact_path, gap_ids, timestamp, gap_context}]
    iteration_history: List[Dict[str, Any]] = Field(default_factory=list)  # per-persona iteration counts
    final_state: Optional[str] = None  # "complete" | "github_issue_created" | "abort"
    completed_at: Optional[str] = None


class ContentRecommendation(BaseModel):
    source_url: str
    source_understanding_id: Optional[str] = None
    source_architecture_id: Optional[str] = None
    site_name: str
    overall_content_strategy: str
    tone_of_voice: ToneOfVoice
    brand_spec: Optional[BrandSpec] = None
    page_strategies: List[PageContentStrategy] = Field(default_factory=list)
    variants: List[ContentVariant] = Field(default_factory=list)
    chosen_variant: Optional[str] = None
    final_rationale: str = ""
    brand_preservation_notes: List[str] = Field(default_factory=list)
    seo_content_opportunities: List[str] = Field(default_factory=list)
    reasoning_trace: List[str] = Field(default_factory=list)


class GitHubRepoSpec(BaseModel):
    """Specification for GitHub repo creation under Alira OS org."""
    repo_name: str  # e.g., "saint-joseph-the-worker-academy"
    full_name: str = ""  # e.g., "Alira-os/saint-joseph-the-worker-academy"
    description: str = "Migrated site via Elyra AI"
    private: bool = True
    has_issues: bool = True
    has_wiki: bool = False
    default_branch: str = "main"
    org: str = "Alira-os"


class RepoTransferResult(BaseModel):
    """Result of a repo transfer operation."""
    success: bool
    repo_url: str
    transfer_script: str = ""  # gh repo transfer command for human approval
    message: str = ""


class PromotionState(BaseModel):
    """State tracking for the promotion pipeline."""
    migration_id: str
    local_build_path: str = ""
    preview_url: Optional[str] = None
    preview_expires_at: Optional[datetime] = None
    github_repo: Optional[str] = None
    github_pr_url: Optional[str] = None
    kcore_review_passed: bool = False
    security_gate_passed: bool = False
    human_approved: bool = False
    human_approved_by: Optional[str] = None
    production_url: Optional[str] = None
    lighthouse_scores: Dict[str, float] = Field(default_factory=dict)
    stage: Literal["build", "review", "preview", "approval", "deploy", "live", "failed"] = "build"
    blocking_issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class DeployResult(BaseModel):
    """Result from the Deploy Specialist."""
    repo_url: str = ""
    preview_url: Optional[str] = None
    preview_expires_at: Optional[datetime] = None
    production_url: Optional[str] = None
    deploy_complete: bool = False
    ci_status: str = "pending"
    lighthouse_scores: Dict[str, float] = Field(default_factory=dict)
    approval_status: Literal["pending", "approved", "rejected", "timeout"] = "pending"
    kcore_review_status: Literal["pending", "passed", "failed", "skipped"] = "skipped"
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


if __name__ == "__main__":
    nav = NavNode(
        label="Services",
        url="/services",
        children=[
            NavNode(label="SEO", url="/services/seo"),
            NavNode(label="Design", url="/services/design"),
        ]
    )
    page = PageStructure(
        url="https://example.com",
        title="Home",
        page_type=[PageType.HOME],
        text_content="Welcome to our site. We provide SEO and design services.",
        text_word_count=9,
        cta_text=["Get Started", "Learn More"],
        breadcrumb_path=["Home"],
        components=[
            Component(
                type=ComponentType.HERO,
                order=0,
                content={"headline": "Welcome", "subheadline": "We build things"},
            )
        ]
    )
    print(page.model_dump_json(indent=2))


# --- Manager / Orchestrator Decision Schema --------------------------------
#
# Phase 0.7: ManagerDecision was a plain @dataclass with no validation. The
# LLM-driven manager persona occasionally produced malformed decisions
# ("Missing action in manager decision" aborts). Migrating to Pydantic lets
# us use the shared extract_json helper + Pydantic validation to either
# recover the decision or fall through to a deterministic abort — no more
# "the manager persona returned prose" class of failures.

class ManagerDecision(BaseModel):
    """Routing decision produced by the Manager persona.

    `action` is a closed enum so the manager loop can dispatch on it
    exhaustively without string typos causing silent fallthroughs. The
    LLM is told to return ONLY this shape; the validator coerces / strips
    anything else.
    """
    action: Literal[
        "invoke_persona",
        "route_back",
        "complete",
        "github_issue_created",
        "abort",
    ]
    persona: Optional[str] = None
    reason: str = ""
    gaps_detected: List[Dict[str, Any]] = Field(default_factory=list)
    retry_with_modified_prompt: Optional[str] = None
    gap_context: Optional[str] = None  # crisp 2-4 bullet summary for route_back
    gate_report: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None  # 0.0-1.0, used by LLM-driven decisions
    iteration: Optional[int] = None  # current iteration count when decision was made
    # Phase 1.0: room + steward routing context. Lets the manager's decision
    # be tagged with the room it came from and the steward who is
    # responsible for first-line coordination there. Default values keep
    # legacy decisions valid (everything was implicit in the planning room).
    room: Optional[Literal["planning", "forge"]] = None
    steward: Optional[str] = None  # name of the steward persona, if any


# --- Phase 1.0: Room + Steward + HandoffBundle + CoherenceGateReport --------
#
# These four schemas are the structural primitives the Dual-Room design
# calls for. They are Pydantic models (not @dataclass) so they participate
# in the same validation, JSON-safe serialization, and gap-ledger flow
# as ManagerDecision. They are *not yet wired into the orchestrator* —
# they exist as the contract for the next phase. Review the shapes and
# we will wire them in.


class Room(BaseModel):
    """A phase-bounded container of persona work.

    A Room is a logical scope in which a Steward coordinates a small set
    of personas. Rooms have:
      - A name (planning, forge, plus future rooms like 'review' or 'qa').
      - A small set of Personas that work in the room.
      - A Steward (the Architect in Planning, the Integration Coordinator
        in Forge) who is the first-line coordinator.
      - A set of In/Out contracts describing what the room needs and
        produces.
      - A coherence gate that must pass before the room emits its bundle.
    """
    name: Literal["planning", "forge"]
    description: str
    personas: List[str] = Field(default_factory=list)
    steward: str
    inputs: List[str] = Field(default_factory=list)  # what the room needs to start
    outputs: List[str] = Field(default_factory=list)  # what the room produces
    coherence_gate: Optional[str] = None  # name of the gate (gate type)
    # Recommended initial discovery order (flexible starting point — the
    # manager/steward can adjust or run limited parallel work). Per the
    # design: "Recommended Initial Discovery Order (flexible starting
    # point — manager/steward can adjust or run limited parallel work)."
    # Empty list means "no recommendation" — the steward picks.
    preflight_order: List[str] = Field(default_factory=list)

    def contains_persona(self, persona: str) -> bool:
        return persona in self.personas

    def ordered_personas(self) -> List[str]:
        """Return personas in preflight order, with any unspecified ones
        appended in their original `personas` list order. Useful for the
        pre-flight loop, which wants an explicit list to iterate.

        If `preflight_order` is empty, returns `personas` as-is.
        """
        if not self.preflight_order:
            return list(self.personas)
        seen = set()
        ordered: List[str] = []
        for p in self.preflight_order:
            if p in self.personas and p not in seen:
                ordered.append(p)
                seen.add(p)
        for p in self.personas:
            if p not in seen:
                ordered.append(p)
                seen.add(p)
        return ordered


class Steward(BaseModel):
    """A persona (or named coordinator) responsible for first-line routing
    inside a Room.

    Stewards are *not* gatekeepers — they don't block handoffs or make
    safety-rail decisions. They're the named coordinator the manager
    delegates to for routine work inside their room. Examples:
      - Planning Steward: Architect Specialist (Architecture Owner + Integrator)
      - Forge Steward: Integration Coordinator (Smoother of rough edges)

    `capabilities` is a free-form list of things the steward can do that
    the manager might want to delegate ("rich_bidirectional_pull",
    "cross_artifact_review", "design_token_consistency").
    """
    name: str
    room: str  # Room.name
    persona_ref: str  # the actual persona name to invoke (e.g. "architect_specialist")
    role_description: str
    capabilities: List[str] = Field(default_factory=list)


class CoherenceGateWaiver(BaseModel):
    """A documented exception to a Coherence Gate failure.

    When the gate fails but the room is allowed to proceed, a waiver
    is recorded. The waiver has a `reason`, an `owner` (who is taking
    responsibility for the risk), and a `risk_level`.
    """
    field: str  # which gate check failed
    reason: str  # why we're proceeding anyway
    owner: str  # who is taking responsibility
    risk_level: Literal["low", "medium", "high", "critical"]
    mitigation: Optional[str] = None  # what we'll do to reduce the risk


class CoherenceGateReport(BaseModel):
    """Result of running a Coherence Gate.

    A gate has 5 inputs (per the design) and 5 outputs. We make the
    outputs first-class fields so they can be persisted in the gap
    ledger / blackboard without losing the gate context.
    """
    gate_name: str
    passed: bool
    blocking: List[str] = Field(default_factory=list)  # hard failures
    warnings: List[str] = Field(default_factory=list)
    waivers: List[CoherenceGateWaiver] = Field(default_factory=list)
    artifact_coverage: Dict[str, bool] = Field(default_factory=dict)
    # Fidelity score from the Architect (0.0-1.0). The gate refuses
    # if this is below threshold (default 0.7) unless a waiver covers it.
    fidelity_score: Optional[float] = None
    fidelity_threshold: float = 0.7
    # Free-form: any other room-level signals (e.g. open_questions_count,
    # bidirectional_pull_count, design_token_consistency_score).
    signals: Dict[str, Any] = Field(default_factory=dict)
    evaluated_at: str = ""  # ISO timestamp; set by caller

    def summarize(self) -> str:
        if self.passed:
            waiver_note = f" ({len(self.waivers)} waivers)" if self.waivers else ""
            return f"PASS{waiver_note}"
        return f"FAIL: {len(self.blocking)} blocking, {len(self.warnings)} warnings"


class HandoffBundle(BaseModel):
    """The structured bundle that crosses from one Room to the next.

    Per the design, the bundle is the *first-class primitive* that
    connects Planning to Forge. It carries:
      - All planning artifacts + their rationale + open questions
      - Known gaps with their target_persona
      - The Coherence Gate result + any waivers
      - Migration success criteria (from onboarding + memory)
      - Optional human-review flag (set by the manager when risk is high)

    The bundle is serialized to memory/<migration_id>/handoff_bundle.json
    when the handoff ceremony completes, so the Forge Room has a single
    well-typed input to start from.
    """
    bundle_id: str
    migration_id: str
    site_slug: str
    from_room: Literal["planning", "forge"]  # expanded when new rooms ship
    to_room: Literal["planning", "forge"]

    # Artifact references (pointers into the per-migration blackboard)
    site_understanding_id: Optional[str] = None
    site_architecture_id: Optional[str] = None
    content_recommendation_id: Optional[str] = None
    visual_direction_id: Optional[str] = None
    brand_spec: Optional[Dict[str, Any]] = None  # inlined — small and used everywhere

    # Rationale and open questions from the Planning Room
    planning_rationale: List[str] = Field(default_factory=list)
    open_questions: List[Dict[str, Any]] = Field(default_factory=list)
    # Each open question: {question, owner, eta, severity}

    # Gaps known at handoff time, with target_persona so the Forge Room
    # can route them efficiently.
    #
    # Why List[Dict[str, Any]] and not List[GapEntry] (Pydantic):
    # Phase 0.7 ran a remediation experiment (skills/agentic/remediation.py)
    # that compared the two shapes against a 3-gap bundle. Both produced
    # identical outcomes on the happy path. Pydantic would surface bad
    # data earlier — but only if GapEntry is strict enough to catch it.
    # Currently GapEntry's `severity` is `str` (no Literal), so a typo
    # like "kinda_high" passes Pydantic too. Until GapEntry tightens,
    # dicts are the right choice: zero conversion overhead at the
    # gap-ledger boundary, and the remediation logic is identical.
    # When GapEntry grows a Literal["low","medium","high","critical"]
    # on severity, revisit this decision.
    known_gaps: List[Dict[str, Any]] = Field(default_factory=list)

    # The Coherence Gate result (the design's "explicit lightweight review")
    coherence_gate: Optional[CoherenceGateReport] = None

    # Migration success criteria (from onboarding + memory lookups)
    success_criteria: List[str] = Field(default_factory=list)

    # If True, the manager has flagged this for human review because
    # risk or novelty is high. The Forge Room can still proceed but
    # the elyra_engineer / human will be looped in early.
    requires_human_review: bool = False
    human_review_reason: Optional[str] = None

    # Provenance — when each artifact was created and which persona.
    artifact_provenance: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    # artifact_provenance[artifact_name] = {created_at, persona, version}

    handoff_at: str = ""  # ISO timestamp; set by HandoffCeremony

    def to_memory_path(self) -> str:
        """Where this bundle is persisted in the per-migration blackboard."""
        return f"memory/migrations/{self.migration_id}/handoff_bundle.json"


# --- Phase 1.1: Forge Room Artifacts (DataContracts, APIContracts, DeploySpec) ---
#
# The Forge Room used to be a single monolithic builder. Phase 1.1 splits
# it into 5 specialized personas that produce 3 typed artifacts between
# them, with the Integration Coordinator smoothing rough edges and
# DevOps (Deployment Guardian) participating early.
#
# These schemas are the contracts. The persona modules reference them
# when parsing LLM output; the Integration Coordinator uses them to
# verify cross-layer consistency; and the orchestrator persists them
# into the per-migration blackboard so the engineer can review them.


class DataContract(BaseModel):
    """A typed data model. Produced by the Data Engineer.

    Represents one table / collection / content-type in the target
    architecture, with fields, types, and a CMS/data-sync note.
    """
    name: str  # e.g. "BlogPost", "Product", "LandingPage"
    kind: Literal["static", "cms", "database", "file"] = "static"
    fields: List[Dict[str, str]] = Field(default_factory=list)
    # Each field: {name, type, required, notes}
    relationships: List[str] = Field(default_factory=list)
    # Other data contracts this one references (by name)
    cms_sync: Optional[str] = None
    # Free-form note on how this model is populated from the source
    # (e.g. "synced from Wix CMS via fetch at build time")
    notes: str = ""


class DataContracts(BaseModel):
    """The bundle of all data contracts for a migration. One per Forge Room run."""
    migration_id: str
    site_slug: str
    contracts: List[DataContract] = Field(default_factory=list)
    # Free-form notes about the data architecture overall.
    data_architecture_summary: str = ""
    reasoning_trace: List[str] = Field(default_factory=list)
    produced_at: str = ""
    produced_by: str = ""  # persona name


class APIEndpoint(BaseModel):
    """A single API endpoint. Produced by the Backend Architect."""
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    path: str
    purpose: str
    request_schema: Optional[Dict[str, Any]] = None
    response_schema: Optional[Dict[str, Any]] = None
    auth_required: bool = False
    notes: str = ""


class APIContracts(BaseModel):
    """The bundle of API contracts for a migration. One per Forge Room run.

    For most static-site migrations this is mostly empty (the site
    is serverless) — the schema supports it for the cases where the
    customer has a backend, an API gateway, or webhooks.
    """
    migration_id: str
    site_slug: str
    base_url: Optional[str] = None
    auth_strategy: Optional[str] = None
    # E.g. "JWT via Supabase", "API key in header", "Public read-only"
    endpoints: List[APIEndpoint] = Field(default_factory=list)
    business_logic_summary: str = ""
    reasoning_trace: List[str] = Field(default_factory=list)
    produced_at: str = ""
    produced_by: str = ""


class DeploySpec(BaseModel):
    """The deploy specification. Produced by the DevOps Engineer (Deployment
    Guardian) EARLY in the Forge Room, so Backend and Data decisions
    can be informed by it.

    Per the design: "DevOps Engineer (Deployment Guardian) — participates
    early. Injects deployment, scaling, monitoring, security, and
    operational constraints into Backend and data decisions from the
    start. Owns IaC, CI/CD setup, preview environments, and
    'deployment-ready by design'."
    """
    migration_id: str
    site_slug: str
    platform: Literal["fly", "vercel", "netlify", "cloudflare_pages", "static_hosting", "other"] = "fly"
    # E.g. "fly.io" with the machine size in target_spec, "vercel" with
    # the framework preset, "static_hosting" with a CDN target.
    target_spec: Dict[str, Any] = Field(default_factory=dict)
    # Platform-specific settings (machine size, region, env vars list, etc.)
    scaling: Dict[str, Any] = Field(default_factory=dict)
    # E.g. {"min_instances": 1, "max_instances": 3, "cpu_kind": "shared"}
    monitoring: List[str] = Field(default_factory=list)
    # E.g. ["uptime_check", "error_rate_alert", "lighthouse_on_deploy"]
    security: List[str] = Field(default_factory=list)
    # E.g. ["https_only", "hsts_enabled", "cors_locked", "secrets_in_env"]
    ci_cd: List[str] = Field(default_factory=list)
    # E.g. ["github_actions", "preview_env_on_pr", "prod_deploy_on_main"]
    # Free-form notes (e.g. "this site uses long-lived images that
    # need a CDN cache; choose Cloudflare with cache_rules: 1y for /static/...")
    notes: str = ""
    reasoning_trace: List[str] = Field(default_factory=list)
    produced_at: str = ""
    produced_by: str = ""


class IntegrationStatus(BaseModel):
    """Output of the Integration Coordinator. Captures cross-layer
    consistency checks and final BuildManifest update.

    Per the design: "Integration Coordinator (Forge Steward / Go-Between
    + Smoother of Rough Edges). Receives outputs from the layered
    specialists. Smooths missed connections and rough edges. Maintains
    lightweight integration standards and resolves cross-layer friction.
    Maintains the evolving BuildManifest."
    """
    migration_id: str
    site_slug: str
    cross_layer_checks_run: List[str] = Field(default_factory=list)
    # E.g. ["api_path_consistent_with_frontend_routes", "design_tokens_applied_everywhere",
    #       "cms_models_match_frontend_data_fetchers", "deploy_env_vars_match_backend_env"]
    issues_found: List[str] = Field(default_factory=list)
    # Crisp description of each cross-layer friction the Coordinator resolved.
    resolutions: List[str] = Field(default_factory=list)
    # Crisp description of each resolution.
    final_build_manifest_id: Optional[str] = None
    # The ID of the final, Integration-cleaned BuildManifest artifact.
    reasoning_trace: List[str] = Field(default_factory=list)
    produced_at: str = ""
    produced_by: str = ""