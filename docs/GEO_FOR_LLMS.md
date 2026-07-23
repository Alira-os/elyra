# GEO-for-LLMs

## What is GEO?

GEO = **Generative Engine Optimization**. The discipline of making a
website maximally useful to large language models and AI search crawlers
(ChatGPT, Claude, Perplexity, Google AI Overviews, etc.). It complements
classical SEO: SEO helps a page rank in a search results page; GEO helps
a page become a citation in a generated answer.

In Elyra, GEO is the responsibility of the `geo_specialist` persona,
which runs once in the Planning Room (strategy) and once in the Forge
(file production). The artifacts live in `models/site_schemas.py`
(`GeoStrategy`, `GeoBuildArtifacts`).

---

## Why this matters

LLMs and AI search products work very differently from classical search
engines:

- **They don't render JavaScript.** Anything behind a client-only render
  is invisible.
- **They don't crawl link graphs exhaustively.** They follow the
  `llms.txt` declaration if present.
- **They prefer structured data.** A `FAQPage` JSON-LD block becomes a
  citation candidate; free-form prose often doesn't.
- **They need a clear "who is this site" signal.** The `Organization`
  and `Person` schema.org blocks plus the author block in `llms.txt`
  give them that signal.
- **They respect `robots.txt` like any other crawler.** An
  `Allow: /` block per AI user-agent keeps the site reachable for
  training and retrieval.

Elyra's GEO file set makes all five of these things explicit and
machine-verifiable.

---

## File set

`geo_specialist`'s Forge pass produces:

| File | Purpose |
|------|---------|
| `llms.txt` | Markdown index of the site for LLM crawlers (Answer.AI spec). |
| `robots.txt` AI stanza | `User-agent: <bot>` + `Allow: /` blocks for each locked AI crawler. Merged into whatever `frontend_architect` wrote. |
| `sitemap.xml` extras | Additional `<url>` entries beyond `frontend_architect`'s sitemap. |
| JSON-LD blocks (inline) | `<script type="application/ld+json">…</script>` blocks inside the relevant page files. |

---

## `llms.txt` format

The `llms.txt` file follows the [Answer.AI `llms.txt` specification](https://llmstxt.org/):

```markdown
# Site Name

> One-paragraph site summary in natural language. Citable.

## Section 1
- [Page title](https://example.com/page-1): one-sentence description.
- [Page title](https://example.com/page-2): one-sentence description.

## Section 2
- [Page title](https://example.com/page-3): one-sentence description.

## Optional
- [Link to /about](https://example.com/about): about the team.
- [Link to /contact](https://example.com/contact): how to reach us.
```

`geo_specialist` produces the full body in the Forge pass; the Planning
pass emits only the outline (H1 + section list) so the visual direction
and content team can plan around it.

---

## Locked AI-crawler allowlist

The 11 entries below are the canonical allowlist. They must appear
**verbatim** in `GeoBuildArtifacts.ai_crawler_allowlist`, and they must
be emitted as `User-agent: <bot>` + `Allow: /` blocks in the AI stanza
of `robots.txt`.

| User-agent | Operator | Notes |
|------------|----------|-------|
| `GPTBot` | OpenAI | Training crawler. |
| `ClaudeBot` | Anthropic | Training crawler. |
| `Claude-User` | Anthropic | On-demand retrieval (Claude "fetch URL" tool). |
| `Google-Extended` | Google | Opt-in for Gemini training; separate from classical Googlebot. |
| `PerplexityBot` | Perplexity | Perplexity's crawler. |
| `Applebot-Extended` | Apple | Apple Intelligence opt-in. |
| `anthropic-ai` | Anthropic | Anthropic's secondary token. |
| `CCBot` | Common Crawl | Feeds most open training datasets. |
| `cohere-ai` | Cohere | Cohere's crawler. |
| `Amazonbot` | Amazon | Alexa / Rufus. |
| `Bytespider` | ByteDance | TikTok / Doubao. |

This list is mirrored as `MigrationManager.LOCKED_AI_CRAWLERS` in
`conductor/orchestrator.py`. `build_quality_gate` enforces the mirror
via `_run_polish_checks(site_dir)`. If you add or remove entries here,
update the constant in the same commit.

---

## Locked schema.org types

`GeoStrategy.schema_org_types_by_route` and
`GeoBuildArtifacts.json_ld_blocks_by_route` must draw from this locked
set only:

- `Organization` — every site
- `Person` — the primary author / team (often nested inside Organization)
- `WebSite` — root + identity (search box, alternate names)
- `FAQPage` — only on routes that expose Q/A content as
  `<h2>` (or `<h3>`) + `<p>` (or `<section>`) in DOM
- `BreadcrumbList` — any multi-level navigation route

Do not invent new types. Adding a non-locked type breaks the planning
coherence gate's `seo_specialist` → `geo_specialist` contract.

---

## What LLMs can't read (and what to do about it)

| Limitation | Mitigation |
|------------|------------|
| No JavaScript rendering | Static-render all critical content. `frontend_architect` already does this for our Next.js builds. |
| No link-graph traversal | Maintain a complete `llms.txt` with every important route. |
| No image understanding | Always include `alt` text on images and `caption` in JSON-LD where relevant. |
| No real-time data | Surface the data `retrieved_at` timestamp in `GeoStrategy.facts_with_sources`. |
| No authentication | Public-only content in `llms.txt`. Auth-gated content goes in `Optional` section with a clear note. |

---

## Build-time verification

The four polish checks that run after `frontend_architect` completes:

1. `sites/<slug>/llms.txt` exists and is non-empty.
2. Number of `<meta name="description">` tags in rendered HTML ≥
   `len(SeoStrategy.target_routes)`.
3. `GeoBuildArtifacts.ai_crawler_allowlist` covers all 11 entries in
   `MigrationManager.LOCKED_AI_CRAWLERS`.
4. At least one JSON-LD block in
   `GeoBuildArtifacts.json_ld_blocks_by_route` JSON-serializes
   successfully.

Failures route_back via the manager loop:
- llms.txt / allowlist / JSON-LD failures → `geo_specialist`
- meta-description shortfall → `frontend_architect`

---

## References

- `llms.txt` specification: https://llmstxt.org/
- schema.org: https://schema.org/
- Anthropic crawler docs: https://support.anthropic.com/en/articles/8896518
- OpenAI crawler docs: https://platform.openai.com/docs/gptbot
- Google-Extended docs: https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers
- PerplexityBot docs: https://docs.perplexity.ai/guides/bots

---

## Versioning

- **1.0** — Phase E initial release. Two-mode design
  (`geo_specialist` Planning + Forge). 11-crawler allowlist locked.