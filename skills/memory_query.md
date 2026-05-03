# Memory Query Skill

**Version:** 1.0
**Status:** Phase 0 MVP (stubbed)

---

## Purpose

Queries the memory layer for similar past migrations. In Phase 0, this is stubbed to return "no prior lessons found" but provides the interface that will be fully wired in Phase 1 with LanceDB vector similarity search.

---

## When to Call

- **Entry point:** The Conductor calls `memory_query` at the start of every migration to check for similar past sites
- **Routing decision:** Before applying heuristic routing, the Conductor checks memory for learned patterns
- **Post-migration:** The Conductor logs the migration result to memory for future reference

---

## Interface

```python
def query_similar_sites(platform: str, task_type: str) -> list[dict]:
    """
    Query memory for similar past migrations.

    Args:
        platform: wix, squarespace, wordpress, generic
        task_type: e-commerce, blog, portfolio, business, generic

    Returns:
        List of similar migrations, each containing:
        {
            "migration_id": "uuid",
            "url": "https://...",
            "platform": "wix",
            "task_type": "portfolio",
            "routing_sequence": ["onboarding", "scraper", "codegen", "deploy"],
            "fidelity_score": 0.82,
            "outcome": "success",
            "created_at": "2026-05-01T..."
        }

    Phase 0 behavior:
        Returns: [] (empty list — no prior lessons)
        Logs query to stderr for later LanceDB integration
    """
```

---

## Phase 0 Behavior (Stub)

```
$ query_similar_sites("wix", "portfolio")
[]
$ # Stderr: [memory_query] No prior lessons found for platform=wix, task_type=portfolio
```

---

## Phase 1+ Behavior (Full Implementation)

```
$ query_similar_sites("wix", "portfolio")
[
    {
        "migration_id": "uuid-123",
        "url": "https://photographer-portfolio.wixsite.com",
        "platform": "wix",
        "task_type": "portfolio",
        "routing_sequence": ["onboarding", "scraper", "codegen_lead", "ui_polish", "deploy"],
        "stack_chosen": "nextjs+tailwind",
        "fidelity_score": 0.84,
        "outcome": "success",
        "created_at": "2026-04-28T..."
    }
]
```

---

## Query Semantics

- **Platform match:** Exact match required in Phase 0. Phase 1+ uses vector similarity (e.g., "wix portfolio" is similar to "wix business")
- **Task type match:** Exact match in Phase 0. Phase 1+ uses semantic similarity
- **Results limit:** Return top 5 most similar migrations (by recency if same fidelity)

---

## Integration Points

- **Conductor:** Calls `memory_query` at start of `orchestrator.run()`
- **Heuristics updater:** Calls `memory_query` to find patterns after successful migrations
- **Debate Arena:** Calls `memory_query` to find similar failure cases

---

## What Gets Logged

After each migration, the Conductor logs:
```python
{
    "event": "migration_complete",
    "migration_id": "uuid",
    "platform": "wix",
    "task_type": "portfolio",
    "routing_sequence": [...],
    "fidelity_score": 0.82,
    "outcome": "success",
    "lessons": ["wix portfolio: ui_polish after codegen improves fidelity by 8%"]
}
```

This is stored in SQLite `migrations` table for Phase 0, and also embedded for LanceDB in Phase 1+.