from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class ProductHomepageOutline(BaseOutline):
    """Outline for a main product homepage or landing overview."""
    product_name: str = Field(description="The name of the product.")
    hero_headline: str = Field(description="The main H1 hook for the product homepage.")
    primary_call_to_action: str = Field(description="The main action (e.g., 'Get Started For Free').")
    key_benefits: List[str] = Field(description="The top 3-4 benefits highlighted on the page.")
    social_proof_elements: Optional[List[str]] = Field(description="Types of social proof to include (e.g., 'Testimonials', 'Logos').")
