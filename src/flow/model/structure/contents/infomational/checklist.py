from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class CheckItem(BaseModel):
    label: str = Field(description="Checklist task or item.")
    context: Optional[str] = Field(default=None, description="Context for this checklist item.")
    difficulty: Optional[Literal["Easy", "Medium", "Hard"]] = Field(default="Easy")


class ChecklistGeneratedContent(BaseGeneratedContent):
    check_items: Optional[List[CheckItem]] = Field(default_factory=list, description="The actionable checklist items.")
    is_printable_ready: Optional[bool] = Field(default=True)
    total_phases: Optional[int] = Field(default=None, description="Total phases or sections for this checklist.")
    estimated_total_time: Optional[str] = Field(default=None, description="Total estimated time for completion.")
