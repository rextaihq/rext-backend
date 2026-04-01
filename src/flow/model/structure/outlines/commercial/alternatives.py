from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class AlternativesOutline(BaseOutline):
    """Outline for content suggesting alternatives to a specific entity."""
    primary_entity: str = Field(description="The primary entity (e.g., 'Mailchimp').")
    reasons_for_alternatives: List[str] = Field(description="Why someone would look for alternatives.")
    total_alternatives_to_list: int = Field(description="Total number of alternatives to cover.")
    best_overall_alternative: Optional[str] = Field(description="The top recommended alternative.")
