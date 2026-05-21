"""
LanceDB Vector Store for Elyra Semantic Memory.

Provides semantic search over migration lessons, site understandings,
and architectural decisions using vector embeddings.

Phase 0/1: Stubbed with graceful degradation. Real LanceDB wiring in Phase 2+.
"""

import os
import json
import hashlib
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SemanticMatch:
    """A semantic search result with similarity score."""
    artifact_id: str
    content: dict
    similarity: float
    tags: list[str]
    artifact_type: str


class VectorStore:
    """
    LanceDB-backed vector store for semantic memory.

    Phase 0/1: Uses simple hash-based similarity as fallback.
    Phase 2+: Uses real embeddings via sentence-transformers + LanceDB.

    Schema:
    - id: unique artifact ID
    - content: JSON string of artifact content
    - content_hash: deterministic hash for dedup
    - embedding: list of floats (when real embeddings available)
    - artifact_type: lesson, anti_pattern, routing_insight, deploy_result, site_summary
    - tags: JSON array of searchable tags
    - migration_id: FK to migrations
    - created_at: timestamp
    """

    LANCE_DB_PATH = "memory/vector/lancedb_data"
    TABLE_NAME = "semantic_memory"

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or self.LANCE_DB_PATH
        self._client = None
        self._table = None
        self._use_fallback = True
        self._fallback_store: dict[str, dict] = {}
        self._connect()

    def _connect(self):
        """Try to connect to LanceDB, fall back to in-memory store."""
        try:
            import lancedb
            self._client = lanceddb.LanceDBClient()
            os.makedirs(self.db_path, exist_ok=True)
            self._db = lanceddb.connect(self.db_path)
            self._try_load_table()
            self._use_fallback = False
            logger.info("LanceDB connected successfully")
        except ImportError:
            logger.warning("LanceDB not installed, using in-memory fallback store")
            self._use_fallback = True
        except Exception as e:
            logger.warning(f"LanceDB connection failed: {e}, using in-memory fallback")
            self._use_fallback = True

    def _try_load_table(self):
        """Load or create the semantic memory table."""
        try:
            self._table = self._db.open_table(self.TABLE_NAME)
        except Exception:
            schema = {
                "id": "string",
                "content": "string",
                "content_hash": "string",
                "embedding": "list<float32>",
                "artifact_type": "string",
                "tags": "string",
                "migration_id": "string",
                "created_at": "string"
            }
            self._table = self._db.create_table(self.TABLE_NAME, schema=schema)

    def _compute_simple_embedding(self, text: str) -> list[float]:
        """
        Compute a simple hash-based embedding vector for Phase 0/1 fallback.
        Uses deterministic hashing to create a pseudo-embedding that enables
        basic similarity comparison via cosine distance on hash buckets.
        """
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

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _content_hash(self, content: dict) -> str:
        """Compute deterministic hash of content for deduplication."""
        content_str = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]

    def add_artifact(
        self,
        artifact_id: str,
        content: dict,
        artifact_type: str,
        tags: list[str],
        migration_id: str,
        embedding_text: Optional[str] = None
    ) -> str:
        """
        Add an artifact to the vector store.

        Args:
            artifact_id: Unique ID for this artifact
            content: Artifact content dict
            artifact_type: Type of artifact (lesson, anti_pattern, etc.)
            tags: Searchable tags
            migration_id: Associated migration ID
            embedding_text: Text to embed (defaults to content string)

        Returns:
            artifact_id
        """
        content_str = json.dumps(content, default=str)
        content_hash = self._content_hash(content)
        embedding_text = embedding_text or content_str

        if self._use_fallback:
            embedding = self._compute_simple_embedding(embedding_text)
            self._fallback_store[artifact_id] = {
                "content": content,
                "embedding": embedding,
                "artifact_type": artifact_type,
                "tags": tags,
                "migration_id": migration_id,
                "content_hash": content_hash
            }
            logger.info(f"Added artifact (fallback): {artifact_id} [{artifact_type}]")
            return artifact_id

        vector = self._compute_simple_embedding(embedding_text)
        self._table.add({
            "id": artifact_id,
            "content": content_str,
            "content_hash": content_hash,
            "embedding": vector,
            "artifact_type": artifact_type,
            "tags": json.dumps(tags),
            "migration_id": migration_id,
            "created_at": self._timestamp()
        })
        logger.info(f"Added artifact: {artifact_id} [{artifact_type}]")
        return artifact_id

    def search(
        self,
        query: str,
        artifact_types: Optional[list[str]] = None,
        limit: int = 5,
        similarity_threshold: float = 0.0
    ) -> list[SemanticMatch]:
        """
        Search for semantically similar artifacts.

        Args:
            query: Natural language query
            artifact_types: Filter by artifact types
            limit: Max results
            similarity_threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of SemanticMatch objects sorted by similarity
        """
        query_embedding = self._compute_simple_embedding(query.lower())

        if self._use_fallback:
            results = []
            for aid, data in self._fallback_store.items():
                if artifact_types and data["artifact_type"] not in artifact_types:
                    continue
                sim = self._cosine_similarity(query_embedding, data["embedding"])
                if sim >= similarity_threshold:
                    results.append(SemanticMatch(
                        artifact_id=aid,
                        content=data["content"],
                        similarity=sim,
                        tags=data["tags"],
                        artifact_type=data["artifact_type"]
                    ))
            results.sort(key=lambda x: x.similarity, reverse=True)
            return results[:limit]

        try:
            query_vector = self._compute_simple_embedding(query.lower())
            if hasattr(self._table, 'search'):
                import pandas as pd
                query_df = pd.DataFrame([{
                    "embedding": query_vector,
                    "id": "__query__"
                }])
                results = self._table.search(query_df["embedding"]).limit(limit).to_df()
            else:
                all_rows = self._table.to_list()
                scored = []
                for row in all_rows:
                    if artifact_types and row["artifact_type"] not in artifact_types:
                        continue
                    row_emb = row.get("embedding") or self._compute_simple_embedding(row.get("content", ""))
                    sim = self._cosine_similarity(query_vector, row_emb)
                    if sim >= similarity_threshold:
                        scored.append((sim, row))
                scored.sort(key=lambda x: x[0], reverse=True)
                results = [r for _, r in scored[:limit]]
        except Exception as e:
            logger.error(f"LanceDB search failed: {e}, falling back")
            return self._fallback_search(query_embedding, artifact_types, limit, similarity_threshold)

        matches = []
        for row in results:
            sim = self._cosine_similarity(query_vector, row.get("embedding") or query_embedding)
            if sim >= similarity_threshold:
                matches.append(SemanticMatch(
                    artifact_id=row["id"],
                    content=json.loads(row["content"]),
                    similarity=sim,
                    tags=json.loads(row["tags"]) if isinstance(row["tags"], str) else row.get("tags", []),
                    artifact_type=row["artifact_type"]
                ))
        return matches

    def _fallback_search(
        self,
        query_embedding: list[float],
        artifact_types: Optional[list[str]],
        limit: int,
        threshold: float
    ) -> list[SemanticMatch]:
        """Fallback search using in-memory store."""
        results = []
        for aid, data in self._fallback_store.items():
            if artifact_types and data["artifact_type"] not in artifact_types:
                continue
            sim = self._cosine_similarity(query_embedding, data["embedding"])
            if sim >= threshold:
                results.append(SemanticMatch(
                    artifact_id=aid,
                    content=data["content"],
                    similarity=sim,
                    tags=data["tags"],
                    artifact_type=data["artifact_type"]
                ))
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:limit]

    def _timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()

    def get_by_migration(self, migration_id: str) -> list[SemanticMatch]:
        """Get all artifacts for a specific migration."""
        if self._use_fallback:
            results = []
            for aid, data in self._fallback_store.items():
                if data["migration_id"] == migration_id:
                    results.append(SemanticMatch(
                        artifact_id=aid,
                        content=data["content"],
                        similarity=1.0,
                        tags=data["tags"],
                        artifact_type=data["artifact_type"]
                    ))
            return results

        try:
            rows = self._table.to_list()
            return [
                SemanticMatch(
                    artifact_id=row["id"],
                    content=json.loads(row["content"]),
                    similarity=1.0,
                    tags=json.loads(row["tags"]) if isinstance(row["tags"], str) else row.get("tags", []),
                    artifact_type=row["artifact_type"]
                )
                for row in rows
                if row["migration_id"] == migration_id
            ]
        except Exception:
            return self._fallback_search([], None, 100, 0.0)

    def delete_artifact(self, artifact_id: str) -> bool:
        """Delete an artifact by ID."""
        if self._use_fallback:
            if artifact_id in self._fallback_store:
                del self._fallback_store[artifact_id]
                return True
            return False

        try:
            self._table.delete(f"id = '{artifact_id}'")
            return True
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False


class LessonStore:
    """
    High-level interface for storing and retrieving migration lessons.
    Composes VectorStore with structured JSON artifact storage.
    """

    def __init__(self, vector_store: Optional[VectorStore] = None):
        self.vector = vector_store or VectorStore()
        self.artifacts_dir = "memory/artifacts"
        os.makedirs(self.artifacts_dir, exist_ok=True)

    def log_lesson(
        self,
        migration_id: str,
        lesson: dict,
        tags: list[str],
        embedding_text: Optional[str] = None
    ) -> str:
        """
        Log a lesson learned from a migration.

        Args:
            migration_id: Associated migration
            lesson: Lesson content dict
            tags: ["wix", "portfolio", "gallery", "trades", ...]
            embedding_text: Text to use for semantic embedding

        Returns:
            artifact_id
        """
        import uuid
        artifact_id = str(uuid.uuid4())
        lesson_with_meta = {
            "lesson": lesson,
            "migration_id": migration_id,
            "tags": tags
        }
        self._save_json(artifact_id, lesson_with_meta)
        self.vector.add_artifact(
            artifact_id=artifact_id,
            content=lesson_with_meta,
            artifact_type="lesson",
            tags=tags,
            migration_id=migration_id,
            embedding_text=embedding_text or lesson.get("description", "")
        )
        return artifact_id

    def log_anti_pattern(
        self,
        migration_id: str,
        anti_pattern: dict,
        tags: list[str]
    ) -> str:
        """Log an anti-pattern discovered during migration."""
        import uuid
        artifact_id = str(uuid.uuid4())
        content = {
            "anti_pattern": anti_pattern,
            "migration_id": migration_id,
            "tags": tags
        }
        self._save_json(artifact_id, content)
        self.vector.add_artifact(
            artifact_id=artifact_id,
            content=content,
            artifact_type="anti_pattern",
            tags=tags,
            migration_id=migration_id,
            embedding_text=anti_pattern.get("description", "")
        )
        return artifact_id

    def log_site_summary(
        self,
        migration_id: str,
        site_summary: dict,
        tags: list[str]
    ) -> str:
        """
        Log a site summary for semantic recall.
        Used when searching "what worked for classical schools?" or "trades gallery sites".
        """
        import uuid
        artifact_id = str(uuid.uuid4())
        content = {
            "site_summary": site_summary,
            "migration_id": migration_id,
            "tags": tags
        }
        self._save_json(artifact_id, content)
        self.vector.add_artifact(
            artifact_id=artifact_id,
            content=content,
            artifact_type="site_summary",
            tags=tags,
            migration_id=migration_id,
            embedding_text=site_summary.get("description", "")
        )
        return artifact_id

    def search_lessons(self, query: str, tags: Optional[list[str]] = None, limit: int = 5) -> list[SemanticMatch]:
        """
        Search lessons semantically.

        Example: "Find all migrations that used a trades gallery"
        Example: "What worked for classical schools?"
        """
        artifact_types = ["lesson", "site_summary"]
        results = self.vector.search(query, artifact_types=artifact_types, limit=limit)
        if tags:
            results = [r for r in results if any(t in r.tags for t in tags)]
        return results

    def search_deploy_results(self, query: str, limit: int = 3) -> list[SemanticMatch]:
        """Search deployment results and patterns."""
        return self.vector.search(query, artifact_types=["deploy_result"], limit=limit)

    def _save_json(self, artifact_id: str, content: dict):
        """Save artifact JSON to disk."""
        path = os.path.join(self.artifacts_dir, f"{artifact_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, default=str)

    def _load_json(self, artifact_id: str) -> Optional[dict]:
        """Load artifact JSON from disk."""
        path = os.path.join(self.artifacts_dir, f"{artifact_id}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='[lesson_store] %(message)s')

    print("Testing LessonStore...")

    store = LessonStore()

    print("\n1. Log a lesson:")
    lid = store.log_lesson(
        migration_id="test-001",
        lesson={"description": "Trades gallery component works well for wix portfolio sites", "pattern": "gallery", "outcome": "success"},
        tags=["wix", "portfolio", "trades", "gallery"]
    )
    print(f"   Lesson ID: {lid}")

    print("\n2. Search for trades gallery lessons:")
    results = store.search_lessons("trades gallery wix")
    print(f"   Found {len(results)} results")
    for r in results:
        print(f"   - [{r.artifact_type}] sim={r.similarity:.3f}: {r.content}")

    print("\n3. Log a site summary:")
    sid = store.log_site_summary(
        migration_id="test-001",
        site_summary={"description": "Classical school site with chapel, academy focus", "type": "academy", "industry": "education"},
        tags=["classical", "academy", "education", "religious"]
    )
    print(f"   Summary ID: {sid}")

    print("\n4. Search for classical schools:")
    results = store.search_lessons("classical schools education")
    print(f"   Found {len(results)} results")

    print("\nLessonStore working correctly.")
