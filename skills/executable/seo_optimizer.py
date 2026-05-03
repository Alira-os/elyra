def get_seo_guidance(scraped_site: dict) -> dict:
    """
    Generate SEO guidance based on scraped site analysis.

    Args:
        scraped_site: The ScrapedSite object from scraper_specialist

    Returns:
        {
            "title_template": str,
            "meta_description_template": str,
            "heading_hierarchy_issues": list,
            "image_alt_text_coverage": float,
            "schema_markup_found": list,
            "schema_markup_missing": list,
            "recommendations": list,
            "llm_prompt_addition": str
        }
    """
    site_name = scraped_site.get("global", {}).get("site_name", "Site")

    title_template = f"{{page_title}} | {site_name}"
    meta_description_template = f"{{page_description}} - {site_name}"

    heading_issues = []
    schema_found = []
    schema_missing = []
    recommendations = []
    total_images = 0
    images_with_alt = 0

    for page_path, page_data in scraped_site.get("pages", {}).items():
        headings = page_data.get("headings", {})

        if "h1" not in headings or not headings["h1"]:
            heading_issues.append(f"{page_path}: Missing <h1>")
        elif len(headings.get("h1", [])) > 1:
            heading_issues.append(f"{page_path}: Multiple <h1> elements")

        if "h2" not in headings and "h1" in headings:
            heading_issues.append(f"{page_path}: No <h2> under <h1>")

        page_images = page_data.get("images", [])
        total_images += len(page_images)
        for img in page_images:
            if img.get("alt") and img["alt"].strip():
                images_with_alt += 1
            else:
                recommendations.append(f"Add alt text to image on {page_path}")

        page_schema = page_data.get("seo", {}).get("schema", {})
        if page_schema:
            schema_found.extend(page_schema.keys() if isinstance(page_schema, dict) else [])

    schema_found = list(set(schema_found))

    if total_images > 0:
        alt_coverage = images_with_alt / total_images
    else:
        alt_coverage = 1.0

    if alt_coverage < 0.8:
        recommendations.append(f"Image alt text coverage is {alt_coverage:.0%} — add alt to {total_images - images_with_alt} images")

    if "Organization" not in schema_found:
        schema_missing.append("Organization")
        recommendations.append("Add Organization schema to homepage")

    if "BreadcrumbList" not in schema_found:
        schema_missing.append("BreadcrumbList")
        recommendations.append("Add BreadcrumbList schema to interior pages")

    llm_prompt_addition = f"""
## SEO Optimization Requirements

When generating code, ensure:

1. **Meta Tags**
   - Every page must have unique <title> and <meta name="description">
   - Format: {title_template}
   - Include Open Graph tags for social sharing
   - Include Twitter Card tags

2. **Heading Structure**
   - One <h1> per page
   - Logical heading hierarchy (h1 > h2 > h3)
   - Descriptive headings with keywords

3. **Image Alt Text**
   - All <img> tags must have descriptive alt attributes ({alt_coverage:.0%} coverage in source)
   - For decorative images: alt=""
   - For images with text: include the text in alt

4. **Schema Markup**
   - Add JSON-LD schema for Organization on homepage
   - Add BreadcrumbList schema on interior pages
   - Add Article schema on blog posts
   - Required types not in source: {', '.join(schema_missing) if schema_missing else 'None'}

5. **Semantic HTML**
   - Use semantic elements: <header>, <nav>, <main>, <article>, <footer>
   - No div soup — use semantic structure

6. **Accessibility**
   - All form inputs have labels
   - Color contrast meets WCAG AA
   - Focus states visible on interactive elements

Apply these to ALL pages generated. This is not optional.
"""

    return {
        "title_template": title_template,
        "meta_description_template": meta_description_template,
        "heading_hierarchy_issues": heading_issues,
        "image_alt_text_coverage": round(alt_coverage, 2),
        "schema_markup_found": schema_found,
        "schema_markup_missing": schema_missing,
        "recommendations": recommendations,
        "llm_prompt_addition": llm_prompt_addition.strip()
    }


def get_seo_prompt_for_codegen(scraped_site: dict) -> str:
    """
    Convenience function to get just the LLM prompt addition.

    Args:
        scraped_site: ScrapedSite object from scraper_specialist

    Returns:
        The LLM prompt addition string (seo_optimizer guidance)
    """
    guidance = get_seo_guidance(scraped_site)
    return guidance["llm_prompt_addition"]


if __name__ == "__main__":
    mock_scraped_site = {
        "global": {"site_name": "Example Portfolio"},
        "pages": {
            "/": {
                "title": "Home",
                "headings": {"h1": "Welcome", "h2": ["Services", "Work"]},
                "images": [
                    {"src": "hero.jpg", "alt": "Hero image"},
                    {"src": "work1.jpg", "alt": ""},
                    {"src": "work2.jpg", "alt": "Design project"},
                ],
                "seo": {"schema": {"Organization": {}}}
            },
            "/about": {
                "title": "About",
                "headings": {"h1": "About Me"},
                "images": [],
                "seo": {}
            }
        }
    }

    guidance = get_seo_guidance(mock_scraped_site)
    print("Title template:", guidance["title_template"])
    print("Alt coverage:", guidance["image_alt_text_coverage"])
    print("Schema found:", guidance["schema_markup_found"])
    print("Schema missing:", guidance["schema_markup_missing"])
    print("Issues:", guidance["heading_hierarchy_issues"])
    print("Recommendations:", guidance["recommendations"][:3])