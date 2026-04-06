from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class HowToStep(BaseModel):
    title: str = Field(description="Step title.")
    description: str = Field(description="Actionable instructions for this step.")
    tools: Optional[List[str]] = Field(default_factory=list, description="Specific tools for this step.")


class HowToGuideGeneratedContent(BaseGeneratedContent):
    steps: Optional[List[HowToStep]] = Field(default_factory=list, description="Instructional steps in order.")
    total_time: Optional[str] = Field(default=None, description="Estimated time (e.g., '30 mins').")
    difficulty: Optional[Literal["Beginner", "Intermediate", "Advanced"]] = Field(default="Beginner")
    tools_needed: List[str] = Field(default_factory=list, description="Overall tools required.")
