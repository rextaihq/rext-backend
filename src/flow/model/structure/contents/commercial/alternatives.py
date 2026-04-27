from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class AlternativesGeneratedContent(BaseGeneratedContent):
    primary_entity: Optional[str] = Field(default=None, description="The primary entity.")
    reasons_for_alternatives: Optional[List[str]] = Field(default_factory=list, description="Why someone would look for alternatives.")
    total_alternatives_to_list: Optional[int] = Field(default=None, description="Total number of alternatives covered.")
    best_overall_alternative: Optional[str] = Field(default=None, description="The top recommended alternative.")
