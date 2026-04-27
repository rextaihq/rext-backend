from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class BestToolsGeneratedContent(BaseGeneratedContent):
    category_name: Optional[str] = Field(default=None, description="The category of tools.")
    total_tools_to_list: Optional[int] = Field(default=None, description="Number of tools focused on.")
    ranking_criteria: Optional[List[str]] = Field(default_factory=list, description="How the tools were selected and ranked.")
    top_pick_declaration: Optional[bool] = Field(default=True)
