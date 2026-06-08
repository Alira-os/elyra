"""
Artifact Store v1 — Elyra Two-Tier Artifact Lifecycle.

Implements the tiered artifact lifecycle described in ADR-004:
  - Ephemeral: .kilo/artifacts/<session>/   (scratch during Kilo runs)
  - Persisted: memory/artifacts/<migration_id>/  (promoted after run completes)

Provides:
  - Pydantic models for all artifact types with mandatory provenance
  - ArtifactStore class: save(), query(), promote_from_scratch(), log_lesson()
  - Phase 0 stub: vector writes return empty until Phase 1

Mandatory provenance fields on every persisted artifact:
  - migration_id  — which migration this belongs to
  - stage         — which workflow stage produced it
  - persona_set   — which personas were invoked
  - decision_context — brief summary of the decision situation
  - artifact_type, path, metadata, tags, created_at

LanceDB integration (Phase 1):
  - Collection: "elyra_artifacts"
  - Embedder: sentence-transformers (all-MiniLM-L6-v2)
  - Each vector record stores: artifact_id, content_text, artifact_type, tags, migration_id, stage
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ArtifactType(str, Enum):
    """Known artifact types."""
    LESSON = "lesson"
    ANTI_PATTERN = "anti_pattern"
    ROUTING_INSIGHT = "routing_insight"
    DEPLOY_RESULT = "deploy_result"
    SITE_SUMMARY = "site_summary"
    SITE_UNDERSTANDING = "site_understanding"
    SITE_ARCHITECTURE = "site_architecture"
    CONTENT_RECOMMENDATION = "content_recommendation"
    MANAGER_DECISION = "manager_decision"
    QUALITY_GATE_REPORT = "quality_gate_report"
    PROMOTION_STATE = "promotion_state"


class WorkflowStage(str, Enum):
    """Workflow stages."""
    ONBOARDING = "onboarding"
    ROUTING = "routing"
    SCRAPING = "scraping"
    CODEGEN = "codegen"
    SECURITY_GATE = "security_gate"
    DEPLOY = "deploy"
    APPROVAL = "approval"
    COMPLETE = "complete"
    ABORT = "abort"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class ArtifactProvenance(BaseModel):
    """Mandatory provenance on every persisted artifact."""
    migration_id: str = Field(..., description="Which migration this artifact belongs to")
    stage: WorkflowStage = Field(..., description="Which workflow stage produced this artifact")
    persona_set: list[str] = Field(default_factory=list, description="Personas invoked to produce this artifact")
    decision_context: str = Field(default="", description="Concise summary of the decision situation")


class ArtifactMetadata(BaseModel):
    """Flexible metadata blob stored alongside every artifact."""
    original_filename: Optional[str] = None
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    summary: Optional[str] = None
    outcome: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
    duration_seconds: Optional[float] = None
    extra: dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class Artifact(ArtifactProvenance):
    """Complete artifact record with all fields."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    artifact_type: ArtifactType
    path: str
    metadata: ArtifactMetadata = Field(default_factory=ArtifactMetadata)
    embedding_vector_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    scratch_source: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump()
        d["artifact_type"] = self.artifact_type.value
        d["stage"] = self.stage.value
        d["metadata"] = self.metadata.model_dump()
        d["created_at"] = self.created_at.isoformat()
        return d


class LessonContent(BaseModel):
    """Structured content for a lesson artifact."""
    description: str = Field(..., description="Human-readable lesson description")
    pattern: Optional[str] = None
    outcome: Optional[str] = None
    suggested_fix: Optional[str] = None
    platform: Optional[str] = None
    task_type: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class ManagerDecisionRecord(BaseModel):
    """Structured manager decision for logging."""
    action: str
    persona: Optional[str] = None
    reason: str = ""
    gaps_detected: list[dict[str, Any]] = Field(default_factory=list)
    retry_with_modified_prompt: Optional[str] = None
    gap_context: Optional[str] = None
    gate_report: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Artifact Store
# ---------------------------------------------------------------------------

class ArtifactStore:
    """
    Two-tier artifact lifecycle manager.

    Tier 1 — Ephemeral scratch (.kilo/artifacts/<session>/):
        Kilo MCP tools write outputs directly here during a run.
        Files are NOT tracked in SQLite until promoted.

    Tier 2 — Persisted (memory/artifacts/<migration_id>/):
        After a run completes, promote_from_scratch() moves selected
        artifacts to the persisted directory and writes them to SQLite
        with full provenance.

    Phase 0:
        - SQLite writes only
        - Vector writes are a no-op (LanceDB not available)
        - promote_from_scratch() copies files but vector.add_artifact() is skipped
        - query_by_*() returns SQLite results only

    Phase 1:
        - LanceDB fully wired
        - log_lesson() writes to ArtifactStore + LanceDB
        - memory_query.py searches SQLite + LanceDB
    """

    # Class-level flag: disable LanceDB writes until Phase 1
    _PHASE_1_ENABLED: bool = False

    SCRATCH_DIR = Path(".kilo/artifacts")
    PERSIST_DIR = Path("memory/artifacts")

    def __init__(self, db_path: str = "elyra_memory.db"):
        self.db_path = db_path

        # Ensure directories exist
        self.SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        self.PERSIST_DIR.mkdir(parents=True, exist_ok=True)

        # Initialize SQLite schema
        self._ensure_schema()

        # Lazy import LanceDB components (graceful degradation)
        self._vector_store: Optional[VectorStoreProxy] = None

    # -----------------------------------------------------------------------
    # Public API — Save
    # -----------------------------------------------------------------------

    def save(
        self,
        artifact: Artifact,
    ) -> Artifact:
        """
        Persist an artifact to SQLite + disk.

        Args:
            artifact: Artifact with mandatory provenance fields populated.

        Returns:
            The saved Artifact (with id populated if not pre-set).

        Raises:
            ValueError: If provenance fields are missing.
        """
        # Validate mandatory provenance
        if not artifact.migration_id:
            raise ValueError("migration_id is required on every artifact")
        if not artifact.stage:
            raise ValueError("stage is required on every artifact")
        if not artifact.persona_set:
            raise ValueError("persona_set is required on every artifact")
        if not artifact.decision_context:
            raise ValueError("decision_context is required on every artifact")

        # Ensure directory for this migration exists
        mig_dir = self.PERSIST_DIR / artifact.migration_id
        mig_dir.mkdir(parents=True, exist_ok=True)

        # If path is not set, generate one
        if not artifact.path:
            filename = f"{artifact.artifact_type.value}_{artifact.id[:8]}.json"
            artifact.path = str(mig_dir / filename)

        # Write artifact JSON to disk
        artifact_path = Path(artifact.path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with open(artifact_path, "w", encoding="utf-8") as f:
            json.dump(artifact.to_dict(), f, indent=2, default=str)

        # Persist to SQLite
        self._save_to_sqlite(artifact)

        # Persist to LanceDB (Phase 1 only)
        if self._PHASE_1_ENABLED:
            self._add_to_vector(artifact)

        return artifact

    def log_lesson(
        self,
        migration_id: str,
        lesson: LessonContent | dict[str, Any],
        tags: list[str],
        stage: WorkflowStage = WorkflowStage.COMPLETE,
        persona_set: Optional[list[str]] = None,
        decision_context: str = "",
    ) -> str:
        """
        Log a lesson from a migration (Debate Arena output).

        Writes to ArtifactStore + LanceDB after human approval.
        This is called by the reflection crew after Debate Arena.

        Args:
            migration_id: Associated migration ID
            lesson: Lesson content dict or LessonContent model
            tags: ["wix", "portfolio", "gallery", ...]
            stage: Which stage this lesson emerged from
            persona_set: Personas that produced this lesson
            decision_context: Brief description of the decision situation

        Returns:
            artifact_id
        """
        if isinstance(lesson, dict):
            lesson = LessonContent(**lesson)

        # Serialize lesson content for embedding
        embedding_text = lesson.description
        content_dict = lesson.model_dump()

        artifact_id = str(uuid.uuid4())

        artifact = Artifact(
            id=artifact_id,
            migration_id=migration_id,
            stage=stage,
            persona_set=persona_set or [],
            decision_context=decision_context,
            artifact_type=ArtifactType.LESSON,
            path=str(self.PERSIST_DIR / migration_id / f"lesson_{artifact_id[:8]}.json"),
            metadata=ArtifactMetadata(
                summary=lesson.description,
                extra=content_dict,
            ),
            tags=tags,
        )

        self.save(artifact)

        # Add to LanceDB if Phase 1
        if self._PHASE_1_ENABLED and self._vector_store is not None:
            self._vector_store.add_artifact(
                artifact_id=artifact_id,
                content=content_dict,
                artifact_type="lesson",
                tags=tags,
                migration_id=migration_id,
                embedding_text=embedding_text,
            )

        return artifact_id

    def promote_from_scratch(
        self,
        session_id: str,
        migration_id: str,
        stage: WorkflowStage,
        persona_set: list[str],
        decision_context: str,
        artifact_type: ArtifactType,
        files: list[str],
        tags: Optional[list[str]] = None,
        metadata_extra: Optional[dict[str, Any]] = None,
    ) -> list[Artifact]:
        """
        Move artifacts from scratch directory to persisted directory.

        Called after a Kilo run completes. Copies files from
        .kilo/artifacts/<session>/ to memory/artifacts/<migration_id>/
        and writes them to SQLite with full provenance.

        Args:
            session_id: The Kilo session ID (used to find scratch files)
            migration_id: Target migration ID
            stage: Workflow stage that produced these artifacts
            persona_set: Personas invoked in this run
            decision_context: Brief decision summary
            artifact_type: Type of all artifacts being promoted
            files: List of filenames in scratch dir to promote
            tags: Optional tags to apply
            metadata_extra: Optional extra metadata to merge in

        Returns:
            List of persisted Artifact records
        """
        scratch_session_dir = self.SCRATCH_DIR / session_id
        persist_migration_dir = self.PERSIST_DIR / migration_id

        if not scratch_session_dir.exists():
            return []

        persisted: list[Artifact] = []

        for filename in files:
            scratch_file = scratch_session_dir / filename
            if not scratch_file.exists():
                continue

            # Generate target path
            persist_migration_dir.mkdir(parents=True, exist_ok=True)
            target_file = persist_migration_dir / filename

            # Copy file to persisted location
            shutil.copy2(scratch_file, target_file)

            # Build metadata
            metadata = ArtifactMetadata(
                original_filename=filename,
                files_created=[str(target_file)],
            )
            if metadata_extra:
                metadata.extra.update(metadata_extra)

            # Build artifact record
            artifact_id = str(uuid.uuid4())
            artifact = Artifact(
                id=artifact_id,
                migration_id=migration_id,
                stage=stage,
                persona_set=persona_set,
                decision_context=decision_context,
                artifact_type=artifact_type,
                path=str(target_file),
                metadata=metadata,
                tags=tags or [],
                scratch_source=str(scratch_file),
            )

            # Persist to SQLite + LanceDB
            self._save_to_sqlite(artifact)

            if self._PHASE_1_ENABLED and self._vector_store is not None:
                # For promoted files, we embed file content text
                try:
                    content_text = target_file.read_text(encoding="utf-8")[:4000]
                except Exception:
                    content_text = str(target_file)
                self._vector_store.add_artifact(
                    artifact_id=artifact_id,
                    content={"promoted_file": filename, "migration_id": migration_id},
                    artifact_type=artifact_type.value,
                    tags=tags or [],
                    migration_id=migration_id,
                    embedding_text=content_text,
                )

            persisted.append(artifact)

        return persisted

    # -----------------------------------------------------------------------
    # Public API — Query
    # -----------------------------------------------------------------------

    def query_by_migration(
        self,
        migration_id: str,
        artifact_type: Optional[ArtifactType] = None,
        stage: Optional[WorkflowStage] = None,
        tag: Optional[str] = None,
        limit: int = 20,
    ) -> list[Artifact]:
        """
        Query artifacts by migration ID.

        Phase 0: Returns SQLite results only.
        Phase 1+: Also returns LanceDB semantic matches (with SQLite as primary).
        """
        rows = self._query_sqlite(
            migration_id=migration_id,
            artifact_type=artifact_type,
            stage=stage,
            tag=tag,
            limit=limit,
        )
        return [self._row_to_artifact(row) for row in rows]

    def query_by_persona(
        self,
        persona: str,
        limit: int = 20,
    ) -> list[Artifact]:
        """Query artifacts by persona in persona_set."""
        rows = self._query_sqlite(persona=persona, limit=limit)
        return [self._row_to_artifact(row) for row in rows]

    def query_by_type(
        self,
        artifact_type: ArtifactType,
        limit: int = 20,
    ) -> list[Artifact]:
        """Query artifacts by type."""
        rows = self._query_sqlite(artifact_type=artifact_type, limit=limit)
        return [self._row_to_artifact(row) for row in rows]

    def query_by_tag(
        self,
        tag: str,
        limit: int = 20,
    ) -> list[Artifact]:
        """Query artifacts that have a specific tag."""
        rows = self._query_sqlite(tag=tag, limit=limit)
        return [self._row_to_artifact(row) for row in rows]

    def query_by_stage(
        self,
        stage: WorkflowStage,
        migration_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[Artifact]:
        """Query artifacts by workflow stage."""
        rows = self._query_sqlite(stage=stage, migration_id=migration_id, limit=limit)
        return [self._row_to_artifact(row) for row in rows]

    def get_recent(
        self,
        limit: int = 20,
        artifact_type: Optional[ArtifactType] = None,
    ) -> list[Artifact]:
        """Get most recently created artifacts."""
        rows = self._query_sqlite(artifact_type=artifact_type, limit=limit, order_by="created_at DESC")
        return [self._row_to_artifact(row) for row in rows]

    def get_by_id(self, artifact_id: str) -> Optional[Artifact]:
        """Get a single artifact by ID."""
        import sqlite3
        table_name = "artifacts"
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                f"SELECT * FROM {table_name} WHERE id = ?",
                (artifact_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cursor.description]
            d = dict(zip(columns, row))
            return self._row_to_artifact(d)
        finally:
            conn.close()

    def query_similar(
        self,
        query: str,
        tags: Optional[list[str]] = None,
        artifact_types: Optional[list[str]] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Semantic search over lessons + site summaries.

        Phase 0: Returns empty list (LanceDB not available).
        Phase 1+: Searches LanceDB collection "elyra_artifacts".
        """
        if not self._PHASE_1_ENABLED:
            return []

        if self._vector_store is None:
            return []

        return self._vector_store.search(
            query=query,
            tags=tags,
            artifact_types=artifact_types,
            limit=limit,
        )

    def list_sessions(self, migration_id: str) -> list[str]:
        """List session IDs that have scratch artifacts for this migration."""
        scratch_mig_dir = self.SCRATCH_DIR / migration_id
        if not scratch_mig_dir.exists():
            return []
        return [d.name for d in scratch_mig_dir.iterdir() if d.is_dir()]

    # -----------------------------------------------------------------------
    # Phase Control
    # -----------------------------------------------------------------------

    @classmethod
    def enable_phase_1(cls) -> None:
        """Enable LanceDB writes. Call this after Phase 1 is activateable."""
        cls._PHASE_1_ENABLED = True

    @classmethod
    def is_phase_1_enabled(cls) -> bool:
        return cls._PHASE_1_ENABLED

    def detect_phase(self) -> int:
        """
        Detect current phase based on enabled features.

        Returns 0 for Phase 0 (LanceDB not available),
               1 for Phase 1 (LanceDB available but disabled for migration).
        """
        if self._is_lancedb_available():
            return 1
        return 0

    # -----------------------------------------------------------------------
    # Private — SQLite helpers
    # -----------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        """Ensure the artifacts schema is loaded into SQLite.

        Handles migration from old schema (without stage/persona_set/decision_context)
        by recreating the table with the new schema if needed.
        """
        schema_path = Path(__file__).parent / "sqlite" / "artifacts.sql"
        if not schema_path.exists():
            schema_path = Path("memory/sqlite/artifacts.sql")

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        try:
            # Check if table exists and has the new schema columns
            cursor = conn.execute("PRAGMA table_info(artifacts)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            # New schema requires these columns
            required_cols = {"stage", "persona_set", "decision_context", "path", "metadata", "scratch_source"}

            if "stage" not in existing_cols:
                # Old schema detected — drop and recreate with new schema
                conn.execute("DROP TABLE IF EXISTS artifacts")
                with open(schema_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
                conn.commit()
            else:
                # New schema already present — just create indexes (IF NOT EXISTS is idempotent)
                with open(schema_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
                conn.commit()
        finally:
            conn.close()

    def _save_to_sqlite(self, artifact: Artifact) -> None:
        """Persist an Artifact to SQLite 'artifacts' table."""
        import sqlite3
        table_name = "artifacts"
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(f"""
                INSERT INTO {table_name} (
                    id, migration_id, stage, persona_set, decision_context,
                    artifact_type, path, metadata, embedding_vector_id, tags,
                    scratch_source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                artifact.id,
                artifact.migration_id,
                artifact.stage.value,
                json.dumps(artifact.persona_set),
                artifact.decision_context,
                artifact.artifact_type.value,
                artifact.path,
                json.dumps(artifact.metadata.model_dump(), default=str),
                artifact.embedding_vector_id,
                json.dumps(artifact.tags),
                artifact.scratch_source,
                artifact.created_at.isoformat(),
            ))
            conn.commit()
        finally:
            conn.close()

    def _query_sqlite(
        self,
        migration_id: Optional[str] = None,
        artifact_type: Optional[ArtifactType] = None,
        stage: Optional[WorkflowStage] = None,
        persona: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 20,
        order_by: str = "created_at DESC",
    ) -> list[dict[str, Any]]:
        """Run a query against the artifacts table."""
        import sqlite3
        table_name = "artifacts"
        conditions = []
        params: list[Any] = []

        if migration_id:
            conditions.append("migration_id = ?")
            params.append(migration_id)
        if artifact_type:
            conditions.append("artifact_type = ?")
            params.append(artifact_type.value)
        if stage:
            conditions.append("stage = ?")
            params.append(stage.value)
        if persona:
            conditions.append("persona_set LIKE ?")
            params.append(f'%"{persona}"%')
        if tag:
            conditions.append("tags LIKE ?")
            params.append(f"%{tag}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
            SELECT id, migration_id, stage, persona_set, decision_context,
                   artifact_type, path, metadata, embedding_vector_id, tags,
                   scratch_source, created_at
            FROM {table_name}
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT ?
        """
        params.append(limit)

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def _row_to_artifact(self, row: dict[str, Any]) -> Artifact:
        """Convert a SQLite row dict to an Artifact model."""
        metadata_dict = self._safe_json_loads(row.get("metadata"))
        tags = self._safe_json_loads(row.get("tags")) or []
        persona_set = self._safe_json_loads(row.get("persona_set")) or []

        created_at_str = row.get("created_at", "")
        if isinstance(created_at_str, str):
            try:
                created_at = datetime.fromisoformat(created_at_str)
            except Exception:
                created_at = datetime.now(timezone.utc)
        else:
            created_at = created_at_str or datetime.now(timezone.utc)

        metadata = ArtifactMetadata(**metadata_dict) if metadata_dict else ArtifactMetadata()

        return Artifact(
            id=row["id"],
            migration_id=row["migration_id"],
            stage=WorkflowStage(row["stage"]),
            persona_set=persona_set,
            decision_context=row.get("decision_context") or "",
            artifact_type=ArtifactType(row["artifact_type"]),
            path=row["path"],
            metadata=metadata,
            embedding_vector_id=row.get("embedding_vector_id"),
            tags=tags,
            scratch_source=row.get("scratch_source"),
            created_at=created_at,
        )

    def _safe_json_loads(self, value: Any) -> Any:
        """Safely parse a JSON string."""
        if not value:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return None
        return value

    # -----------------------------------------------------------------------
    # Private — LanceDB helpers (Phase 1)
    # -----------------------------------------------------------------------

    def _is_lancedb_available(self) -> bool:
        """Check if LanceDB and sentence-transformers are available."""
        try:
            import lancedb
            import sentence_transformers
            return True
        except ImportError:
            return False

    def _get_vector_store(self) -> Optional[VectorStoreProxy]:
        """Lazily create the VectorStoreProxy."""
        if self._vector_store is not None:
            return self._vector_store

        if not self._is_lancedb_available():
            return None

        try:
            self._vector_store = VectorStoreProxy(
                db_path="memory/vector/lancedb_data",
                collection="elyra_artifacts",
            )
            return self._vector_store
        except Exception:
            return None

    def _add_to_vector(self, artifact: Artifact) -> None:
        """Add an artifact to the LanceDB vector store."""
        vs = self._get_vector_store()
        if vs is None:
            return

        embedding_text = artifact.metadata.summary or ""
        content_dict = artifact.metadata.extra

        vs.add_artifact(
            artifact_id=artifact.id,
            content=content_dict,
            artifact_type=artifact.artifact_type.value,
            tags=artifact.tags,
            migration_id=artifact.migration_id,
            embedding_text=embedding_text,
        )


# ---------------------------------------------------------------------------
# Vector Store Proxy (Phase 1 LanceDB integration)
# ---------------------------------------------------------------------------

class VectorStoreProxy:
    """
    LanceDB-backed vector store for semantic search.

    Schema:
        - id: unique artifact ID
        - content: JSON string of artifact content
        - content_hash: deterministic hash for dedup
        - embedding: list<float32> (128-dim from all-MiniLM-L6-v2)
        - artifact_type: lesson, anti_pattern, routing_insight, deploy_result, site_summary
        - tags: JSON array
        - migration_id: FK string
        - stage: workflow stage string
        - created_at: ISO timestamp

    Phase 0: This class is never instantiated (graceful degradation).
    Phase 1: Full LanceDB with sentence-transformers embeddings.
    """

    def __init__(self, db_path: str, collection: str = "elyra_artifacts"):
        self.db_path = db_path
        self.collection = collection
        self._client = None
        self._table = None
        self._use_fallback = True

        self._connect()

    def _connect(self) -> None:
        """Try to connect to LanceDB."""
        try:
            import lancedb
            import sentence_transformers

            os.makedirs(self.db_path, exist_ok=True)
            self._db = lancedb.connect(self.db_path)

            # Load or create table
            try:
                self._table = self._db.open_table(self.collection)
            except Exception:
                schema = {
                    "id": "string",
                    "content": "string",
                    "content_hash": "string",
                    "embedding": "list<float32>",
                    "artifact_type": "string",
                    "tags": "string",
                    "migration_id": "string",
                    "stage": "string",
                    "created_at": "string",
                }
                self._table = self._db.create_table(self.collection, schema=schema)

            # Load embedder (blocking for ~1s on first load)
            self._embedder = sentence_transformers.SentenceTransformer(
                "all-MiniLM-L6-v2"
            )

            self._use_fallback = False
        except ImportError:
            self._use_fallback = True
        except Exception:
            self._use_fallback = True

    def _compute_embedding(self, text: str) -> list[float]:
        """Compute embedding vector using sentence-transformers."""
        if self._use_fallback:
            return self._simple_embedding(text)

        import numpy as np
        embedding = self._embedder.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def _simple_embedding(self, text: str) -> list[float]:
        """Fallback hash-based embedding for when LanceDB is not available."""
        import hashlib
        embedding = []
        text_lower = text.lower()
        for i in range(128):
            char_val = sum(ord(c) * (i + 1) for c in text_lower[:min(len(text_lower), 64)])
            bucket = (char_val + i * 17) % 100 / 100.0
            embedding.append(bucket)
        norm = sum(x * x for x in embedding) ** 0.5
        if norm > 0:
            embedding = [x / norm for x in embedding]
        return embedding

    def add_artifact(
        self,
        artifact_id: str,
        content: dict[str, Any],
        artifact_type: str,
        tags: list[str],
        migration_id: str,
        stage: str = "",
        embedding_text: Optional[str] = None,
    ) -> None:
        """
        Add an artifact to the vector store.

        Phase 0: Never called (guarded by _PHASE_1_ENABLED).
        Phase 1: Full LanceDB integration.
        """
        import hashlib

        content_str = json.dumps(content, sort_keys=True, default=str)
        content_hash = hashlib.sha256(content_str.encode()).hexdigest()[:16]
        embedding_text = embedding_text or content_str[:500]
        vector = self._compute_embedding(embedding_text)

        if self._use_fallback:
            return

        from datetime import datetime
        self._table.add({
            "id": artifact_id,
            "content": content_str,
            "content_hash": content_hash,
            "embedding": vector,
            "artifact_type": artifact_type,
            "tags": json.dumps(tags),
            "migration_id": migration_id,
            "stage": stage,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    def search(
        self,
        query: str,
        tags: Optional[list[str]] = None,
        artifact_types: Optional[list[str]] = None,
        migration_id: Optional[str] = None,
        stage: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Perform semantic search over artifacts.

        Returns list of dicts with: artifact_id, content, similarity, tags, artifact_type.
        """
        if self._use_fallback:
            return []

        query_vector = self._compute_embedding(query)

        try:
            import pandas as pd
            query_df = pd.DataFrame([{
                "embedding": query_vector,
                "id": "__query__",
            }])
            results = self._table.search(query_df["embedding"]).limit(limit).to_df()
        except Exception:
            return self._fallback_search(query_vector, tags, artifact_types, limit)

        matches = []
        for _, row in results.iterrows():
            row_dict = dict(row)
            content = row_dict.get("content", "{}")
            try:
                content = json.loads(content)
            except Exception:
                pass

            matches.append({
                "artifact_id": row_dict.get("id"),
                "content": content,
                "similarity": row_dict.get("_distance", 0.0),
                "tags": json.loads(row_dict.get("tags", "[]")) if isinstance(row_dict.get("tags"), str) else [],
                "artifact_type": row_dict.get("artifact_type"),
                "migration_id": row_dict.get("migration_id"),
            })

        return matches

    def _fallback_search(
        self,
        query_embedding: list[float],
        tags: Optional[list[str]],
        artifact_types: Optional[list[str]],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fallback when LanceDB is not available."""
        return []


# ---------------------------------------------------------------------------
# Module-level log_lesson (for skills/executable/memory_query.py wiring)
# ---------------------------------------------------------------------------

_artifact_store: Optional[ArtifactStore] = None


def get_artifact_store(db_path: str = "elyra_memory.db") -> ArtifactStore:
    """Get or create the singleton ArtifactStore instance."""
    global _artifact_store
    if _artifact_store is None:
        _artifact_store = ArtifactStore(db_path)
    return _artifact_store


def log_lesson(
    migration_id: str,
    lesson: LessonContent | dict[str, Any],
    tags: list[str],
    stage: WorkflowStage = WorkflowStage.COMPLETE,
    persona_set: Optional[list[str]] = None,
    decision_context: str = "",
) -> str:
    """
    Module-level log_lesson for wiring from reflection crew.

    This is the entry point called by the Debate Arena reflection crew.
    It delegates to ArtifactStore.log_lesson() after human approval.
    """
    store = get_artifact_store()
    return store.log_lesson(
        migration_id=migration_id,
        lesson=lesson,
        tags=tags,
        stage=stage,
        persona_set=persona_set,
        decision_context=decision_context,
    )


# ---------------------------------------------------------------------------
# Main / Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("ArtifactStore v1 — testing schema and basic operations...")

    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = os.path.join(tmpdir, "test_artifact.db")
        store = ArtifactStore(db_path=test_db)

        migration_id = "test-mig-001"
        stage = WorkflowStage.COMPLETE
        persona_set = ["scraper_specialist", "codegen_crew_lead"]
        decision_context = "Wix portfolio migration with gallery component"

        # Save a test artifact
        artifact = Artifact(
            migration_id=migration_id,
            stage=stage,
            persona_set=persona_set,
            decision_context=decision_context,
            artifact_type=ArtifactType.SITE_SUMMARY,
            path=str(store.PERSIST_DIR / migration_id / "site_summary.json"),
            metadata=ArtifactMetadata(
                summary="Test site summary for wix portfolio",
            ),
            tags=["wix", "portfolio", "test"],
        )
        saved = store.save(artifact)
        print(f"  Saved artifact: {saved.id} -> {saved.path}")

        # Query by migration
        results = store.query_by_migration(migration_id)
        print(f"  Query by migration: {len(results)} artifact(s)")

        # Query by type
        results = store.query_by_type(ArtifactType.SITE_SUMMARY)
        print(f"  Query by type: {len(results)} artifact(s)")

        # Query recent
        results = store.get_recent(limit=5)
        print(f"  Get recent: {len(results)} artifact(s)")

        # Log a lesson
        lesson_id = store.log_lesson(
            migration_id=migration_id,
            lesson={
                "description": "Wix portfolio with gallery component migrates well to Next.js + Tailwind",
                "pattern": "gallery",
                "outcome": "success",
            },
            tags=["wix", "portfolio", "gallery", "nextjs"],
            stage=WorkflowStage.COMPLETE,
            persona_set=["scraper_specialist", "codegen_crew_lead"],
            decision_context=decision_context,
        )
        print(f"  Logged lesson: {lesson_id}")

        # Query similar (Phase 0 — should return empty)
        similar = store.query_similar("wix portfolio gallery")
        print(f"  Query similar (Phase 0, should be empty): {len(similar)} result(s)")

        # Detect phase
        phase = store.detect_phase()
        print(f"  Phase detected: {phase}")

        print("\nArtifactStore v1 working correctly.")
