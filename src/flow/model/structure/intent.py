from pydantic import BaseModel, Field
from typing import Literal, List


class SEOIntentOutput(BaseModel):
    intent: Literal[
        "INFORMATIONAL",
        "COMMERCIAL",
        "NAVIGATIONAL",
        "TRANSACTIONAL"
    ] = Field(
        description="Primary SEO search intent"
    )

    confidence: Literal["low", "medium", "high"] = Field(
        description="Confidence level of the intent classification"
    )
    
    is_brand: bool = Field(
        description="Whether the content is brand-focused or generic"
    )

class SEOIntentResult(SEOIntentOutput):
    domain: str = Field(description="The domain of the competitor")

class BatchSEOIntentOutput(BaseModel):
    results: List[SEOIntentResult] = Field(description="List of SEO intent classifications for competitors")
    final_intent_type: Literal[
        "INFORMATIONAL",
        "COMMERCIAL",
        "NAVIGATIONAL",
        "TRANSACTIONAL"
    ] = Field(description="Final SEO intent type")


class SerpSignalIntentResult(SEOIntentOutput):
    signal_id: str = Field(description="Stable id, e.g. title_3 or paa_1")
    signal_type: Literal["title", "paa", "related_topic"] = Field(
        description="SERP signal source type"
    )
    text: str = Field(description="Title, PAA question, or related search text")


class BatchSerpSignalIntentOutput(BaseModel):
    results: List[SerpSignalIntentResult] = Field(
        description="Intent classification for SERP titles, PAA, and related topics"
    )
