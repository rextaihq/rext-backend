from fastapi import APIRouter, HTTPException
from langchain_core.messages import SystemMessage, HumanMessage
from urllib.parse import urlparse, urlunparse
from src.api.tools.schemas.tools_schema import (
    CanonicalTagRequest,
    CanonicalTagResponse,
    HreflangRequest,
    HreflangResponse,
)
from src.flow.model.llm_manager import tools_model

router = APIRouter(
    prefix="/tools",
)


@router.get("/")
def get_tools():
    return {"message": "SEO Tools API"}


# =========================
# Helpers
# =========================

def normalize_url(url: str) -> str:
    """
    Normalize URL for canonical usage.
    - Force https
    - Lowercase domain
    - Remove query params & fragments
    - Normalize trailing slash
    """
    parsed = urlparse(url)

    scheme = "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"

    return urlunparse((scheme, netloc, path, "", "", ""))


# =========================
# Canonical Tag Generator
# =========================

@router.post("/canonical-tag-generator", response_model=CanonicalTagResponse)
async def generate_canonical_tag(request: CanonicalTagRequest):
    """
    AI-powered Canonical Tag Generator.

    Generates an SEO-friendly canonical tag to prevent duplicate content issues.
    """
    try:
        normalized_url = normalize_url(str(request.url))

        model = tools_model()

        prompt = f"""
You are an SEO expert.

Generate a valid HTML canonical tag for the given URL.

URL:
{request.url}

Rules:
- Use https
- Remove tracking parameters
- Normalize trailing slashes
- Prefer lowercase URLs
- Follow SEO best practices

Return ONLY the canonical tag.
Example:
<link rel="canonical" href="https://example.com/page" />

"""

        response = model.invoke([
            SystemMessage(content="You generate SEO ONLY valid HTML canonical tags."),
            HumanMessage(content=prompt)
        ])

        canonical_tag = response.content.strip()

        # Safety fallback
        if not canonical_tag.startswith("<link") or 'rel="canonical"' not in canonical_tag:
            canonical_tag = f'<link rel="canonical" href="{normalized_url}" />'

        return CanonicalTagResponse(
            canonical_tag=canonical_tag,
            url=str(request.url),
            normalized_url=normalized_url,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate canonical tag: {str(e)}"
        )


# =========================
# Hreflang Tag Generator
# =========================

@router.post("/hreflang-tag-generator", response_model=HreflangResponse)
async def generate_hreflang_tags(request: HreflangRequest):
    """
    AI-powered Google-compliant Hreflang Tag Generator.

    Generates hreflang tags for HTML <head> or XML Sitemaps.
    """
    try:
        if len(request.language_region_urls) > 50:
            raise HTTPException(
                status_code=400,
                detail="Maximum of 50 URLs allowed for hreflang generation."
            )

        model = tools_model()

        if request.output_format == "sitemap":
            format_rule = "- Output ONLY valid XML <xhtml:link> tags"
            format_instruction = "Return ONLY valid XML <xhtml:link rel=\"alternate\" hreflang=\"...\" href=\"...\" /> tags."
            context_note = "Your output must be ready to paste directly inside a <url> block of an XML sitemap."
        else:
            format_rule = "- Output ONLY valid HTML <link> tags"
            format_instruction = "Return ONLY valid HTML <link rel=\"alternate\" hreflang=\"...\" href=\"...\" /> tags."
            context_note = "Your output must be ready to paste directly inside the <head> section of an HTML document."

        # Identical URL check for SEO warnings
        warnings = []
        urls_seen = {}
        for entry in request.language_region_urls:
            url_str = str(entry.url)
            if url_str in urls_seen:
                warnings.append(f"Identical URL used for both '{urls_seen[url_str]}' and '{entry.language or 'unknown'}'. Google recommends unique URLs for different language versions.")
            urls_seen[url_str] = entry.language or "unknown"

        system_prompt = f"""
You are a senior SEO engineer and international search optimization expert.

Your sole task is to generate Google Search–compliant hreflang tags for multilingual and multi-regional websites.

STRICT RULES (DO NOT VIOLATE):
- Follow Google's official hreflang implementation guidelines
- Use ISO 639-1 language codes (lowercase)
- Use ISO 3166-1 Alpha-2 region codes (uppercase) when provided
- Format hreflang values strictly as: language-REGION (e.g., en-US, es-ES)
- Normalize incorrect input formats (e.g., EN_us → en-US)
- If language or region are not provided for a URL, infer them from the URL path, subdomain, or TLD if possible.
- Do NOT invent, guess, or modify URLs
- Remove duplicate hreflang entries
- Each hreflang value must be unique
- Self-referencing URLs MUST be included in the output for all versions.
- Generate x-default for the default URL provided.
{format_rule}
- One tag per line
- No explanations
- No comments
- No markdown
- No code blocks
- No additional text before or after output

{context_note}
"""

        # Prepare input for LLM
        lang_region_urls_str = "\n".join([
            f"- url: {entry.url}, language: {entry.language or 'unknown'}, region: {entry.region or 'unknown'}"
            for entry in request.language_region_urls
        ])

        user_prompt = f"""
Generate hreflang tags using the following input.

Default URL (for x-default):
{request.default_url}

Language and Region URLs:
{lang_region_urls_str}

Include x-default:
{str(request.include_x_default).lower()}

{format_instruction}
"""

        response = model.invoke([
            SystemMessage(content=system_prompt.strip()),
            HumanMessage(content=user_prompt.strip())
        ])

        hreflang_tags = response.content.strip()

        # Final cleanup: Remove markdown code blocks if any
        if hreflang_tags.startswith("```"):
            lines = hreflang_tags.split("\n")
            if lines[0].startswith("```") and lines[-1].startswith("```"):
                hreflang_tags = "\n".join(lines[1:-1]).strip()
            else:
                hreflang_tags = hreflang_tags.replace("```html", "").replace("```xml", "").replace("```", "").strip()

        return HreflangResponse(
            hreflang_tags=hreflang_tags,
            warnings=warnings if warnings else None
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate hreflang tags: {str(e)}"
        )
