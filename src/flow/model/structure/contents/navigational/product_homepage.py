from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ProductHomepageGeneratedContent(BaseGeneratedContent):
    product_name: str = Field(description="The name of the product.")
    hero_headline: str = Field(description="The main H1 hook.")
    primary_call_to_action: str = Field(description="The main action.")
    key_benefits: List[str] = Field(description="The top benefits highlighted.")
    social_proof_elements: Optional[List[str]] = Field(description="Types of social proof included.")
