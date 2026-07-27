from pydantic import BaseModel, Field


class ContentTypeRecommendation(BaseModel):
    """LLM's pick of the single best-fit content type for a query, from a fixed candidate list."""

    recommended_content_type: str = Field(
        description="The single best-fit content type, copied EXACTLY (same spelling/casing) from the provided candidate list."
    )
    reason: str = Field(
        description=(
            "One short sentence (max ~20 words) explaining why this format fits best. "
            "Write for a reader with ZERO SEO or content-marketing background: no jargon "
            "(don't say 'SERP', 'intent', 'conversion', 'funnel', etc.). If a concept is "
            "unavoidable, explain it in plain words within the same sentence."
        )
    )
