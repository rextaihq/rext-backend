"""
On-Page SEO Scoring Node
"""

import logging
from typing import Dict

import markdown
from bs4 import BeautifulSoup

from src.flow.engines.content.utils.utils import calculate_seokar
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def markdown_to_clean_html(md_text: str) -> str:
    html = markdown.markdown(md_text or "", extensions=["extra", "toc"])
    soup = BeautifulSoup(html, "html.parser")

    def add_class(tag, class_name):
        existing = tag.get("class", [])
        if class_name not in existing:
            tag["class"] = existing + [class_name]

    # Headings
    for h1 in soup.find_all("h1"):
        add_class(h1, "main-heading")

    for h2 in soup.find_all("h2"):
        add_class(h2, "section-heading")

    for h3 in soup.find_all("h3"):
        add_class(h3, "sub-heading")

    # Paragraphs
    for p in soup.find_all("p"):
        add_class(p, "paragraph")

    # Images
    for img in soup.find_all("img"):
        if not img.get("alt"):
            img["alt"] = "relevant image"
        img["loading"] = "lazy"

    return str(soup)


def wrap_full_html(
    html_body: str,
    meta_title: str,
    meta_description: str,
    slug: str,
    focus_keyphrase: str,
    schema_data: str = None,
) -> str:
    import json as _json

    safe_title = meta_title or ""
    safe_desc = meta_description or ""
    safe_slug = slug or ""
    safe_keyword = focus_keyphrase or ""
    canonical = f"https://example.com/{safe_slug}" if safe_slug else "https://example.com"

    # JSON-LD — only inject if schema_data is a valid JSON string
    json_ld_block = ""
    if schema_data:
        try:
            parsed = _json.loads(schema_data)
            json_ld_block = (
                f'\n    <script type="application/ld+json">\n'
                f"    {_json.dumps(parsed, indent=2)}\n"
                f"    </script>"
            )
        except (ValueError, TypeError):
            pass  # Invalid JSON — skip silently

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>{safe_title}</title>
    <meta name="description" content="{safe_desc}">
    <meta name="robots" content="index, follow">

    <!-- SEO Enhancements -->
    <link rel="canonical" href="{canonical}">
    <meta name="keywords" content="{safe_keyword}">{json_ld_block}

    <!-- Open Graph -->
    <meta property="og:title" content="{safe_title}">
    <meta property="og:description" content="{safe_desc}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="{canonical}">

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{safe_title}">
    <meta name="twitter:description" content="{safe_desc}">

</head>
<body>
<article>
{html_body}
</article>
</body>
</html>
"""


def calculate_on_page_seo(state: REXT) -> Dict:
    """Calculate on-page SEO metrics using Seokar.

    Analyzes HTML content against target keywords to compute an on-page
    SEO score. Checks title, meta description, slug, headers, image alt text,
    and keyword density.

    Args:
        state: REXT state containing ``content.final_content`` and
            ``content.content_type``.

    Returns:
        Dict: State update with ``content.review.on_page_metrics`` populated
        with Seokar analysis results.
    """
    logger.info("Starting on-page SEO scoring")

    content_state = state.get("content", {})
    content_type = content_state.get("content_type")
    final_content = content_state.get("final_content")

    if not final_content:
        logger.warning("Final content not found, skipping SEO analysis")
        return {}

    # ---- Extract only what you actually need ----
    title = final_content.get("title")
    meta_title = final_content.get("meta_title")
    meta_description = final_content.get("meta_description")
    slug = final_content.get("slug")
    focus_keyphrase = final_content.get("focus_keyphrase")
    introduction = final_content.get("introduction") or ""
    body_markdown = final_content.get("body_markdown") or ""

    # ---- Combine full article — prepend H1 so Seokar sees it ----
    h1 = title or meta_title or ""
    full_markdown = (
        f"# {h1}\n\n{introduction}\n\n{body_markdown}"
        if h1
        else f"{introduction}\n\n{body_markdown}"
    )

    # ---- Convert to HTML ----
    html_body = markdown_to_clean_html(full_markdown)

    # ---- Normalize schema ----
    schema = final_content.get("schema_markup")
    schema_data = None
    if isinstance(schema, dict):
        schema_data = schema.get("schema_data")
    elif hasattr(schema, "schema_data"):
        schema_data = schema.schema_data

    full_html = wrap_full_html(
        html_body=html_body,
        meta_title=meta_title or title,
        meta_description=meta_description,
        slug=slug,
        focus_keyphrase=focus_keyphrase,
        schema_data=schema_data,
    )

    # ---- Run SEO Analyzer ----
    try:
        seokar_state = calculate_seokar(
            html_content=full_html,
            title=meta_title or title,
            meta_description=meta_description,
            slug=slug,
            schema_markup=schema_data,
            focus_keyphrase=focus_keyphrase,
            content_type=content_type,
        )
    except Exception as e:
        logger.exception(f"Seokar SEO analysis failed for slug: {slug}")
        return {"content": {"review": {"on_page_metrics": None}}, "error": str(e)}

    return {"content": {"review": {"on_page_metrics": seokar_state}}}
