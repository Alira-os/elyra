from memory.sqlite.crud import Database, MigrationCRUD, DebateCRUD, HeuristicCRUD, SessionStateCRUD
from memory.vector.lessons import LessonStore, SemanticMatch
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MutationSeed:
    """Memory-derived context injected into OpenCode prompts for biasing codegen toward proven patterns."""
    similar_sites_count: int
    winning_stack: str
    average_fidelity: float
    preferred_patterns: list[str]
    anti_patterns: list[str]
    source_migrations: list[str]

    def to_prompt_section(self) -> str:
        """Convert to markdown section for OpenCode prompt."""
        return f"""## Memory-Derived Guidance (Mutation Seed)
Based on {self.similar_sites_count} similar migrations with avg fidelity {self.average_fidelity:.2f}:
- Preferred stack: {self.winning_stack}
- Successful patterns: {', '.join(self.preferred_patterns) if self.preferred_patterns else 'none identified'}
- Avoid: {', '.join(self.anti_patterns) if self.anti_patterns else 'none identified'}

Use this guidance unless user explicitly specifies otherwise."""


class Memory:
    def __init__(self, db_path: str = "elyra_memory.db"):
        self.db = Database(db_path)
        self.migrations = MigrationCRUD(self.db)
        self.debates = DebateCRUD(self.db)
        self.heuristics = HeuristicCRUD(self.db)
        self.sessions = SessionStateCRUD(self.db)
        self.lessons = LessonStore()

    def query_similar_sites(self, platform: str, task_type: str) -> list[dict]:
        """
        Query memory for similar past migrations.

        Phase 1+: Uses LanceDB for semantic similarity search.

        Args:
            platform: wix, squarespace, wordpress, generic
            task_type: e-commerce, blog, portfolio, business, generic

        Returns:
            List of similar migrations with routing sequences and outcomes
        """
        query = f"{platform} {task_type} site migration"
        results = self.lessons.search_lessons(query, tags=[platform, task_type], limit=5)
        migrations = []
        for r in results:
            content = r.content
            if "migration_id" in content:
                mig = self.migrations.get_migration(content["migration_id"])
                if mig:
                    mig["_lesson_similarity"] = r.similarity
                    migrations.append(mig)
        return migrations

    def query_lessons(self, query: str, tags: Optional[list[str]] = None, limit: int = 5) -> list[SemanticMatch]:
        """
        Semantic search over migration lessons.

        Example: "Find all migrations that used a trades gallery"
        Example: "What worked for classical schools?"
        """
        return self.lessons.search_lessons(query, tags=tags, limit=limit)

    def save_migration(self, migration_data: dict) -> str:
        """
        Save a completed migration to memory.

        Args:
            migration_data: Dict containing migration details

        Returns:
            migration_id
        """
        migration_id = self.migrations.create_migration(migration_data)
        self.lessons.log_site_summary(
            migration_id=migration_id,
            site_summary={
                "url": migration_data.get("url", ""),
                "platform": migration_data.get("platform", ""),
                "task_type": migration_data.get("task_type", ""),
                "description": f"{migration_data.get('platform')} {migration_data.get('task_type')} migration"
            },
            tags=[migration_data.get("platform", ""), migration_data.get("task_type", "")]
        )
        return migration_id

    def get_migration(self, migration_id: str) -> Optional[dict]:
        """Get a migration by ID."""
        return self.migrations.get_migration(migration_id)

    def update_migration_fidelity(self, migration_id: str, fidelity_score: float) -> None:
        """Update fidelity score for a migration."""
        self.migrations.update_fidelity(migration_id, fidelity_score)

    def update_stage_history(self, migration_id: str, stage: str, metadata: Optional[dict] = None) -> None:
        """Append a stage transition to the migration's stage_history."""
        self.migrations.update_stage_history(migration_id, stage, metadata)

    def update_preview_url(self, migration_id: str, preview_url: str, expires_at: datetime) -> None:
        """Set preview URL with expiration for a migration."""
        self.migrations.update_preview(migration_id, preview_url, expires_at)

    def mark_production_live(self, migration_id: str, production_url: str, github_repo: str) -> None:
        """Mark migration as production live."""
        self.migrations.update_production(migration_id, production_url, github_repo)

    def list_recent_migrations(self, platform: Optional[str] = None,
                               task_type: Optional[str] = None,
                               limit: int = 20) -> list[dict]:
        """List recent migrations, optionally filtered."""
        return self.migrations.list_migrations(platform, task_type, limit)

    def get_mutation_seed(self, task_context: dict) -> Optional[MutationSeed]:
        """
        Get memory-derived "mutation seed" for biasing codegen.

        Queries similar past migrations and extracts patterns that worked.
        If no similar migrations exist, returns None (no injection).

        Args:
            task_context: Dict with 'platform', 'task_type', 'url', etc.

        Returns:
            MutationSeed or None
        """
        platform = task_context.get("platform", "generic")
        task_type = task_context.get("task_type", "generic")

        similar = self.list_recent_migrations(platform, task_type, limit=5)

        if not similar:
            return None

        successful = [m for m in similar if m.get("outcome") == "success"]
        if not successful:
            return None

        stacks = [m.get("stack_chosen") for m in successful if m.get("stack_chosen")]
        stack_counts = {}
        for s in stacks:
            if s:
                stack_counts[s] = stack_counts.get(s, 0) + 1

        winning_stack = max(stack_counts, key=stack_counts.get) if stack_counts else "nextjs+tailwind"

        fidelity_scores = [m.get("fidelity_score") for m in successful if m.get("fidelity_score")]
        avg_fidelity = sum(fidelity_scores) / len(fidelity_scores) if fidelity_scores else 0.7

        routing_seqs = [m.get("routing_used") for m in successful if m.get("routing_used")]

        preferred = []
        for seq in routing_seqs:
            if seq and "stack_intelligence" in seq:
                preferred.append("uses stack_intelligence")
            if seq and "ui_polish" in seq:
                preferred.append("includes ui_polish")
            if seq and "seo_optimizer" in seq:
                preferred.append("includes seo_optimizer")

        migration_ids = [m.get("id") for m in successful[:3]]

        return MutationSeed(
            similar_sites_count=len(successful),
            winning_stack=winning_stack,
            average_fidelity=avg_fidelity,
            preferred_patterns=list(set(preferred)) if preferred else [],
            anti_patterns=[],
            source_migrations=migration_ids
        )

    def save_debate(self, migration_id: str, debate_result: dict) -> str:
        """Save a debate output for a migration."""
        return self.debates.create_debate(migration_id, debate_result)

    def get_debate(self, debate_id: str) -> Optional[dict]:
        """Get a debate by ID."""
        return self.debates.get_debate(debate_id)

    def approve_debate(self, debate_id: str, approved: bool,
                       changes_proposed: Optional[list] = None) -> None:
        """Mark a debate as approved by human."""
        self.debates.approve_debate(debate_id, approved, changes_proposed)

    def get_heuristic(self, platform: str, task_type: str) -> Optional[dict]:
        """Get routing heuristic for platform + task_type."""
        return self.heuristics.get_heuristic(platform, task_type)

    def update_heuristic(self, platform: str, task_type: str,
                         routing_sequence: list, success: bool,
                         fidelity_score: Optional[float] = None) -> None:
        """Update routing heuristic based on migration result."""
        self.heuristics.upsert_heuristic(platform, task_type, routing_sequence, success, fidelity_score)

    def checkpoint_session(self, session_id: str, state_data: dict,
                           current_phase: str, completed_steps: list) -> None:
        """Save session checkpoint for crash recovery."""
        self.sessions.save_session(session_id, state_data, current_phase, completed_steps)

    def load_session(self, session_id: str) -> Optional[dict]:
        """Load session checkpoint."""
        return self.sessions.load_session(session_id)

    def delete_session(self, session_id: str) -> None:
        """Delete session checkpoint after successful completion."""
        self.sessions.delete_session(session_id)


if __name__ == "__main__":
    m = Memory()

    print("Testing Memory layer...")

    print("\n1. Query similar sites (should return empty):")
    result = m.query_similar_sites("wix", "portfolio")
    print(f"   Result: {result}")

    print("\n2. Create a test migration:")
    mid = m.save_migration({
        "id": "test-001",
        "url": "https://example.wixsite.com",
        "platform": "wix",
        "task_type": "portfolio",
        "routing_used": ["onboarding", "scraper", "codegen", "deploy"],
        "fidelity_score": 0.82,
        "outcome": "success"
    })
    print(f"   Migration ID: {mid}")

    print("\n3. Get migration:")
    mig = m.get_migration(mid)
    print(f"   Migration: {mig}")

    print("\n4. List recent migrations:")
    migrations = m.list_recent_migrations()
    print(f"   Count: {len(migrations)}")

    print("\n5. Get heuristic for wix+portfolio:")
    h = m.get_heuristic("wix", "portfolio")
    print(f"   Heuristic: {h}")

    print("\nMemory layer working correctly.")