from pydantic import BaseModel, Field
from typing import List, Literal


class SeedKeywordsOutput(BaseModel):
    primary_keyword: str = Field(
        description="The single 2-4 word phrase that is the standard, commonly-searched term for this business's core category. Not the brand name."
    )
    secondary_keywords: List[str] = Field(
        description="Exactly 9 other real, standard commercial search phrases covering a wide spread of phrasing styles."
    )
    business_summary: str = Field(
        description="One sentence describing what the company sells and to whom."
    )
    audience: str = Field(
        description="One short phrase describing the target customer/buyer persona."
    )


class CompetitorClassification(BaseModel):
    topic_overlap: int = Field(ge=0, le=100, description="How much subject matter/content focus overlaps")
    audience_overlap: int = Field(ge=0, le=100, description="How much target customer/buyer persona overlaps")
    product_similarity: int = Field(ge=0, le=100, description="How similar the actual product/service offering is")
    type: Literal[
        "business_competitor", "content_competitor", "supplier_or_manufacturer"
    ] = Field(description="Competitor relationship type")
