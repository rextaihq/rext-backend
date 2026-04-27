from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class BestToolsOutline(BaseOutline):
    """Outline for content listing the 'best' tools or products in a category."""
    category_name: str = Field(description="The category of tools (e.g., 'CRM Software').")
    total_tools_to_list: int = Field(description="Number of tools to focus on.")
    ranking_criteria: List[str] = Field(description="How the tools were selected and ranked.")
    top_pick_declaration: Optional[bool] = Field(default=True, description="Whether to highlight a 'best overall' tool.")
