from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class ComparisonSection(Section):
    """Specifically for comparing items."""
    comparison_criteria: List[str] = Field(description="Aspects being compared (e.g., 'Pricing', 'Performance').")


class ComparisonOutline(BaseOutline):
    """Outline for content comparing two or more products or services."""
    compared_entities: List[str] = Field(description="The items being compared.")
    winner_declaration: Optional[bool] = Field(default=False, description="Whether to declare a winner.")
    comparison_table_included: bool = Field(default=True, description="Whether a comparison table is required.")
    sections: List[ComparisonSection] = Field(description="Detailed comparison sections.")
