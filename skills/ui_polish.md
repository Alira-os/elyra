# UI Polish Skill

**Version:** 1.0
**Status:** Phase 3 — UI Polish Skill

---

## Purpose

The `ui_polish` skill is a reusable visual quality pass that runs after code generation. It inspects the generated component and page files, directly modifies them for visual excellence, and logs every change with a specific reason tracing back to the `BrandSpec`.

This skill owns the "make it feel impeccable" mandate. It is not a linter or a static analyzer — it is an active code modifier.

---

## When to Call

Call `ui_polish` after the initial code generation pass (Builder persona or any codegen output) and before the final BuildManifest is produced.

**The skill directly modifies files. All changes are logged for auditability.**

---

## What It Checks & Fixes

### 1. Spacing Consistency

- All `gap`, `margin`, `padding` values must use the `spacing_scale` from BrandSpec
- Check for hardcoded values like `gap-4` that should be `gap-6` per the spacing scale
- Enforce 8px grid across all layouts
- Check both horizontal and vertical rhythm within components

### 2. Typography Hierarchy

- `h1` through `h6` must use `font_family_heading` and follow `type_scale`
- Body text must use `font_family_body`
- Line heights must be appropriate for the type scale
- Font size relationships must show clear visual hierarchy (h1 should be noticeably larger than h2)

### 3. Color Contrast

- All text must meet WCAG AA contrast ratios against their backgrounds
- Use `semantic_tokens` from BrandSpec for all color decisions
- Check: primary button text vs primary button background
- Check: body text vs page background
- Flag any hardcoded hex values that should be CSS variables

### 4. Motion Philosophy

Translate the `motion_philosophy` into concrete CSS:

| Philosophy | Duration | Easing | Transforms | Scale on Hover |
|-------------|----------|--------|------------|----------------|
| `monastic` | 200–300ms | `ease-out` | opacity, translateY only | none |
| `classical` | 400ms | `ease-out` | subtle scale | `scale(1.02)` |
| `energetic` | 150ms | `ease-in-out` | scale, shadow | `scale(1.05)` |
| `subtle` | 150–200ms | `ease` | opacity only | minimal |

- Check that `transition` properties match the philosophy
- Ensure no `duration: 500ms` when philosophy is `energetic`
- Verify reduced motion media query is present (`@media (prefers-reduced-motion: reduce)`)

### 5. Component Variants

- Apply all `component_variants` from BrandSpec (e.g., `button: [primary, secondary, ghost]`)
- Each variant must have distinct, intentional styling — not just color swaps
- Ghost buttons should have transparent backgrounds with border

### 6. Dark Mode

- If `dark_mode_strategy` is `full_tokens`, verify both light and dark token sets exist in CSS
- If `auto_invert`, verify `[data-theme="dark"]` overrides are correct
- Test contrast in both modes

### 7. Button & Interactive States

- Every button must have: default, hover, focus, active, and disabled states
- Focus states must be visible (never `outline: none` without alternatives)
- Hover states should match the `motion_philosophy`
- Cursor must be `pointer` on clickable elements

### 8. Form Field States

- Inputs must have: default, focus, error, disabled states
- Focus ring must be visible
- Error states must show color + text feedback
- Labels must always be visible (not just placeholder text)

### 9. Responsive Layout

- Test at mobile (375px), tablet (768px), desktop (1280px)
- Navbar/header collapses correctly on mobile
- Cards and grids reflow properly
- Text does not overflow or cause horizontal scroll

### 10. Semantic HTML + Accessibility

- Use `<main>`, `<nav>`, `<header>`, `<footer>`, `<article>` appropriately
- All images must have `alt` attributes
- Interactive elements must have `aria-label` or descriptive text
- Form fields must have associated `<label>` elements
- No `div` used as button — use `<button>` for native behavior

---

## Output

The skill returns a list of `PolishChange` objects:

```python
class PolishChange(BaseModel):
    file: str                    # e.g., "components/Hero.tsx"
    change: str                  # e.g., "gap-4 → gap-8"
    reason: str                   # e.g., "Increased breathing room to match monastic motion philosophy"
    brand_spec_reference: str      # e.g., "spacing_scale.xl" or "motion_philosophy"
```

Every change must include:
- Specific file modified
- Exact change made (before → after)
- Why this improves the output (reference BrandSpec or accessibility requirement)
- Which BrandSpec field or token this relates to

---

## Logging Requirements

All changes are logged in the `BuildManifest.ui_polish_changes` list. This is the audit trail that enables the Project Manager to correlate polish decisions with outcome quality.

---

## Anti-Patterns

- **Do not** skip the reduced motion media query
- **Do not** leave buttons without visible focus states
- **Do not** output generic shadcn/ui component styling without BrandSpec customization
- **Do not** use hardcoded hex values instead of CSS custom properties from BrandSpec
- **Do not** apply `scale` transforms when `motion_philosophy` is `monastic`
- **Do not** leave form fields without labels or with only placeholder text