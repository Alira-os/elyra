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
    typography_delta: Optional[Dict[str, str]] = None  # {font_family_heading: "Playfair Display"} delta ONLY
    motion_delta: Optional[Dict[str, str]] = None  # {motion_philosophy: "energetic"} delta ONLY
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