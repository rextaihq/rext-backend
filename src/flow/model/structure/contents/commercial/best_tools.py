from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class BestToolsGeneratedContent(BaseGeneratedContent):
    category_name: str = Field(description="The category of tools.")
    total_tools_to_list: int = Field(description="Number of tools focused on.")
    ranking_criteria: List[str] = Field(description="How the tools were selected and ranked.")
    top_pick_declaration: Optional[bool] = Field(default=True)
