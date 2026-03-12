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
    probability: float = Field(
        description="The probability/confidence score of the predicted intent (0.0 to 1.0).",
        ge=0.0,
        le=1.0
    )
    explanation: str = Field(
        description="A brief reasoning for your choice."
    )

# Alias for backward compatibility with existing utility functions
class KeywordIntentResponse(SEOIntentOutput):
    """Structured response for keyword search intent prediction."""
    pass

class CompetitorIntentOutput(BaseModel):
    """Structured intent for a single competitor domain."""
    domain: str = Field(description="The domain name of the competitor.")
    intent: Literal["INFORMATIONAL", "COMMERCIAL", "NAVIGATIONAL", "TRANSACTIONAL"] = Field(
        description="The predicted search intent for this specific competitor result."
    )
    is_brand: bool = Field(description="Whether the result represents a brand/navigational query for this domain.")

class BatchSEOIntentOutput(BaseModel):
    """Structured response for batch competitor intent classification."""
    results: List[CompetitorIntentOutput] = Field(description="List of classified intents for each competitor.")
