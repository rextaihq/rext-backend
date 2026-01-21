from datetime import datetime
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

    # Open Graph Tags
    og_tags = f"""
    <meta property="og:title" content="{title or ''}">
    <meta property="og:description" content="{meta_description or ''}">
    <meta property="og:type" content="{content_type}">
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

        "analyzed_at": datetime.utcnow().isoformat()
    }

    return seokar_state
