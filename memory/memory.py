from memory.sqlite.crud import Database, MigrationCRUD, DebateCRUD, HeuristicCRUD, SessionStateCRUD
from skills.executable.memory_query import query_similar_sites, log_migration
from typing import Optional


class Memory:
    def __init__(self, db_path: str = "elyra_memory.db"):
        self.db = Database(db_path)
        self.migrations = MigrationCRUD(self.db)
        self.debates = DebateCRUD(self.db)
        self.heuristics = HeuristicCRUD(self.db)
        self.sessions = SessionStateCRUD(self.db)

    def query_similar_sites(self, platform: str, task_type: str) -> list[dict]:
        """
        Query memory for similar past migrations.

        Phase 0: Returns empty list (LanceDB not wired yet)
        Phase 1+: Will perform vector similarity search

        Args:
            platform: wix, squarespace, wordpress, generic
            task_type: e-commerce, blog, portfolio, business, generic

        Returns:
            List of similar migrations with routing sequences and outcomes
        """
        return query_similar_sites(platform, task_type)

    def save_migration(self, migration_data: dict) -> str:
        """
        Save a completed migration to memory.

        Args:
            migration_data: Dict containing migration details

        Returns:
            migration_id
        """
        migration_id = self.migrations.create_migration(migration_data)
        log_migration(migration_data)
        return migration_id

    def get_migration(self, migration_id: str) -> Optional[dict]:
        """Get a migration by ID."""
        return self.migrations.get_migration(migration_id)

    def update_migration_fidelity(self, migration_id: str, fidelity_score: float) -> None:
        """Update fidelity score for a migration."""
        self.migrations.update_fidelity(migration_id, fidelity_score)

    def list_recent_migrations(self, platform: Optional[str] = None,
                               task_type: Optional[str] = None,
                               limit: int = 20) -> list[dict]:
        """List recent migrations, optionally filtered."""
        return self.migrations.list_migrations(platform, task_type, limit)

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