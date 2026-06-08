import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Any


class Database:
    def __init__(self, db_path: str = "elyra_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            with open("memory/sqlite/schema.sql", "r") as f:
                conn.executescript(f.read())
            conn.commit()

    def _row_to_dict(self, row, columns: list[str] = None) -> dict:
        if not row:
            return {}
        if hasattr(row, 'keys'):
            return {key: row[key] for key in row.keys()}
        if isinstance(row, tuple) and columns:
            return dict(zip(columns, row))
        if isinstance(row, tuple):
            return dict(row) if len(row) == 2 and isinstance(row[0], str) else list(row)
        return dict(row) if row else {}

    def _get_columns(self, cursor) -> list[str]:
        return [desc[0] for desc in cursor.description] if cursor.description else []

    def _safe_json_loads(self, value):
        if not value:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None

    def _json_field(self, value) -> str:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value)


class MigrationCRUD:
    def __init__(self, db: Database):
        self.db = db

    def create_migration(self, data: dict) -> str:
        migration_id = data.get("id") or str(uuid.uuid4())
        conn = self.db._get_connection()
        try:
            conn.execute("""
                INSERT INTO migrations (id, url, platform, task_type, stack_chosen,
                                        fidelity_score, routing_used, outcome,
                                        stage_history, fidelity_history, persona_versions,
                                        decisions, site_architecture_id, content_recommendation_id,
                                        production_url, github_repo, preview_url, preview_expires_at,
                                        created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                migration_id,
                data.get("url"),
                data.get("platform"),
                data.get("task_type"),
                self.db._json_field(data.get("stack_chosen")),
                data.get("fidelity_score"),
                self.db._json_field(data.get("routing_used")),
                data.get("outcome"),
                self.db._json_field(data.get("stage_history")),
                self.db._json_field(data.get("fidelity_history")),
                self.db._json_field(data.get("persona_versions")),
                self.db._json_field(data.get("decisions")),
                data.get("site_architecture_id"),
                data.get("content_recommendation_id"),
                data.get("production_url"),
                data.get("github_repo"),
                data.get("preview_url"),
                data.get("preview_expires_at"),
                datetime.now().isoformat()
            ))
            conn.commit()
        finally:
            conn.close()
        return migration_id

    def get_migration(self, migration_id: str) -> Optional[dict]:
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM migrations WHERE id = ?",
                (migration_id,)
            )
            row = cursor.fetchone()
            if row:
                columns = self.db._get_columns(cursor)
                d = self.db._row_to_dict(row, columns)
                d["stack_chosen"] = self.db._safe_json_loads(d.get("stack_chosen"))
                d["routing_used"] = self.db._safe_json_loads(d.get("routing_used"))
                d["stage_history"] = self.db._safe_json_loads(d.get("stage_history"))
                d["fidelity_history"] = self.db._safe_json_loads(d.get("fidelity_history"))
                d["persona_versions"] = self.db._safe_json_loads(d.get("persona_versions"))
                d["decisions"] = self.db._safe_json_loads(d.get("decisions"))
                return d
            return None
        finally:
            conn.close()

    def update_fidelity(self, migration_id: str, fidelity_score: float) -> bool:
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "UPDATE migrations SET fidelity_score = ?, updated_at = ? WHERE id = ?",
                (fidelity_score, datetime.now().isoformat(), migration_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_outcome(self, migration_id: str, outcome: str) -> bool:
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "UPDATE migrations SET outcome = ?, updated_at = ? WHERE id = ?",
                (outcome, datetime.now().isoformat(), migration_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_stage_history(self, migration_id: str, stage: str, metadata: Optional[dict] = None) -> bool:
        """Append a stage transition to the migration's stage_history."""
        conn = self.db._get_connection()
        try:
            cursor = conn.execute("SELECT stage_history FROM migrations WHERE id = ?", (migration_id,))
            row = cursor.fetchone()
            if not row:
                return False
            history = self.db._safe_json_loads(row[0]) or []
            stage_entry = {"stage": stage, "timestamp": datetime.now().isoformat()}
            if metadata:
                stage_entry["metadata"] = metadata
            history.append(stage_entry)
            cursor = conn.execute(
                "UPDATE migrations SET stage_history = ?, updated_at = ? WHERE id = ?",
                (self.db._json_field(history), datetime.now().isoformat(), migration_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_production(self, migration_id: str, production_url: str, github_repo: str) -> bool:
        """Mark migration as production live."""
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                """UPDATE migrations SET outcome = 'success', production_url = ?,
                   github_repo = ?, updated_at = ? WHERE id = ?""",
                (production_url, github_repo, datetime.now().isoformat(), migration_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_preview(self, migration_id: str, preview_url: str, expires_at: datetime) -> bool:
        """Set preview URL with expiration."""
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                """UPDATE migrations SET preview_url = ?, preview_expires_at = ?,
                   updated_at = ? WHERE id = ?""",
                (preview_url, expires_at.isoformat(), datetime.now().isoformat(), migration_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_migrations(self, platform: Optional[str] = None,
                       task_type: Optional[str] = None,
                       limit: int = 20) -> list[dict]:
        conn = self.db._get_connection()
        query = "SELECT * FROM migrations"
        params = []
        where_clauses = []

        if platform:
            where_clauses.append("platform = ?")
            params.append(platform)
        if task_type:
            where_clauses.append("task_type = ?")
            params.append(task_type)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        try:
            cursor = conn.execute(query, params)
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            results = []
            for row in rows:
                d = self.db._row_to_dict(row, columns)
                d["stack_chosen"] = self.db._safe_json_loads(d.get("stack_chosen"))
                d["routing_used"] = self.db._safe_json_loads(d.get("routing_used"))
                d["stage_history"] = self.db._safe_json_loads(d.get("stage_history"))
                d["fidelity_history"] = self.db._safe_json_loads(d.get("fidelity_history"))
                d["persona_versions"] = self.db._safe_json_loads(d.get("persona_versions"))
                d["decisions"] = self.db._safe_json_loads(d.get("decisions"))
                results.append(d)
            return results
        finally:
            conn.close()


class DebateCRUD:
    def __init__(self, db: Database):
        self.db = db

    def create_debate(self, migration_id: str, result: dict) -> str:
        debate_id = str(uuid.uuid4())
        conn = self.db._get_connection()
        try:
            conn.execute("""
                INSERT INTO debate_outputs (id, migration_id, debate_result, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                debate_id,
                migration_id,
                json.dumps(result),
                datetime.now().isoformat()
            ))
            conn.commit()
        finally:
            conn.close()
        return debate_id

    def get_debate(self, debate_id: str) -> Optional[dict]:
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM debate_outputs WHERE id = ?",
                (debate_id,)
            )
            row = cursor.fetchone()
            if row:
                columns = self.db._get_columns(cursor)
                d = self.db._row_to_dict(row, columns)
                d["debate_result"] = self.db._safe_json_loads(d.get("debate_result"))
                d["changes_proposed"] = self.db._safe_json_loads(d.get("changes_proposed"))
                return d
            return None
        finally:
            conn.close()

    def get_debates_for_migration(self, migration_id: str) -> list[dict]:
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM debate_outputs WHERE migration_id = ? ORDER BY created_at DESC",
                (migration_id,)
            )
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            results = []
            for row in rows:
                d = self.db._row_to_dict(row, columns)
                d["debate_result"] = self.db._safe_json_loads(d.get("debate_result"))
                d["changes_proposed"] = self.db._safe_json_loads(d.get("changes_proposed"))
                results.append(d)
            return results
        finally:
            conn.close()

    def approve_debate(self, debate_id: str, approved: bool,
                        changes_proposed: Optional[list] = None) -> bool:
        conn = self.db._get_connection()
        try:
            conn.execute("""
                UPDATE debate_outputs
                SET human_approved = ?, changes_proposed = ?, updated_at = ?
                WHERE id = ?
            """, (
                approved,
                self.db._json_field(changes_proposed),
                datetime.now().isoformat(),
                debate_id
            ))
            conn.commit()
            return True
        finally:
            conn.close()

    def mark_changes_applied(self, debate_id: str) -> bool:
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "UPDATE debate_outputs SET changes_applied = TRUE WHERE id = ?",
                (debate_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


class HeuristicCRUD:
    def __init__(self, db: Database):
        self.db = db

    def get_heuristic(self, platform: str, task_type: str) -> Optional[dict]:
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM routing_heuristics WHERE platform = ? AND task_type = ?",
                (platform, task_type)
            )
            row = cursor.fetchone()
            if row:
                columns = self.db._get_columns(cursor)
                d = self.db._row_to_dict(row, columns)
                d["routing_sequence"] = self.db._safe_json_loads(d.get("routing_sequence"))
                return d
            return None
        finally:
            conn.close()

    def upsert_heuristic(self, platform: str, task_type: str,
                         routing_sequence: list, success: bool,
                         fidelity_score: Optional[float] = None) -> None:
        conn = self.db._get_connection()
        try:
            existing = self.get_heuristic(platform, task_type)
            if existing:
                success_count = existing["success_count"] + (1 if success else 0)
                failure_count = existing["failure_count"] + (0 if success else 1)

                if fidelity_score:
                    old_count = success_count + failure_count - 1
                    if old_count > 0:
                        old_avg = existing["avg_fidelity"] or 0
                        new_avg = (old_avg * old_count + fidelity_score) / (old_count + 1)
                    else:
                        new_avg = fidelity_score
                else:
                    new_avg = existing["avg_fidelity"]

                conn.execute("""
                    UPDATE routing_heuristics
                    SET success_count = ?, failure_count = ?, avg_fidelity = ?,
                        last_updated = ?
                    WHERE platform = ? AND task_type = ?
                """, (
                    success_count, failure_count, new_avg,
                    datetime.now().isoformat(), platform, task_type
                ))
            else:
                conn.execute("""
                    INSERT INTO routing_heuristics
                    (platform, task_type, routing_sequence, success_count,
                     failure_count, avg_fidelity, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    platform, task_type, json.dumps(routing_sequence),
                    1 if success else 0, 0 if success else 1,
                    fidelity_score, datetime.now().isoformat()
                ))
            conn.commit()
        finally:
            conn.close()


class SessionStateCRUD:
    def __init__(self, db: Database):
        self.db = db

    def save_session(self, session_id: str, state_data: dict,
                     current_phase: str, completed_steps: list) -> None:
        conn = self.db._get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO session_state
                (session_id, state_data, current_phase, completed_steps,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                json.dumps(state_data),
                current_phase,
                json.dumps(completed_steps),
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            conn.commit()
        finally:
            conn.close()

    def load_session(self, session_id: str) -> Optional[dict]:
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM session_state WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            if row:
                columns = self.db._get_columns(cursor)
                d = self.db._row_to_dict(row, columns)
                d["state_data"] = self.db._safe_json_loads(d.get("state_data")) or {}
                d["completed_steps"] = self.db._safe_json_loads(d.get("completed_steps")) or []
                return d
            return None
        finally:
            conn.close()

    def delete_session(self, session_id: str) -> bool:
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM session_state WHERE session_id = ?",
                (session_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


class ArtifactCRUD:
    """CRUD operations for the artifacts table with mandatory provenance."""

    def __init__(self, db: Database):
        self.db = db

    def _init_schema(self) -> None:
        """Ensure the artifacts schema is loaded."""
        schema_path = Path(__file__).parent / "artifacts.sql"
        if not schema_path.exists():
            return
        with self.db._get_connection() as conn:
            with open(schema_path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.commit()

    def save_artifact(
        self,
        artifact_id: str,
        migration_id: str,
        stage: str,
        persona_set: list[str],
        decision_context: str,
        artifact_type: str,
        path: str,
        metadata: Optional[dict] = None,
        embedding_vector_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
        scratch_source: Optional[str] = None,
    ) -> str:
        """Save an artifact with full provenance."""
        conn = self.db._get_connection()
        try:
            conn.execute("""
                INSERT INTO artifacts (
                    id, migration_id, stage, persona_set, decision_context,
                    artifact_type, path, metadata, embedding_vector_id, tags,
                    scratch_source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                artifact_id,
                migration_id,
                stage,
                json.dumps(persona_set),
                decision_context,
                artifact_type,
                path,
                json.dumps(metadata or {}, default=str),
                embedding_vector_id,
                json.dumps(tags or []),
                scratch_source,
                datetime.now().isoformat(),
            ))
            conn.commit()
        finally:
            conn.close()
        return artifact_id

    def get_artifact(self, artifact_id: str) -> Optional[dict]:
        """Get a single artifact by ID."""
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE id = ?",
                (artifact_id,)
            )
            row = cursor.fetchone()
            if row:
                columns = self.db._get_columns(cursor)
                d = self.db._row_to_dict(row, columns)
                return self._deserialize_artifact(d)
            return None
        finally:
            conn.close()

    def query_by_migration(
        self,
        migration_id: str,
        artifact_type: Optional[str] = None,
        stage: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """Query artifacts by migration ID."""
        conditions = ["migration_id = ?"]
        params: list[Any] = [migration_id]

        if artifact_type:
            conditions.append("artifact_type = ?")
            params.append(artifact_type)
        if stage:
            conditions.append("stage = ?")
            params.append(stage)
        if tag:
            conditions.append("tags LIKE ?")
            params.append(f'%"{tag}"%')

        query = f"""
            SELECT * FROM artifacts
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC LIMIT ?
        """
        params.append(limit)

        conn = self.db._get_connection()
        try:
            cursor = conn.execute(query, params)
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            return [self._deserialize_artifact(self.db._row_to_dict(row, columns)) for row in rows]
        finally:
            conn.close()

    def query_by_persona(self, persona: str, limit: int = 20) -> list[dict]:
        """Query artifacts by persona in persona_set."""
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE persona_set LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f'%"{persona}"%', limit)
            )
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            return [self._deserialize_artifact(self.db._row_to_dict(row, columns)) for row in rows]
        finally:
            conn.close()

    def query_by_type(self, artifact_type: str, limit: int = 20) -> list[dict]:
        """Query artifacts by type."""
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE artifact_type = ? ORDER BY created_at DESC LIMIT ?",
                (artifact_type, limit)
            )
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            return [self._deserialize_artifact(self.db._row_to_dict(row, columns)) for row in rows]
        finally:
            conn.close()

    def query_by_tag(self, tag: str, limit: int = 20) -> list[dict]:
        """Query artifacts that have a specific tag."""
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE tags LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f'%"{tag}"%', limit)
            )
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            return [self._deserialize_artifact(self.db._row_to_dict(row, columns)) for row in rows]
        finally:
            conn.close()

    def query_by_stage(self, stage: str, migration_id: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Query artifacts by stage."""
        conn = self.db._get_connection()
        try:
            if migration_id:
                cursor = conn.execute(
                    "SELECT * FROM artifacts WHERE stage = ? AND migration_id = ? ORDER BY created_at DESC LIMIT ?",
                    (stage, migration_id, limit)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM artifacts WHERE stage = ? ORDER BY created_at DESC LIMIT ?",
                    (stage, limit)
                )
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            return [self._deserialize_artifact(self.db._row_to_dict(row, columns)) for row in rows]
        finally:
            conn.close()

    def get_recent(self, limit: int = 20, artifact_type: Optional[str] = None) -> list[dict]:
        """Get most recently created artifacts."""
        conn = self.db._get_connection()
        try:
            if artifact_type:
                cursor = conn.execute(
                    "SELECT * FROM artifacts WHERE artifact_type = ? ORDER BY created_at DESC LIMIT ?",
                    (artifact_type, limit)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM artifacts ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            columns = self.db._get_columns(cursor)
            rows = cursor.fetchall()
            return [self._deserialize_artifact(self.db._row_to_dict(row, columns)) for row in rows]
        finally:
            conn.close()

    def _deserialize_artifact(self, d: dict) -> dict:
        """Deserialize JSON fields in an artifact row."""
        d["persona_set"] = self.db._safe_json_loads(d.get("persona_set")) or []
        d["tags"] = self.db._safe_json_loads(d.get("tags")) or []
        d["metadata"] = self.db._safe_json_loads(d.get("metadata")) or {}
        return d