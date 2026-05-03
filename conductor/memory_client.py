from memory.memory import Memory
from typing import Optional, Any


class MemoryClient:
    """
    Memory layer interface for the Conductor.
    Wraps the Memory class and provides Conductor-specific methods.
    """

    def __init__(self, db_path: str = "elyra_memory.db"):
        self.memory = Memory(db_path)

    def query_for_routing(self, platform: str, task_type: str) -> list[dict]:
        """
        Query memory for similar migrations to inform routing decision.

        Phase 0: Returns empty list
        Phase 1+: Returns similar migrations with routing and outcomes
        """
        return self.memory.query_similar_sites(platform, task_type)

    def log_migration_start(self, migration_data: dict) -> str:
        """Log start of a new migration."""
        return self.memory.save_migration(migration_data)

    def log_migration_result(self, migration_id: str, outcome: str,
                             fidelity_score: Optional[float] = None) -> None:
        """Log the outcome of a migration."""
        if fidelity_score is not None:
            self.memory.update_migration_fidelity(migration_id, fidelity_score)
        self.memory.migrations.update_outcome(migration_id, outcome)

    def update_heuristic_from_result(self, platform: str, task_type: str,
                                     routing_sequence: list,
                                     success: bool,
                                     fidelity_score: Optional[float] = None) -> None:
        """Update routing heuristic based on migration result."""
        self.memory.update_heuristic(platform, task_type, routing_sequence, success, fidelity_score)

    def checkpoint_session(self, session_id: str, state_data: dict,
                           current_phase: str, completed_steps: list) -> None:
        """Save session checkpoint for crash recovery."""
        self.memory.checkpoint_session(session_id, state_data, current_phase, completed_steps)

    def load_session_checkpoint(self, session_id: str) -> Optional[dict]:
        """Load session checkpoint."""
        return self.memory.load_session(session_id)

    def clear_session_checkpoint(self, session_id: str) -> None:
        """Clear session checkpoint after successful completion."""
        self.memory.delete_session(session_id)

    def save_debate_output(self, migration_id: str, debate_result: dict) -> str:
        """Save debate output for later review."""
        return self.memory.save_debate(migration_id, debate_result)

    def get_migration_history(self, platform: Optional[str] = None,
                              task_type: Optional[str] = None,
                              limit: int = 10) -> list[dict]:
        """Get migration history, optionally filtered."""
        return self.memory.list_recent_migrations(platform, task_type, limit)


if __name__ == "__main__":
    mc = MemoryClient()

    print("Testing MemoryClient...")

    print("\n1. Query for routing (empty in Phase 0):")
    result = mc.query_for_routing("wix", "portfolio")
    print(f"   Result: {result}")

    print("\n2. Log migration start:")
    mid = mc.log_migration_start({
        "url": "https://example.wixsite.com",
        "platform": "wix",
        "task_type": "portfolio",
        "routing_used": ["onboarding", "scraper", "codegen", "deploy"],
        "outcome": "pending"
    })
    print(f"   Migration ID: {mid}")

    print("\n3. Update migration result:")
    mc.log_migration_result(mid, "success", 0.82)

    print("\n4. Get migration history:")
    history = mc.get_migration_history()
    print(f"   Count: {len(history)}")

    print("\nMemoryClient working correctly.")