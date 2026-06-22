from datetime import datetime, timezone
from seokar import Seokar, SEOResultLevel


import json

def calculate_seokar(
    html_content: str, 
    title: str = None, 
    meta_description: str = None,
    slug: str = None,
    schema_markup: dict = None,
    focus_keyphrase: str = None,
    content_type:str = "article"
) -> dict:
    """
    Analyze HTML content using Seokar and return normalized SEO metrics.
    Wraps content in a complete shadow HTML template for maximum analysis accuracy.
    """
    
    # ---- Prepare injection strings ----
    canonical_link = f'<link rel="canonical" href="https://example.com/{slug}">' if slug else ""
    
    # JSON-LD Schema
    schema_script = ""
    if schema_markup:
        try:
            schema_json = json.dumps(schema_markup, indent=2)
            schema_script = f'<script type="application/ld+json">\n{schema_json}\n</script>'
        except:
            pass

    # Open Graph Tags — include og:image and og:url so Seokar does not flag
    # missing OG tags (those are set by the CMS at publish time, not by content)
    canonical_url = f"https://example.com/{slug}" if slug else "https://example.com"
    og_tags = f"""
    <meta property="og:title" content="{title or ''}">
    <meta property="og:description" content="{meta_description or ''}">
    <meta property="og:type" content="{content_type}">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:image" content="{canonical_url}/og-image.jpg">
    """

    # Twitter Card Tags — included so Seokar does not flag incomplete Twitter
    # cards (also a CMS concern, not a content concern)
    twitter_tags = f"""
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title or ''}">
    <meta name="twitter:description" content="{meta_description or ''}">
    <meta name="twitter:image" content="{canonical_url}/og-image.jpg">
    """

    # ---- Wrap in full shadow HTML template ----
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title or 'Untitled Article'}</title>
    <meta name="description" content="{meta_description or ''}">
    {canonical_link}
    {og_tags}
    {twitter_tags}
    {schema_script}
</head>
<body>
    <article>
        {html_content}
    </article>
</body>
</html>"""

    analyzer = Seokar(
        html_content=full_html,
    )

    report = analyzer.analyze()

    # ---- Issues Mapping ----
    issues = []
    for issue in report.get("issues", []):
        issues.append({
            "type": issue.get("element_type"),
            "level": issue["level"].name,
            "level_value": issue["level"].value,
            "message": issue.get("message"),
            "details": issue.get("details"),
            "recommendation": issue.get("recommendation"),
        })

    # ---- Keyword Density ----
    keywords = report.get("content_quality", {}).get(
        "keyword_density_top_10_with_bigrams", {}
    )

    # ---- Final Normalized State ----
    seokar_state = {
        "seo_health_score": report["seo_health"]["score"],

        "issue_summary": {
            "critical": report["seo_health"]["critical_issues_count"],
            "errors": report["seo_health"]["error_issues_count"],
            "warnings": report["seo_health"]["warning_issues_count"],
        },

        "page": {
            "title": report["basic_seo"].get("title"),
            "meta_description": report["basic_seo"].get("meta_description"),
            "canonical_url": report["basic_seo"].get("canonical_url"),
        },

        "issues": issues,

        "content_quality": {
            "top_keywords": keywords
        },

        "analyzed_at": datetime.now(timezone.utc).isoformat()
    }

    return seokar_state
