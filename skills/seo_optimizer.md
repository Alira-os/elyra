# SEO Optimizer Skill

**Version:** 1.0
**Status:** Phase 0 MVP

---

## Purpose

Provides guidance for optimizing migrated content for SEO and AI visibility. This skill is **guidance-only** — it does not execute changes directly. Instead, it outputs an LLM prompt that the Conductor passes to the codegen phase.

---

## When to Call

- **After scraping, before codegen:** The Conductor passes `seo_optimizer` guidance to `codegen_crew_lead`
- **Post-deploy review:** If Lighthouse SEO score < 0.85, provide fix guidance

---

## What This Skill Covers

### 1. Meta Tags
- [ ] Title tag: `{page_title} | {site_name}` format
- [ ] Meta description: 150-160 characters, includes primary keyword
- [ ] Open Graph tags: `og:title`, `og:description`, `og:image`, `og:url`
- [ ] Twitter Card tags: `twitter:card`, `twitter:title`, `twitter:description`
- [ ] Canonical URL on every page

### 2. Heading Hierarchy
- [ ] Exactly one `<h1>` per page
- [ ] Logical heading hierarchy: `<h2>` under `<h1>`, `<h3>` under `<h2>`
- [ ] Headings are descriptive and contain keywords where natural
- [ ] No heading skips (e.g., `<h1>` → `<h3>` without `<h2>`)

### 3. Image Optimization
- [ ] All images have descriptive `alt` text
- [ ] Images use modern formats (WebP, AVIF) when possible
- [ ] Images have explicit `width` and `height` attributes
- [ ] Lazy loading for below-fold images: `loading="lazy"`

### 4. Semantic HTML
- [ ] Use `<header>`, `<nav>`, `<main>`, `<article>`, `<section>`, `<aside>`, `<footer>`
- [ ] Use `<button>` for actions, `<a>` for links
- [ ] Form elements have associated `<label>` tags
- [ ] Tables are used for tabular data, not layout

### 5. Schema Markup (JSON-LD)
- [ ] Organization schema on homepage
- [ ] BreadcrumbList on interior pages
- [ ] Article/BlogPosting schema on blog posts
- [ ] LocalBusiness schema if applicable
- [ ] Product schema if e-commerce

### 6. Content Quality
- [ ] No duplicate content across pages
- [ ] Internal linking structure is logical
- [ ] External links open in new tab (`target="_blank" rel="noopener"`)
- [ ] Mobile-friendly (responsive design)

---

## LLM Prompt Guidance

The `seo_optimizer` skill outputs this prompt fragment that the Conductor includes in the codegen prompt:

```
## SEO Optimization Requirements

When generating code, ensure:

1. **Meta Tags**
   - Every page must have unique <title> and <meta name="description">
   - Include Open Graph tags for social sharing
   - Include Twitter Card tags

2. **Heading Structure**
   - One <h1> per page
   - Logical heading hierarchy (h1 > h2 > h3)
   - Descriptive headings with keywords

3. **Image Alt Text**
   - All <img> tags must have descriptive alt attributes
   - For decorative images: alt=""
   - For images with text: include the text in alt

4. **Schema Markup**
   - Add JSON-LD schema for Organization on homepage
   - Add BreadcrumbList schema on interior pages
   - Add Article schema on blog posts

5. **Semantic HTML**
   - Use semantic elements: <header>, <nav>, <main>, <article>, <footer>
   - No div soup — use semantic structure

6. **Accessibility**
   - All form inputs have labels
   - Color contrast meets WCAG AA
   - Focus states visible on interactive elements

Apply these to ALL pages generated. This is not optional.
```

---

## Interface

```python
def get_seo_guidance(scraped_site: dict) -> dict:
    """
    Generate SEO guidance based on scraped site analysis.

    Args:
        scraped_site: The ScrapedSite object from scraper_specialist

    Returns:
        {
            "title_template": str,
            "meta_description_template": str,
            "heading_hierarchy_issues": list of issues found,
            "image_alt_text_coverage": 0.0 - 1.0,
            "schema_markup_found": list of schema types found,
            "schema_markup_missing": list of schema types missing,
            "recommendations": list of specific recommendations,
            "llm_prompt_addition": str  # The prompt fragment above
        }
    """
```

---

## Phase 0 Limitations

- No automated checking in Phase 0 — guidance is passed to LLM for codegen
- Phase 1+ will add automated checks after codegen
- Schema markup generation may need manual review for complex sites

---

## Dependencies

- `skills.executable.seo_optimizer` — This is guidance only, no CLI tool
- Output feeds into `codegen_crew_lead` prompt

---

## Anti-Patterns

- **Do not** add keyword stuffing — SEO is about quality, not quantity
- **Do not** add schema markup that doesn't match the content (e.g., Article on a product page)
- **Do not** skip alt text on images "for now" — this impacts accessibility AND SEO
- **Do not** use the same meta description on every page