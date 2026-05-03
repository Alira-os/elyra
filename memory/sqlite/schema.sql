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
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_migrations_platform ON migrations(platform);
CREATE INDEX IF NOT EXISTS idx_migrations_task_type ON migrations(task_type);
CREATE INDEX IF NOT EXISTS idx_migrations_outcome ON migrations(outcome);
CREATE INDEX IF NOT EXISTS idx_migrations_created_at ON migrations(created_at);

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