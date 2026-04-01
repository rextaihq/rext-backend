from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class CheckItem(BaseModel):
    label: str = Field(description="Checklist task or item.")
    context: Optional[str] = Field(description="Context for this checklist item.")
    difficulty: Literal["Easy", "Medium", "Hard"] = "Easy"


class ChecklistGeneratedContent(BaseGeneratedContent):
    check_items: List[CheckItem] = Field(description="The actionable checklist items.")
    is_printable_ready: bool = True
    total_phases: Optional[int] = Field(description="Total phases or sections for this checklist.")
    estimated_total_time: Optional[str] = Field(description="Total estimated time for completion.")
