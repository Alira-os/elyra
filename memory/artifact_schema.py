"""
Elyra ArtifactStore — Data Model & Vector Schema Design
=======================================================

Source of truth for the engineering-senior-developer to implement.

Architecture Overview
---------------------
The ArtifactStore is part of Elyra's hybrid 5-layer memory system:
  Layer 1: SQLite metadata (this module) — provenance, indexing, FK relationships
  Layer 2: Git-tracked JSON blobs under memory/artifacts/<migration_id>/<type>/
  Layer 3: Per-site Git repos (Alira-os org)
  Layer 4: LanceDB semantic search (Phase 1+)
  Layer 5: Large media (external URLs, not in git)

Data Flow
---------
  Persona produces artifact → Scratch (.kilo/artifacts/<session>/) →
  promote_from_scratch() → permanent storage (Layer 1 SQLite + Layer 2 JSON + Layer 4 LanceDB)

Text-Based Data Flow Diagram for Promotion Path
------------------------------------------------

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  Persona Agent (scraper / designer / builder / etc.)                   │
  │  Produces artifact files in .kilo/artifacts/<session>/                  │
  └────────────────────────────────┬────────────────────────────────────────┘
                                   │
                                   ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │  promote_from_scratch(session_id, migration_id)                        │
  │                                                                         │
  │  1. LIST  .kilo/artifacts/<session>/  (all files)                     │
  │  2. CLASSIFY each file by type:                                        │
  │       nav.json       → NavArtifact                                      │
  │       meta.json      → MetaArtifact                                    │
  │       lighthouse.json→ LighthouseArtifact                               │
  │       decision.json  → DecisionArtifact                                │
  │       lesson.json    → LessonArtifact                                  │
  │       anti_pattern.json → AntiPatternArtifact                          │
  │       snapshot.json  → SnapshotArtifact                                │
  │       deploy_result.json → DeployResultArtifact                        │
  │  3. WRITE each to memory/artifacts/<migration_id>/<type>/<artifact_id>.json
  │  4. INSERT rows into SQLite artifacts table                             │
  │  5. EMBED into LanceDB (Phase 1+) — generate embedding for text field  │
  │  6. DELETE .kilo/artifacts/<session>/ (scratch cleanup)               │
  └────────────────────────────────┬────────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                              ▼
  ┌──────────────────────────────┐   ┌──────────────────────────────────┐
  │  SQLite artifacts table       │   │  LanceDB semantic_memory table   │
  │  (Layer 1 - provenance/FK)     │   │  (Layer 4 - vector search)       │
  │                               │   │                                  │
  │  id ──────────────────────────┼──►│  id (cross-ref)                  │
  │  migration_id (FK)            │   │  migration_id                    │
  │  stage                        │   │  artifact_type                   │
  │  persona_set (JSON array)     │   │  tags                            │
  │  decision_context             │   │  content (JSON string)           │
  │  artifact_type                │   │  embedding (list[float32])       │
  │  path (relative)              │   │  created_at                      │
  │  metadata (JSON)              │   │                                  │
  │  embedding_vector_id          │   └──────────────────────────────────┘
  │  tags (JSON array)            │
  │  created_at                   │
  │  promoted_at                  │
  └──────────────────────────────┘

Phase 0 Degradation (SQLite-only)
---------------------------------
In Phase 0, LanceDB is stubbed with an in-memory hash-based fallback store.
  - find_similar_artifacts() returns empty list (no semantic search)
  - All other SQLite-based query functions work normally
  - System continues to store artifacts in SQLite and Layer 2 JSON
  - No data loss during Phase 0; semantic search becomes available in Phase 1+

Provenance Enforcement
----------------------
Every persisted artifact MUST have:
  - migration_id  (which migration this belongs to)
  - stage         (scrape/design/build/verify/deploy)
  - persona_set   (which personas ran — JSON array of persona names)
  - decision_context (why was this artifact created — routing reason)

Validation decorator:
  @require_provenance(migration_id=True, stage=True, persona_set=True, decision_context=True)
  def save_artifact(artifact: BaseArtifact): ...

Or use the enforce_provenance() factory function before any insert.

Phase 0 vs Phase 1+ Storage
----------------------------
Phase 0: artifacts stored in SQLite (content JSON column) + Layer 2 JSON files
Phase 1+: artifacts stored in SQLite + Layer 2 JSON + LanceDB for semantic search

=======================================================================================
"""

from __future__ import annotations

import json
import uuid
import hashlib
import os
import re
import shutil
from datetime import datetime, timezone
from typing import Optional, Any
from pathlib import Path

# -----------------------------------------------------------------------------------------------
# Pydantic Models
# -----------------------------------------------------------------------------------------------

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from enum import Enum


class ArtifactStage(str, Enum):
    """Pipeline stage during which this artifact was produced."""
    SCRAPE = "scrape"
    DESIGN = "design"
    BUILD = "build"
    VERIFY = "verify"
    DEPLOY = "deploy"


class ArtifactType(str, Enum):
    """Discriminated union tag for artifact subtypes."""
    LESSON = "lesson"
    ANTI_PATTERN = "anti_pattern"
    ROUTING_INSIGHT = "routing_insight"
    DEPLOY_RESULT = "deploy_result"
    NAV = "nav"
    META = "meta"
    SNAPSHOT = "snapshot"
    DECISION = "decision"


class PersonaName(str, Enum):
    """Canonical persona names used in Elyra's registry."""
    MIGRATION_ORCHESTRATOR = "migration_orchestrator"
    ONBOARDING_SPECIALIST = "onboarding_specialist"
    SCRAPER_SPECIALIST = "scraper_specialist"
    STACK_INTELLIGENCE = "stack_intelligence"
    CODEGEN_CREW_LEAD = "codegen_crew_lead"
    UI_POLISH = "ui_polish"
    SECURITY_AUDITOR = "security_auditor"
    DEPLOY_SPECIALIST = "deploy_specialist"


# -----------------------------------------------------------------------------------------------
# Base Artifact — the root of the discriminated union
# -----------------------------------------------------------------------------------------------

class BaseArtifact(BaseModel):
    """
    Root artifact model. All artifact types inherit from this.

    Provenance fields (required on every instance):
      migration_id  — which migration this artifact belongs to
      stage          — which pipeline stage produced it
      persona_set    — which personas ran to produce this artifact
      decision_context — why this artifact was created (routing reason)

    Storage fields:
      id            — globally unique artifact ID (UUID4)
      artifact_type — discriminated union tag (lesson/anti_pattern/nav/meta/...)
      path          — relative path to Layer 2 JSON file (memory/artifacts/<migration_id>/<type>/)
      metadata      — freeform JSON, validated by subclass validators
      tags          — JSON array of searchable strings
      embedding_vector_id — FK to LanceDB (Phase 1+)
      created_at    — when artifact was first created (naive UTC)
      promoted_at   — when artifact moved from scratch to permanent storage

    Scalar JSON fields (stored as JSON text in SQLite):
      persona_set  → JSON array of strings
      tags         → JSON array of strings
      metadata     → JSON object
    """

    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=True,
    )

    # --- Provenance (required on every artifact) ---
    migration_id: str = Field(
        ...,
        description="Which migration this artifact belongs to. Foreign key to migrations.id.",
        min_length=1,
        max_length=64,
    )
    stage: ArtifactStage = Field(
        ...,
        description="Pipeline stage during which this artifact was produced.",
    )
    persona_set: list[str] = Field(
        ...,
        description="Which personas ran to produce this artifact. JSON array stored in SQLite.",
        min_length=1,
    )
    decision_context: str = Field(
        ...,
        description="Why this artifact was created — routing reason, what triggered it.",
        max_length=1024,
    )

    # --- Identity ---
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Globally unique artifact ID.",
    )
    artifact_type: ArtifactType = Field(
        ...,
        description="Discriminated union tag identifying the artifact subtype.",
    )

    # --- Storage ---
    path: Optional[str] = Field(
        default=None,
        description="Relative path to Layer 2 JSON file. Set by promote_from_scratch().",
        max_length=512,
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Freeform JSON object. Schema validated by subclass validators.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="JSON array of searchable strings. Used for LanceDB filtering.",
    )
    embedding_vector_id: Optional[str] = Field(
        default=None,
        description="FK to LanceDB vector ID. Populated after Phase 1 embedding.",
        max_length=64,
    )

    # --- Timestamps ---
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When artifact was first created (naive UTC).",
    )
    promoted_at: Optional[datetime] = Field(
        default=None,
        description="When artifact was moved from scratch to permanent storage.",
    )

    # --- Validators ---
    @field_validator("migration_id")
    @classmethod
    def validate_migration_id(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z0-9_\-]+$', v):
            raise ValueError(f"migration_id must be alphanumeric + dash/underscore, got: {v!r}")
        return v

    @field_validator("persona_set")
    @classmethod
    def validate_persona_set(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("persona_set must have at least one persona")
        for p in v:
            if not re.match(r'^[a-z_]+$', p):
                raise ValueError(f"Invalid persona name: {p!r} (use lowercase with underscores)")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        for tag in v:
            if len(tag) > 64:
                raise ValueError(f"Tag too long (max 64): {tag!r}")
            if not re.match(r'^[a-zA-Z0-9_\-]+$', tag):
                raise ValueError(f"Invalid tag: {tag!r} (use alphanumeric + dash/underscore)")
        return v

    @field_validator("decision_context")
    @classmethod
    def validate_decision_context(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError(f"decision_context must be at least 10 chars, got: {v!r}")
        return v.strip()

    # --- Helpers ---
    def to_row(self) -> dict:
        """Serialize to a SQLite insert-ready dict (JSON columns as text)."""
        return {
            "id": self.id,
            "migration_id": self.migration_id,
            "stage": self.stage.value if isinstance(self.stage, Enum) else self.stage,
            "persona_set": json.dumps(self.persona_set, ensure_ascii=False),
            "decision_context": self.decision_context,
            "artifact_type": self.artifact_type.value if isinstance(self.artifact_type, Enum) else self.artifact_type,
            "path": self.path,
            "metadata": json.dumps(self.metadata, ensure_ascii=False, default=str),
            "embedding_vector_id": self.embedding_vector_id,
            "tags": json.dumps(self.tags, ensure_ascii=False),
            "created_at": self.created_at.isoformat(),
            "promoted_at": self.promoted_at.isoformat() if self.promoted_at else None,
        }

    @classmethod
    def from_row(cls, row: dict) -> BaseArtifact:
        """Deserialize from a SQLite row dict (JSON text columns decoded)."""
        d = dict(row)
        for json_field in ("persona_set", "metadata", "tags"):
            if json_field in d and isinstance(d[json_field], str):
                d[json_field] = json.loads(d[json_field])
        # Handle enum values stored as strings
        if "stage" in d and isinstance(d["stage"], str):
            d["stage"] = d["stage"]
        if "artifact_type" in d and isinstance(d["artifact_type"], str):
            d["artifact_type"] = d["artifact_type"]
        return cls(**d)

    def embedding_text(self) -> str:
        """
        Return the text content used to generate the vector embedding.
        Subclasses override this to provide semantically meaningful embeddings.
        """
        return json.dumps(self.metadata, default=str, sort_keys=True)


# -----------------------------------------------------------------------------------------------
# Artifact Subtypes (Discriminated Union)
# -----------------------------------------------------------------------------------------------

class NavArtifact(BaseArtifact):
    """
    Navigation structure artifact produced by the scraper.

    metadata fields:
      nav_tree: list[NavNode] — typed navigation hierarchy
      total_nodes: int
      cta_buttons: list[str]
    """
    artifact_type: ArtifactType = Field(default=ArtifactType.NAV, frozen=True)

    def embedding_text(self) -> str:
        nav_nodes = self.metadata.get("nav_tree", [])
        labels = []
        for node in nav_nodes:
            if isinstance(node, dict):
                labels.append(node.get("label", ""))
            elif isinstance(node, str):
                labels.append(node)
        return f"nav: {', '.join(labels)}"


class MetaArtifact(BaseArtifact):
    """
    Site meta/properties artifact produced by onboarding or scraper.

    metadata fields:
      site_name: str
      platform: str
      task_type: str
      pages_discovered: int
      brand_color: str
    """
    artifact_type: ArtifactType = Field(default=ArtifactType.META, frozen=True)

    def embedding_text(self) -> str:
        site_name = self.metadata.get("site_name", "")
        platform = self.metadata.get("platform", "")
        task_type = self.metadata.get("task_type", "")
        return f"site: {site_name} ({platform} {task_type})"


class LighthouseArtifact(BaseArtifact):
    """
    Lighthouse audit results artifact produced by security_auditor or builder.

    metadata fields:
      performance: float (0-100)
      accessibility: float (0-100)
      best_practices: float (0-100)
      seo: float (0-100)
      scores: dict[str, float]
      url: str
      audited_at: str (ISO)
    """
    artifact_type: ArtifactType = Field(default=ArtifactType.META, frozen=True)

    @field_validator("metadata")
    @classmethod
    def validate_lighthouse_metadata(cls, v: dict) -> dict:
        score_fields = ["performance", "accessibility", "best_practices", "seo"]
        scores = v.get("scores", {})
        for field in score_fields:
            val = scores.get(field, v.get(field))
            if val is not None:
                if not isinstance(val, (int, float)):
                    raise ValueError(f"Lighthouse.{field} must be numeric, got: {type(val).__name__}")
                if not (0 <= val <= 100):
                    raise ValueError(f"Lighthouse.{field} must be 0-100, got: {val}")
        return v


class DecisionArtifact(BaseArtifact):
    """
    Architectural/design decision artifact produced by any persona.

    metadata fields:
      category: str (e.g., "stack", "routing", "content_strategy")
      decision: str
      rationale: str
      alternatives: list[str]
      risk: str (low/medium/high)
      outcome: str (success/failure/unknown)
    """
    artifact_type: ArtifactType = Field(default=ArtifactType.DECISION, frozen=True)

    def embedding_text(self) -> str:
        d = self.metadata
        return f"decision: {d.get('category','')} — {d.get('decision','')}. rationale: {d.get('rationale','')}"


class LessonArtifact(BaseArtifact):
    """
    Lesson learned artifact produced by any persona after reflection.

    metadata fields:
      description: str (what happened)
      pattern: str (e.g., "gallery", "nav", "seo")
      outcome: str (success/failure)
      platform: str (optional)
      task_type: str (optional)
    """
    artifact_type: ArtifactType = Field(default=ArtifactType.LESSON, frozen=True)

    def embedding_text(self) -> str:
        d = self.metadata
        return f"lesson: {d.get('description','')} [pattern={d.get('pattern','')} outcome={d.get('outcome','')}]"


class AntiPatternArtifact(BaseArtifact):
    """
    Anti-pattern discovered artifact produced by any persona.

    metadata fields:
      description: str (what went wrong)
      anti_pattern: str (name of the anti-pattern)
      cause: str (why it happened)
      workaround: str (how to avoid/fix)
      severity: str (high/medium/low)
    """
    artifact_type: ArtifactType = Field(default=ArtifactType.ANTI_PATTERN, frozen=True)

    def embedding_text(self) -> str:
        d = self.metadata
        return f"anti-pattern: {d.get('anti_pattern','')} — {d.get('description','')}"


class SnapshotArtifact(BaseArtifact):
    """
    Point-in-time system state snapshot artifact produced by orchestrator.

    metadata fields:
      phase: str
      completed_steps: list[str]
      current_step: str
      state_summary: dict
      fidelity_score: float
    """
    artifact_type: ArtifactType = Field(default=ArtifactType.SNAPSHOT, frozen=True)

    def embedding_text(self) -> str:
        d = self.metadata
        phase = d.get("phase", "")
        steps = d.get("completed_steps", [])
        return f"snapshot phase={phase} steps={len(steps)}"


class DeployResultArtifact(BaseArtifact):
    """
    Deployment result artifact produced by deploy_specialist.

    metadata fields:
      repo_url: str
      preview_url: str (optional)
      production_url: str (optional)
      deploy_complete: bool
      ci_status: str (pending/passing/failing)
      lighthouse_scores: dict[str, float]
      errors: list[str]
      warnings: list[str]
    """
    artifact_type: ArtifactType = Field(default=ArtifactType.DEPLOY_RESULT, frozen=True)

    def embedding_text(self) -> str:
        d = self.metadata
        preview = d.get("preview_url", "none")
        prod = d.get("production_url", "none")
        return f"deploy: repo={d.get('repo_url','?')} preview={preview} prod={prod}"


# -----------------------------------------------------------------------------------------------
# Type Registry for promotion classification
# -----------------------------------------------------------------------------------------------

ARTIFACT_TYPE_REGISTRY: dict[str, type[BaseArtifact]] = {
    "nav": NavArtifact,
    "meta": MetaArtifact,
    "lighthouse": LighthouseArtifact,   # file: lighthouse.json
    "decision": DecisionArtifact,
    "lesson": LessonArtifact,
    "anti_pattern": AntiPatternArtifact,
    "snapshot": SnapshotArtifact,
    "deploy_result": DeployResultArtifact,
}


# -----------------------------------------------------------------------------------------------
# Provenance Enforcement
# -----------------------------------------------------------------------------------------------

def enforce_provenance(
    migration_id: str,
    stage: ArtifactStage,
    persona_set: list[str],
    decision_context: str,
) -> dict:
    """
    Factory function that validates and returns a provenance dict.
    Call this before constructing any artifact to ensure provenance completeness.

    Raises ValueError if any required field is missing or invalid.

    Usage:
        provenance = enforce_provenance(
            migration_id="abc-123",
            stage=ArtifactStage.SCRAPE,
            persona_set=["scraper_specialist"],
            decision_context="Platform detected as wix — routing to scraper",
        )
        artifact = LessonArtifact(**provenance, metadata={...})
    """
    # Run same validation as BaseArtifact field validators
    if not migration_id or len(migration_id.strip()) == 0:
        raise ValueError("migration_id is required")
    if not re.match(r'^[a-zA-Z0-9_\-]+$', migration_id.strip()):
        raise ValueError(f"migration_id must be alphanumeric + dash/underscore, got: {migration_id!r}")

    if not isinstance(stage, ArtifactStage):
        raise ValueError(f"stage must be ArtifactStage enum, got: {type(stage).__name__}")

    if not persona_set or not isinstance(persona_set, list):
        raise ValueError("persona_set must be a non-empty list")
    for p in persona_set:
        if not re.match(r'^[a-z_]+$', p):
            raise ValueError(f"Invalid persona name: {p!r} (use lowercase with underscores)")

    if not decision_context or len(decision_context.strip()) < 10:
        raise ValueError(f"decision_context must be at least 10 chars, got: {decision_context!r}")

    return {
        "migration_id": migration_id.strip(),
        "stage": stage,
        "persona_set": persona_set,
        "decision_context": decision_context.strip(),
    }


def require_provenance(**required_fields: bool):
    """
    Decorator factory for provenance enforcement on artifact save functions.

    Usage:
        @require_provenance(migration_id=True, stage=True, persona_set=True, decision_context=True)
        def save_artifact(artifact: BaseArtifact, db: Database): ...

    The decorated function must receive artifact as first positional arg.
    """
    def decorator(fn):
        def wrapper(artifact: BaseArtifact, *args, **kwargs):
            missing = []
            for field, required in required_fields.items():
                if required:
                    val = getattr(artifact, field, None)
                    if val is None or (isinstance(val, (list, str)) and len(val) == 0):
                        missing.append(field)
            if missing:
                raise ValueError(
                    f"Artifact {artifact.__class__.__name__} missing required provenance fields: {missing}. "
                    f"Ensure enforce_provenance() was called before construction."
                )
            return fn(artifact, *args, **kwargs)
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator


# -----------------------------------------------------------------------------------------------
# Artifact CRUD (in-memory — wired to SQLite via ArtifactCRUD in crud.py)
# -----------------------------------------------------------------------------------------------

class ArtifactCRUD:
    """
    High-level artifact operations. Combines SQLite persistence + Layer 2 JSON + LanceDB.

    Phase 0: SQLite + Layer 2 only (LanceDB stubbed gracefully).
    Phase 1+: SQLite + Layer 2 + LanceDB embedding.
    """

    ARTIFACTS_BASE = Path("memory/artifacts")

    def __init__(self, db=None, vector_store=None):
        """
        Args:
            db: Database instance (memory.sqlite.crud.Database)
            vector_store: VectorStore instance (memory.vector.lessons.VectorStore)
                         If None, uses in-memory fallback (Phase 0 behavior).
        """
        self.db = db
        self.vector_store = vector_store

    def save(self, artifact: BaseArtifact) -> str:
        """
        Persist an artifact to SQLite + Layer 2 JSON file.

        Phase 0: LanceDB embedding skipped (vector_store may be None or stubbed).
        Phase 1+: Calls vector_store.add_artifact() to embed.

        Returns:
            artifact.id

        Raises:
            ValueError: if provenance fields are missing/invalid.
        """
        # Provenance enforcement
        enforce_provenance(
            migration_id=artifact.migration_id,
            stage=artifact.stage,
            persona_set=artifact.persona_set,
            decision_context=artifact.decision_context,
        )

        # Build Layer 2 JSON path
        type_dir = self.ARTIFACTS_BASE / artifact.migration_id / artifact.artifact_type.value
        type_dir.mkdir(parents=True, exist_ok=True)
        artifact.path = str(type_dir.relative_to(Path.cwd()) / f"{artifact.id}.json")

        # Write Layer 2 JSON
        with open(type_dir / f"{artifact.id}.json", "w", encoding="utf-8") as f:
            json.dump(artifact.model_dump(mode="json"), f, indent=2, default=str)

        # Mark as promoted
        artifact.promoted_at = datetime.now(timezone.utc)

        # Persist to SQLite
        if self.db:
            row = artifact.to_row()
            self._insert_artifact_row(row)

        # Embed to LanceDB (Phase 1+)
        if self.vector_store and artifact.embedding_vector_id is None:
            try:
                vector_id = self.vector_store.add_artifact(
                    artifact_id=artifact.id,
                    content=artifact.model_dump(mode="json"),
                    artifact_type=artifact.artifact_type.value,
                    tags=artifact.tags,
                    migration_id=artifact.migration_id,
                    embedding_text=artifact.embedding_text(),
                )
                artifact.embedding_vector_id = vector_id
            except Exception:
                # Graceful degradation — don't fail artifact save if LanceDB fails
                pass

        return artifact.id

    def _insert_artifact_row(self, row: dict) -> None:
        """Insert a row into the SQLite artifacts table."""
        if not self.db:
            return
        conn = self.db._get_connection()
        try:
            conn.execute("""
                INSERT INTO artifacts (
                    id, migration_id, stage, persona_set, decision_context,
                    artifact_type, path, metadata, embedding_vector_id,
                    tags, created_at, promoted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["id"],
                row["migration_id"],
                row["stage"],
                row["persona_set"],
                row["decision_context"],
                row["artifact_type"],
                row["path"],
                row["metadata"],
                row["embedding_vector_id"],
                row["tags"],
                row["created_at"],
                row["promoted_at"],
            ))
            conn.commit()
        finally:
            conn.close()

    def get(self, artifact_id: str) -> Optional[BaseArtifact]:
        """Retrieve an artifact by ID from SQLite + reconstruct from Layer 2 JSON."""
        if not self.db:
            return None
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE id = ?", (artifact_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = self.db._get_columns(cursor)
            d = self.db._row_to_dict(row, columns)
            return BaseArtifact.from_row(d)
        finally:
            conn.close()

    def list_for_migration(self, migration_id: str) -> list[BaseArtifact]:
        """Get all artifacts for a given migration."""
        if not self.db:
            return []
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE migration_id = ? ORDER BY created_at DESC",
                (migration_id,)
            )
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            return [BaseArtifact.from_row(self.db._row_to_dict(r, columns)) for r in rows]
        finally:
            conn.close()

    def list_by_type(self, artifact_type: ArtifactType, limit: int = 50) -> list[BaseArtifact]:
        """Get artifacts filtered by type."""
        if not self.db:
            return []
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE artifact_type = ? ORDER BY created_at DESC LIMIT ?",
                (artifact_type.value, limit)
            )
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            return [BaseArtifact.from_row(self.db._row_to_dict(r, columns)) for r in rows]
        finally:
            conn.close()

    def list_by_stage(self, stage: ArtifactStage, limit: int = 50) -> list[BaseArtifact]:
        """Get artifacts filtered by stage."""
        if not self.db:
            return []
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE stage = ? ORDER BY created_at DESC LIMIT ?",
                (stage.value, limit)
            )
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            return [BaseArtifact.from_row(self.db._row_to_dict(r, columns)) for r in rows]
        finally:
            conn.close()

    def list_by_persona(self, persona_name: str, limit: int = 50) -> list[BaseArtifact]:
        """Get artifacts where a specific persona was in persona_set."""
        if not self.db:
            return []
        conn = self.db._get_connection()
        try:
            # persona_set is JSON array — search with LIKE for the persona name
            cursor = conn.execute(
                """SELECT * FROM artifacts
                   WHERE persona_set LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (f'%"{persona_name}"%', limit)
            )
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            return [BaseArtifact.from_row(self.db._row_to_dict(r, columns)) for r in rows]
        finally:
            conn.close()

    def delete(self, artifact_id: str) -> bool:
        """Delete an artifact (SQLite row + Layer 2 JSON file)."""
        artifact = self.get(artifact_id)
        if not artifact:
            return False
        # Delete Layer 2 JSON
        if artifact.path:
            p = Path(artifact.path)
            if p.exists():
                p.unlink()
        # Delete from SQLite
        if self.db:
            conn = self.db._get_connection()
            try:
                cursor = conn.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
        return True


# -----------------------------------------------------------------------------------------------
# Query Functions (Conductor's primary interface)
# -----------------------------------------------------------------------------------------------

class ArtifactQueries:
    """
    Key query functions the Conductor needs to drive routing decisions
    and memory-aware behavior.

    All methods accept an optional vector_store for Phase 1+ semantic search.
    Phase 0: falls back to SQLite-only filtering (no semantic similarity).
    """

    def __init__(self, db=None, vector_store=None):
        self.crud = ArtifactCRUD(db=db, vector_store=vector_store)
        self.db = db
        self.vector_store = vector_store

    def get_artifacts_for_migration(self, migration_id: str) -> list[BaseArtifact]:
        """
        Get all artifacts for a given migration.
        Used by Conductor to reconstruct full migration context.
        """
        return self.crud.list_for_migration(migration_id)

    def get_lessons_for_stage(self, stage: ArtifactStage, limit: int = 20) -> list[LessonArtifact]:
        """
        Get lessons learned at a given stage.
        Used to inform routing decisions for similar stages.
        """
        all_lessons = self.crud.list_by_type(ArtifactType.LESSON, limit=limit * 2)
        return [a for a in all_lessons if a.stage == stage][:limit]

    def find_similar_artifacts(
        self,
        query_text: str,
        artifact_types: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        limit: int = 5,
    ) -> list:
        """
        Semantic search over artifacts.

        Phase 0 (no LanceDB): returns empty list — semantic search unavailable.
        Phase 1+ (LanceDB wired): returns SemanticMatch objects with similarity scores.

        Args:
            query_text: Natural language query string
            artifact_types: Filter by artifact type names (e.g., ["lesson", "anti_pattern"])
            tags: Filter by required tags (AND logic — artifact must have all tags)
            limit: Max results

        Returns:
            Phase 0: []
            Phase 1+: list of SemanticMatch objects (artifact_id, content, similarity, tags, artifact_type)
        """
        if not self.vector_store:
            # Phase 0 graceful degradation — no semantic search available
            return []

        results = self.vector_store.search(
            query=query_text,
            artifact_types=artifact_types,
            tags=tags,
            limit=limit,
            similarity_threshold=0.0,
        )
        return results

    def get_recent_anti_patterns(self, limit: int = 10) -> list[AntiPatternArtifact]:
        """
        Get anti-patterns from recent migrations.
        Used to avoid known failure patterns during routing.
        """
        all_ap = self.crud.list_by_type(ArtifactType.ANTI_PATTERN, limit=limit * 3)
        return all_ap[:limit]

    def get_artifacts_by_persona(self, persona_name: str, limit: int = 50) -> list[BaseArtifact]:
        """
        Filter artifacts by which personas ran.

        Used to understand what a specific persona has contributed historically,
        enabling the Conductor to understand each persona's footprint.
        """
        return self.crud.list_by_persona(persona_name, limit=limit)

    def get_deploy_results(self, limit: int = 10) -> list[DeployResultArtifact]:
        """Get recent deployment results for deploy pattern analysis."""
        return self.crud.list_by_type(ArtifactType.DEPLOY_RESULT, limit=limit)

    def get_nav_artifacts(self, migration_id: Optional[str] = None) -> list[NavArtifact]:
        """Get navigation artifacts, optionally filtered by migration."""
        if migration_id:
            arts = self.crud.list_for_migration(migration_id)
            return [a for a in arts if a.artifact_type == ArtifactType.NAV]
        return self.crud.list_by_type(ArtifactType.NAV, limit=50)


# -----------------------------------------------------------------------------------------------
# Promotion Flow
# -----------------------------------------------------------------------------------------------

class PromotionPipeline:
    """
    Orchestrates the promotion of artifacts from scratch (.kilo/artifacts/<session>/)
    to permanent storage (memory/artifacts/<migration_id>/<type>/ + SQLite + LanceDB).

    Data Flow:
      1. LIST   .kilo/artifacts/<session>/   (enumerate all files)
      2. CLASSIFY each by filename → artifact subclass
      3. WRITE  memory/artifacts/<migration_id>/<type>/<id>.json  (Layer 2)
      4. INSERT SQLite artifacts table row
      5. EMBED  LanceDB (Phase 1+)
      6. DELETE scratch directory

    Classification by filename:
      nav.json              → NavArtifact
      meta.json             → MetaArtifact
      lighthouse.json        → LighthouseArtifact
      decision.json         → DecisionArtifact
      lesson.json           → LessonArtifact
      anti_pattern.json     → AntiPatternArtifact
      snapshot.json         → SnapshotArtifact
      deploy_result.json    → DeployResultArtifact
      (any other *.json)   → BaseArtifact (generic JSON blob)
    """

    SCRATCH_BASE = Path(".kilo/artifacts")

    # Filename → artifact type key mapping
    FILENAME_TYPE_MAP: dict[str, str] = {
        "nav": "nav",
        "meta": "meta",
        "lighthouse": "meta",         # Lighthouse stored as meta subtype
        "decision": "decision",
        "lesson": "lesson",
        "anti_pattern": "anti_pattern",
        "snapshot": "snapshot",
        "deploy_result": "deploy_result",
    }

    def __init__(self, db=None, vector_store=None):
        self.crud = ArtifactCRUD(db=db, vector_store=vector_store)
        self.db = db
        self.vector_store = vector_store

    def promote_from_scratch(
        self,
        session_id: str,
        migration_id: str,
        persona_set: list[str],
        stage: ArtifactStage,
        decision_context: str,
        base_path: Optional[Path] = None,
    ) -> dict[str, Any]:
        """
        Promote all artifacts from session scratch directory to permanent storage.

        Args:
            session_id: Scratch directory identifier (.kilo/artifacts/<session_id>/)
            migration_id: Target migration ID (where artifacts are filed)
            persona_set: Personas that ran during this session (propagated to all artifacts)
            stage: Pipeline stage this promotion represents
            decision_context: Routing reason for this promotion

        Returns:
            dict with promotion report:
              {
                "promoted": list[artifact_id],
                "failed": list[{filename, error}],
                "skipped": list[filename],
                "embedded": int (LanceDB embed count, Phase 1+),
                "deleted_scratch": bool,
              }
        """
        scratch_dir = (base_path or self.SCRATCH_BASE) / session_id

        if not scratch_dir.exists():
            raise FileNotFoundError(
                f"Scratch directory not found: {scratch_dir}. "
                f"Cannot promote artifacts for session {session_id!r}."
            )

        # List all JSON files in scratch directory
        json_files = list(scratch_dir.glob("*.json"))
        if not json_files:
            # Nothing to promote — clean up empty scratch dir
            shutil.rmtree(scratch_dir, ignore_errors=True)
            return {
                "promoted": [],
                "failed": [],
                "skipped": [],
                "embedded": 0,
                "deleted_scratch": True,
            }

        provenance = enforce_provenance(
            migration_id=migration_id,
            stage=stage,
            persona_set=persona_set,
            decision_context=decision_context,
        )

        promoted_ids: list[str] = []
        failed: list[dict] = []
        skipped: list[str] = []
        embedded_count = 0

        for json_file in json_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)

                # Classify by filename stem
                stem = json_file.stem.lower()
                type_key = self.FILENAME_TYPE_MAP.get(stem, "unknown")

                # Get artifact class
                artifact_cls = ARTIFACT_TYPE_REGISTRY.get(type_key, BaseArtifact)

                # Build provenance-enforced kwargs
                artifact_kwargs = {
                    **provenance,
                    "metadata": raw_data,
                    "tags": self._extract_tags(raw_data, type_key),
                }

                # Apply type-specific metadata overrides
                if type_key == "meta" and "lighthouse" in stem:
                    # Lighthouse files stored as MetaArtifact with lighthouse subtype
                    artifact_kwargs["metadata"] = {"lighthouse": raw_data}
                    artifact_kwargs["tags"] = ["lighthouse"] + artifact_kwargs["tags"]

                artifact = artifact_cls(**artifact_kwargs)

                # Save to SQLite + Layer 2
                artifact_id = self.crud.save(artifact)
                promoted_ids.append(artifact_id)

                # Track LanceDB embedding
                if artifact.embedding_vector_id:
                    embedded_count += 1

            except Exception as e:
                failed.append({"filename": json_file.name, "error": str(e)})

        # Delete scratch directory after successful promotion
        try:
            shutil.rmtree(scratch_dir, ignore_errors=True)
            deleted_scratch = True
        except Exception:
            deleted_scratch = False

        return {
            "promoted": promoted_ids,
            "failed": failed,
            "skipped": skipped,
            "embedded": embedded_count,
            "deleted_scratch": deleted_scratch,
        }

    def _extract_tags(self, raw_data: dict, type_key: str) -> list[str]:
        """Extract searchable tags from raw artifact data."""
        tags = set()
        # Platform/task tags
        if "platform" in raw_data:
            tags.add(str(raw_data["platform"]).lower())
        if "task_type" in raw_data:
            tags.add(str(raw_data["task_type"]).lower())
        # Stage tag
        tags.add(type_key)
        # Explicit tags field
        if "tags" in raw_data and isinstance(raw_data["tags"], list):
            for t in raw_data["tags"]:
                if isinstance(t, str):
                    tags.add(t.lower())
        return list(tags)[:20]  # Cap at 20 tags


# -----------------------------------------------------------------------------------------------
# LanceDB Collection Schema
# -----------------------------------------------------------------------------------------------

"""
LanceDB Collection: "semantic_memory"
======================================

Used for semantic similarity search over all Elyra artifacts.

Schema (LanceDB / Arrow):
-------------------------
Field               Type          Description
-----               ----          -----------
id                  string        Artifact ID (UUID) — primary key
migration_id        string        FK to migrations table
artifact_type       string        lesson / anti_pattern / routing_insight / deploy_result / nav / meta / snapshot / decision
tags                string        JSON array ["wix","portfolio","trades"]
content             string        Full JSON artifact content (for reconstruction)
content_hash        string        SHA-256 first 16 chars (deduplication)
embedding           list<float32> 128-dim embedding vector (Phase 1+ real embeddings)
embedding_text      string        The text that was embedded (for debugging/logging)
created_at          string        ISO timestamp

Indexes:
  - Vector index on embedding (IVF, nprobes=10)
  - Row-level index on artifact_type
  - Bloom filter on migration_id for fast filtering

Metadata stored for filtering (not embedded):
  - migration_id (filter by specific migration)
  - artifact_type (filter by type — used in query pattern "lessons only")
  - tags (JSON array — tag-based filtering)

Which field gets embedded?
  embedding_text() from each artifact subclass.
  For LessonArtifact: "lesson: {description} [pattern={pattern} outcome={outcome}]"
  For AntiPatternArtifact: "anti-pattern: {anti_pattern} — {description}"
  For NavArtifact: "nav: {comma-separated nav labels}"
  This ensures semantic search returns contextually similar artifacts.

Recommended Embedder (Phase 1+):
  - openai/text-embedding-3-small (1536 dim, $0.02/1K tokens) — best quality
  - OR local: sentence-transformers/all-MiniLM-L6-v2 (384 dim) — free, fast, good for internal use
  - Fallback: hash-based pseudo-embedding (Phase 0, 128 dim)

Phase 0 stub behavior:
  - _compute_simple_embedding() generates deterministic hash vectors
  - Enables basic cosine similarity for demo/development
  - find_similar_artifacts() returns empty list to signal "not wired"
"""

# -----------------------------------------------------------------------------------------------
# SQLite DDL (artifacts.sql)
# -----------------------------------------------------------------------------------------------

"""
-- Elyra ArtifactStore - SQLite DDL
-- Phase 0 MVP: Layer 1 metadata store (vector stubbed until Phase 1)

-- Full DDL for the artifacts table with all columns, indexes, and constraints.

CREATE TABLE IF NOT EXISTS artifacts (
    -- Primary key
    id                  TEXT PRIMARY KEY,

    -- Provenance (required on every artifact)
    migration_id        TEXT NOT NULL,      -- FK to migrations.id
    stage               TEXT NOT NULL,      -- scrape/design/build/verify/deploy
    persona_set         TEXT NOT NULL,      -- JSON array of persona names
    decision_context    TEXT NOT NULL,      -- routing reason (min 10 chars)

    -- Identity
    artifact_type       TEXT NOT NULL,      -- lesson/anti_pattern/routing_insight/deploy_result/nav/meta/snapshot/decision

    -- Storage
    path                TEXT,               -- relative path to Layer 2 JSON file
    metadata            TEXT NOT NULL,      -- JSON object (freeform, validated by subclass)
    embedding_vector_id TEXT,               -- FK to LanceDB (Phase 1+)

    -- Search/filter
    tags                TEXT,              -- JSON array of searchable strings

    -- Timestamps
    created_at          TEXT NOT NULL,      -- ISO timestamp (naive UTC)
    promoted_at         TEXT,              -- ISO timestamp when moved from scratch to permanent

    -- Constraints
    FOREIGN KEY (migration_id) REFERENCES migrations(id)
);

-- Indexes:

-- Primary lookup: artifacts by migration (most common query)
CREATE INDEX IF NOT EXISTS idx_artifacts_migration
    ON artifacts(migration_id);

-- Type filtering: get all lessons or all anti_patterns
CREATE INDEX IF NOT EXISTS idx_artifacts_type
    ON artifacts(artifact_type);

-- Stage filtering: get all scrape-stage artifacts for routing insights
CREATE INDEX IF NOT EXISTS idx_artifacts_stage
    ON artifacts(stage);

-- Tag search: artifacts with a specific tag (partial match via LIKE or JSON extraction)
-- Note: SQLite JSON1 extension used for tag filtering (tags LIKE '%"wix"%')
CREATE INDEX IF NOT EXISTS idx_artifacts_tags
    ON artifacts(tags);

-- Composite: migration + type (for targeted queries)
CREATE INDEX IF NOT EXISTS idx_artifacts_migration_type
    ON artifacts(migration_id, artifact_type);

-- Composite: migration + stage (for stage-level analysis)
CREATE INDEX IF NOT EXISTS idx_artifacts_migration_stage
    ON artifacts(migration_id, stage);

-- Persona filter: search persona_set JSON array (uses JSON1 LIKE pattern)
CREATE INDEX IF NOT EXISTS idx_artifacts_persona
    ON artifacts(persona_set);

-- Time-based queries: recent artifacts first
CREATE INDEX IF NOT EXISTS idx_artifacts_created_at
    ON artifacts(created_at DESC);

-- Recommended additional indexes beyond the primary ones:

-- 1. Anti-patterns by severity (if stored in metadata, use expression index)
-- CREATE INDEX IF NOT EXISTS idx_artifacts_severity
--     ON artifacts(CAST(json_extract(metadata, '$.severity') AS TEXT))
--     WHERE artifact_type = 'anti_pattern';

-- 2. Lighthouse score range queries (expression index on performance score)
-- CREATE INDEX IF NOT EXISTS idx_artifacts_lighthouse_perf
--     ON artifacts(CAST(json_extract(metadata, '$.scores.performance') AS REAL))
--     WHERE artifact_type = 'meta' AND json_extract(metadata, '$.lighthouse') IS NOT NULL;

-- 3. Tag intersection queries (for multi-tag filtering)
-- Tags are stored as JSON array, use JSON1 for queries:
--   SELECT * FROM artifacts WHERE json_each(tags) = 'wix';
-- This requires JSON1 extension which is built into SQLite.
"""

SQLITE_DDL = """
-- Elyra ArtifactStore - SQLite DDL
-- Phase 0 MVP: Layer 1 metadata store (vector stubbed until Phase 1)

CREATE TABLE IF NOT EXISTS artifacts (
    -- Primary key
    id                  TEXT PRIMARY KEY,

    -- Provenance (required on every artifact)
    migration_id        TEXT NOT NULL,
    stage               TEXT NOT NULL,  -- scrape/design/build/verify/deploy
    persona_set         TEXT NOT NULL,  -- JSON array of persona names
    decision_context    TEXT NOT NULL,  -- routing reason (min 10 chars)

    -- Identity
    artifact_type       TEXT NOT NULL,  -- lesson/anti_pattern/routing_insight/deploy_result/nav/meta/snapshot/decision

    -- Storage
    path                TEXT,           -- relative path to Layer 2 JSON file
    metadata            TEXT NOT NULL,  -- JSON object
    embedding_vector_id TEXT,           -- FK to LanceDB (Phase 1+)

    -- Search/filter
    tags                TEXT,          -- JSON array of searchable strings

    -- Timestamps
    created_at          TEXT NOT NULL,  -- ISO timestamp (naive UTC)
    promoted_at         TEXT,           -- ISO timestamp

    FOREIGN KEY (migration_id) REFERENCES migrations(id)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_migration
    ON artifacts(migration_id);

CREATE INDEX IF NOT EXISTS idx_artifacts_type
    ON artifacts(artifact_type);

CREATE INDEX IF NOT EXISTS idx_artifacts_stage
    ON artifacts(stage);

CREATE INDEX IF NOT EXISTS idx_artifacts_tags
    ON artifacts(tags);

CREATE INDEX IF NOT EXISTS idx_artifacts_migration_type
    ON artifacts(migration_id, artifact_type);

CREATE INDEX IF NOT EXISTS idx_artifacts_migration_stage
    ON artifacts(migration_id, stage);

CREATE INDEX IF NOT EXISTS idx_artifacts_persona
    ON artifacts(persona_set);

CREATE INDEX IF NOT EXISTS idx_artifacts_created_at
    ON artifacts(created_at DESC);
"""