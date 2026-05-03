# Routing Heuristics Skill

**Version:** 1.0
**Status:** Phase 0 MVP

---

## Purpose

Returns the default routing sequence (ordered list of personas to invoke) for a given platform and task type. This is the heuristic baseline that the Conductor uses unless memory query or LLM override suggests modifications.

---

## When to Call

- **After platform detection:** The Conductor calls `routing_heuristics` to get the default routing sequence
- **On failure:** After handling a persona failure, the Conductor may call `routing_heuristics` to get fallback sequence
- **LLM override:** If LLM suggests routing modifications, the Conductor compares against heuristics

---

## Default Routing Rules

| Platform | Task Type | Routing Sequence |
|----------|-----------|------------------|
| wix | e-commerce | onboarding_specialist → scraper_specialist → stack_intelligence → codegen_crew_lead → security_auditor → deploy_specialist |
| wix | portfolio | onboarding_specialist → scraper_specialist → stack_intelligence → codegen_crew_lead → ui_polish → security_auditor → deploy_specialist |
| wix | blog | onboarding_specialist → scraper_specialist → stack_intelligence → codegen_crew_lead → seo_optimizer → security_auditor → deploy_specialist |
| wix | business | onboarding_specialist → scraper_specialist → stack_intelligence → codegen_crew_lead → security_auditor → deploy_specialist |
| squarespace | e-commerce | (same as wix) |
| squarespace | portfolio | (same as wix) |
| squarespace | blog | (same as wix) |
| squarespace | business | (same as wix) |
| wordpress | blog | onboarding_specialist → scraper_specialist → stack_intelligence → codegen_crew_lead → security_auditor → deploy_specialist |
| wordpress | business | (same as wix) |
| generic | generic | onboarding_specialist → scraper_specialist → stack_intelligence → codegen_crew_lead → security_auditor → deploy_specialist |

---

## Confidence Thresholds

| Condition | Threshold | Behavior |
|-----------|-----------|----------|
| Platform + task_type exact match | confidence = 1.0 | Use routing as-is |
| Platform match, generic task_type | confidence = 0.8 | Use generic routing for task_type |
| Generic platform, exact task_type | confidence = 0.6 | LLM override recommended |
| Generic platform + generic task_type | confidence = 0.5 | LLM override strongly recommended |

---

## Interface

```python
def get_routing_sequence(platform: str, task_type: str, confidence_threshold: float = 0.7) -> dict:
    """
    Get default routing sequence for platform + task_type.

    Args:
        platform: wix, squarespace, wordpress, generic
        task_type: e-commerce, blog, portfolio, business, generic
        confidence_threshold: Minimum confidence to accept routing without LLM override

    Returns:
        {
            "routing_sequence": ["onboarding_specialist", "scraper_specialist", ...],
            "confidence": 0.8,
            "requires_override": False,
            "fallback_available": True
        }
    """
```

---

## Stack Intelligence Integration

The `stack_intelligence` persona (in Phase 0, handled by Conductor heuristics) chooses the stack based on:

| Site Type | Default Stack | Alternatives |
|-----------|--------------|--------------|
| E-commerce | Next.js + Tailwind + Shopify Buy SDK | Nuxt + Vuetify + Shopify |
| Portfolio | Next.js + Tailwind + Contentlayer | Astro + Tailwind |
| Blog | Next.js + Tailwind + MDX | Astro + Contentlayer |
| Business | Next.js + Tailwind | Nuxt + Tailwind |

Stack choice is stored in `TaskContext.stack_chosen` and passed to `codegen_crew_lead`.

---

## LLM Override Triggers

The Conductor should invoke LLM override when:

1. `confidence < confidence_threshold` (default 0.7)
2. Platform is "generic" or "unknown"
3. Memory query returns a different routing that worked better
4. Site is "large" (> 50 pages detected)

---

## Updating Heuristics

Heuristics are updated from Debate Arena outputs in Phase 1+. The update function:

```python
def update_heuristic(platform: str, task_type: str, new_sequence: list[str]) -> None:
    """
    Update routing heuristic based on learned pattern.
    Only used in Phase 1+ when Debate Arena is active.
    """
```

---

## Anti-Patterns

- **Do not** route directly to `codegen_crew_lead` without `scraper_specialist` (for migrations)
- **Do not** skip `security_auditor` even for "simple" sites
- **Do not** include `ui_polish` for e-commerce (fidelity gain doesn't justify complexity)