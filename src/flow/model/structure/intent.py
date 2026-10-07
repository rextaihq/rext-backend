from typing import List, Literal

from pydantic import BaseModel, Field


class SEOIntentOutput(BaseModel):
    intent: Literal["INFORMATIONAL", "COMMERCIAL", "NAVIGATIONAL", "TRANSACTIONAL"] = Field(
        description="Primary SEO search intent"
    )

    is_brand: bool = Field(description="Whether the content is brand-focused or generic")


class SEOIntentResult(SEOIntentOutput):
    domain: str = Field(description="The domain of the competitor")


class BatchSEOIntentOutput(BaseModel):
    results: List[SEOIntentResult] = Field(
        description="List of SEO intent classifications for competitors"
    )
    final_intent_type: Literal["INFORMATIONAL", "COMMERCIAL", "NAVIGATIONAL", "TRANSACTIONAL"] = (
        Field(description="Final SEO intent type")
    )
    suggested_keywords: List[str] = Field(
        default_factory=list,
        description="5-10 related keyword variations and long-tail keywords derived from the query and competitor context",
    )
