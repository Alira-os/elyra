-- Elyra Memory Layer - SQLite Schema
-- Phase 0 MVP: Structured metadata store (vector stubbed until Phase 1)

-- Migration history
CREATE TABLE IF NOT EXISTS migrations (
    id TEXT PRIMARY KEY,
    url TEXT,
    platform TEXT NOT NULL,  -- wix, squarespace, wordpress, generic
    task_type TEXT NOT NULL,  -- e-commerce, blog, portfolio, business, generic
    stack_chosen TEXT,  -- JSON of stack decision
    fidelity_score REAL,
    routing_used TEXT,  -- JSON array of personas invoked
    outcome TEXT NOT NULL,  -- success, partial, failed
    stage_history TEXT,  -- JSON array of stage transitions with timestamps
    fidelity_history TEXT,  -- JSON array of fidelity scores at each stage
    persona_versions TEXT,  -- JSON map of persona name to version used
    decisions TEXT,  -- JSON array of key architectural decisions made
    site_architecture_id TEXT,  -- FK to site_architectures table
    content_recommendation_id TEXT,  -- FK to content_recommendations table
    production_url TEXT,  -- set after production deploy
    github_repo TEXT,  -- full repo name e.g. "Alira-os/saint-joseph-the-worker-academy"
    preview_url TEXT,  -- temporary preview URL with TTL
    preview_expires_at DATETIME,  -- when preview URL expires
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_migrations_platform ON migrations(platform);
CREATE INDEX IF NOT EXISTS idx_migrations_task_type ON migrations(task_type);
CREATE INDEX IF NOT EXISTS idx_migrations_outcome ON migrations(outcome);
CREATE INDEX IF NOT EXISTS idx_migrations_created_at ON migrations(created_at);

-- Site architectures (from Architect Specialist)
CREATE TABLE IF NOT EXISTS site_architectures (
    id TEXT PRIMARY KEY,
    migration_id TEXT,
    source_url TEXT NOT NULL,
    target_stack TEXT NOT NULL,  -- JSON of stack decisions
    deployment_spec TEXT NOT NULL,  -- JSON of DeploymentSpec
    pages_spec TEXT,  -- JSON array of PageSpec
    components_spec TEXT,  -- JSON array of ComponentSpec
    image_strategy TEXT,  -- JSON of ImageMigrationStrategy
    seo_migration TEXT,  -- JSON of SeoMigrationPlan
    architecture_decisions TEXT,  -- JSON array of ArchitectureDecision
    estimated_build_hours REAL,
    confidence REAL,
    warnings TEXT,  -- JSON array
    reasoning_trace TEXT,  -- JSON array
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (migration_id) REFERENCES migrations(id)
);

CREATE INDEX IF NOT EXISTS idx_architectures_migration ON site_architectures(migration_id);

-- Content recommendations (from Marketing Specialist)
CREATE TABLE IF NOT EXISTS content_recommendations (
    id TEXT PRIMARY KEY,
    migration_id TEXT,
    source_url TEXT NOT NULL,
    site_name TEXT NOT NULL,
    content_strategy TEXT,  -- overall strategy description
    tone_of_voice TEXT,  -- JSON of ToneOfVoice
    page_strategies TEXT,  -- JSON array of PageContentStrategy
    variants TEXT,  -- JSON array of ContentVariant
    chosen_variant TEXT,
    final_rationale TEXT,
    brand_preservation_notes TEXT,  -- JSON array
    seo_opportunities TEXT,  -- JSON array
    reasoning_trace TEXT,  -- JSON array
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (migration_id) REFERENCES migrations(id)
);

CREATE INDEX IF NOT EXISTS idx_recommendations_migration ON content_recommendations(migration_id);

-- Migration: rename conflicting artifacts table (added 2026-05-23)
-- The old artifacts table has incompatible schema (no stage, content vs path)
-- This must run BEFORE the new artifacts table is created.
-- Uses a harmless error swallowed by "PRAGMA ignore_statement_errors=ON" approach
-- via Python-side exception handling. Only rename if both tables would collide.
CREATE TABLE IF NOT EXISTS artifacts_v0_deprecated (
    id TEXT PRIMARY KEY,
    migration_id TEXT,
    artifact_type TEXT,
    content TEXT,
    embedding_vector_id TEXT,
    tags TEXT,
    source_persona TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Debate outputs
CREATE TABLE IF NOT EXISTS debate_outputs (
    id TEXT PRIMARY KEY,
    migration_id TEXT NOT NULL,
    debate_result TEXT NOT NULL,  -- JSON of debate analysis
    human_approved BOOLEAN,
    changes_proposed TEXT,  -- JSON array of proposed changes
    changes_applied BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (migration_id) REFERENCES migrations(id)
);

CREATE INDEX IF NOT EXISTS idx_debate_migration ON debate_outputs(migration_id);
CREATE INDEX IF NOT EXISTS idx_debate_approved ON debate_outputs(human_approved);

-- Routing heuristics
CREATE TABLE IF NOT EXISTS routing_heuristics (
    platform TEXT NOT NULL,
    task_type TEXT NOT NULL,
    routing_sequence TEXT NOT NULL,  -- JSON array of persona names
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    avg_fidelity REAL,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (platform, task_type)
);

CREATE INDEX IF NOT EXISTS idx_heuristics_lookup ON routing_heuristics(platform, task_type);

-- Session state (for checkpointing)
CREATE TABLE IF NOT EXISTS session_state (
    session_id TEXT PRIMARY KEY,
    state_data TEXT NOT NULL,  -- JSON of full state
    current_phase TEXT NOT NULL,
    completed_steps TEXT,  -- JSON array
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_session_phase ON session_state(current_phase);