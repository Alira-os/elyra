-- Elyra Artifact Store - SQLite Schema
-- Phase 0 MVP: Structured artifact provenance (vector stubbed until Phase 1)
--
-- Two-tier lifecycle:
--   .kilo/artifacts/<session>/  — ephemeral scratch (not persisted)
--   memory/artifacts/<migration_id>/  — persisted after run completes
--
-- This schema tracks persisted artifacts with full provenance.

-- Artifacts table: mandatory provenance fields
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    migration_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    persona_set TEXT NOT NULL,
    decision_context TEXT,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    metadata TEXT,
    embedding_vector_id TEXT,
    tags TEXT,
    scratch_source TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (migration_id) REFERENCES migrations(id)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_migration ON artifacts(migration_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_stage ON artifacts(stage);
CREATE INDEX IF NOT EXISTS idx_artifacts_persona_set ON artifacts(persona_set);
CREATE INDEX IF NOT EXISTS idx_artifacts_created_at ON artifacts(created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_tags ON artifacts(tags);
