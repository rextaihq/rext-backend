from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class AlternativesGeneratedContent(BaseGeneratedContent):
    primary_entity: str = Field(description="The primary entity.")
    reasons_for_alternatives: List[str] = Field(description="Why someone would look for alternatives.")
    total_alternatives_to_list: int = Field(description="Total number of alternatives covered.")
    best_overall_alternative: Optional[str] = Field(description="The top recommended alternative.")
