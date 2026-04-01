from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class HowToStep(BaseModel):
    title: str = Field(description="Step title.")
    description: str = Field(description="Actionable instructions for this step.")
    tools: Optional[List[str]] = Field(default_factory=list, description="Specific tools for this step.")


class HowToGuideGeneratedContent(BaseGeneratedContent):
    steps: List[HowToStep] = Field(description="Instructional steps in order.")
    total_time: Optional[str] = Field(description="Estimated time (e.g., '30 mins').")
    difficulty: Literal["Beginner", "Intermediate", "Advanced"] = "Beginner"
    tools_needed: List[str] = Field(default_factory=list, description="Overall tools required.")
