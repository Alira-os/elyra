# npm Audit Skill

**Version:** 1.0
**Status:** Phase 0 MVP

---

## Purpose

Runs `npm audit` on a project to check for known vulnerabilities in dependencies. The output feeds into the `SecurityQualityGate` — if any **critical** vulnerabilities are found, deployment is blocked.

---

## When to Call

- **After codegen, before deploy:** The `SecurityQualityGate` runs `npm_audit` on the generated project
- **CI pipeline:** Part of the standard CI workflow in GitHub Actions
- **Quality gate thresholds (Phase 0 MVP):**
  - **Critical vulnerabilities:** 0 (hard block)
  - **High vulnerabilities:** Warning only (does not block)
  - **Medium/Low:** Warning only (does not block)

---

## CLI Invocation

```bash
cd /path/to/project
npm audit --audit-level=high
```

---

## Interface

```python
def run_npm_audit(project_dir: str) -> dict:
    """
    Run npm audit on a project directory.

    Args:
        project_dir: Path to the project root (must have package.json)

    Returns:
        {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "passed": True | False,
            "summary": "0 critical, 2 high vulnerabilities found",
            "details": [
                {"severity": "critical", "name": "package-name", "url": "https://..."},
                ...
            ]
        }
    """
```

---

## Severity Handling

| Severity | Action | Blocks Deploy? |
|----------|--------|----------------|
| Critical | Hard block | **Yes** |
| High | Warning | No |
| Medium | Warning | No |
| Low | Info | No |
| None | Pass | No |

---

## What Gets Passed to SecurityQualityGate

```python
{
    "project_dir": "/path/to/elyra-migration-xxx",
    "critical": 0,
    "high": 2,
    "medium": 5,
    "low": 12,
    "passed": False,  # because there are high vulnerabilities
    "summary": "0 critical, 2 high, 5 medium, 12 low vulnerabilities found",
    "blocking": False,  # Only critical blocks
    "details": [
        {"severity": "high", "name": "lodash", "url": "https://npmjs.com/advisories/..."},
        {"severity": "high", "name": "axios", "url": "https://npmjs.com/advisories/..."}
    ]
}
```

If `passed == False` due to critical vulnerabilities, `SecurityQualityGate.check()` will block deployment and return detailed fix instructions.

---

## Fix Instructions

When vulnerabilities are found, provide these steps:

```bash
# Update all dependencies
npm update

# Or update specific package
npm update <package-name>

# For critical vulnerabilities, may need major version bump
npm install <package-name>@latest

# After updating, re-run audit
npm audit
```

---

## Anti-Patterns

- **Do not** ignore critical vulnerabilities even if "they probably won't affect us"
- **Do not** skip npm audit for "simple" static sites (even static sites have dependencies)
- **Do not** add `--production` flag to skip devDependencies (some vulnerabilities are in dev tools)
- **Do not** use `npm audit --fix` automatically — always review changes first