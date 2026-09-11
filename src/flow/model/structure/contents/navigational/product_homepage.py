from typing import List, Optional

from pydantic import Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class ProductHomepageGeneratedContent(BaseGeneratedContent):
    product_name: Optional[str] = Field(default=None, description="The name of the product.")
    hero_headline: Optional[str] = Field(default=None, description="The main H1 hook.")
    primary_call_to_action: Optional[str] = Field(default=None, description="The main action.")
    key_benefits: Optional[List[str]] = Field(
        default_factory=list, description="The top benefits highlighted."
    )
    social_proof_elements: Optional[List[str]] = Field(
        default=None, description="Types of social proof included."
    )
