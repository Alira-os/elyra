"""
Conductor - Elyra Orchestration Package

Orchestrates the migration workflow via the MigrationManager (Room-based
state machine + Manager-driven routing). The legacy `Conductor` class
was removed in Phase A.
"""

from conductor.orchestrator import MigrationManager, ManagerDecision

__all__ = ["MigrationManager", "ManagerDecision"]
