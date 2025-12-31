from pydantic import BaseModel, Field
from typing import Literal


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
