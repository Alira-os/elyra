# Lighthouse Skill

**Version:** 1.0
**Status:** Phase 0 MVP

---

## Purpose

Runs Lighthouse CI to audit a deployed site for performance, accessibility, best practices, and SEO. The output feeds into the `SecurityQualityGate` which blocks deployment if scores don't meet thresholds.

---

## When to Call

- **After deploy:** The `SecurityQualityGate` calls `lighthouse` on the staging URL before presenting to human for approval
- **After codegen (optional):** Can run on local build to catch issues early
- **Quality gate thresholds (Phase 0 MVP):**
  - Performance ≥ 85
  - Accessibility ≥ 90
  - Best Practices ≥ 85
  - SEO ≥ 85

---

## CLI Invocation

```bash
npx @lhci/cli autorun \
  --collect.url=https://staging.fly.dev \
  --collect.numberOfRuns=3 \
  --assert.preset=desktop \
  --assert.assertions.performance=["error",{"minScore": 0.85}] \
  --assert.assertions.accessibility=["error",{"minScore": 0.90}]
```

---

## Interface

```python
def run_lighthouse(url: str, preset: str = "desktop") -> dict:
    """
    Run Lighthouse CI on a URL.

    Args:
        url: The URL to audit
        preset: "desktop" or "mobile" (default: desktop)

    Returns:
        {
            "performance": 0.0 - 1.0,
            "accessibility": 0.0 - 1.0,
            "best_practices": 0.0 - 1.0,
            "seo": 0.0 - 1.0,
            "final_score": 0.0 - 1.0,  # weighted average
            "passed": True | False,
            "issues": ["Accessibility: Image missing alt text", ...],
            "details_url": "https://grid.example.com/..."  # Lighthouse report link
        }
    """
```

---

## Score Weights

| Category | Weight | Min Score (Phase 0) |
|----------|--------|---------------------|
| Performance | 25% | 0.85 |
| Accessibility | 25% | 0.90 |
| Best Practices | 25% | 0.85 |
| SEO | 25% | 0.85 |

**Final Score:** Weighted average of all four categories.

---

## Parsing Lighthouse Output

Lighthouse outputs JSON. Key fields:

```json
{
  "categories": {
    "performance": {"score": 0.92},
    "accessibility": {"score": 0.88},
    "best-practices": {"score": 0.95},
    "seo": {"score": 0.90}
  },
  "audits": {
    "image-alt": {
      "id": "image-alt",
      "title": "Image elements have missing alt attributes",
      "score": 0,
      "description": "...",
      "displayValue": "12 images missing alt"
    }
  }
}
```

---

## Common Issues and Fixes

| Issue | Category | Fix Guidance |
|-------|----------|-------------|
| Image missing alt text | Accessibility | Add descriptive alt attributes |
| Document doesn't have <title> | SEO | Add descriptive <title> to each page |
| Links do not have descriptive text | Accessibility | Use meaningful link text |
| Background/foreground colors lack contrast | Accessibility | Adjust color values for contrast |
| HTML could be optimized | Performance | Minify HTML output |
| Uses deprecated APIs | Best Practices | Replace deprecated API calls |
| Missing meta description | SEO | Add meta description to each page |
| Links to cross-origin destinations are unsafe | Best Practices | Add rel="noopener noreferrer" |

---

## Dependencies

- `npx @lhci/cli` — Lighthouse CI npm package
- Network access to the target URL
- For local builds: `npm run build` must succeed first

---

## What Gets Passed to SecurityQualityGate

```python
{
    "url": "https://mysite.fly.dev",
    "scores": {
        "performance": 0.92,
        "accessibility": 0.88,
        "best_practices": 0.95,
        "seo": 0.90
    },
    "final_score": 0.9125,
    "passed": False,  # accessibility < 0.90
    "issues": [
        "Accessibility: 12 images missing alt text",
        "Accessibility: Links do not have descriptive text"
    ]
}
```

---

## Anti-Patterns

- **Do not** run Lighthouse on localhost without proper network access
- **Do not** cache Lighthouse results — run fresh on each deployment
- **Do not** skip Lighthouse even for "simple" portfolio sites
- **Do not** use mobile preset for desktop audits (or vice versa)