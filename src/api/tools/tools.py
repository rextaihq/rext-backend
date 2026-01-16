from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
from openai import OpenAI
import os
from urllib.parse import urlparse, urlunparse

router = APIRouter(
    prefix="/tools",
    tags=["Tools"],
)


# =========================
# Models
# =========================

class CanonicalTagRequest(BaseModel):
    url: HttpUrl
    description: str | None = None


class CanonicalTagResponse(BaseModel):
    canonical_tag: str
    url: str
    normalized_url: str


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
# Routes
# =========================

@router.get("/")
def get_tools():
    return {"message": "SEO Tools API"}


@router.post("/canonical-tag-generator", response_model=CanonicalTagResponse)
async def generate_canonical_tag(request: CanonicalTagRequest):
    """
    AI-powered Canonical Tag Generator.

    Generates an SEO-friendly canonical tag to prevent duplicate content issues.
    """
    try:
        normalized_url = normalize_url(str(request.url))

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

{f"Additional context: {request.description}" if request.description else ""}
"""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You generate SEO ONLY valid HTML canonical tags."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            max_tokens=100,
        )

        canonical_tag = response.choices[0].message.content.strip()

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
