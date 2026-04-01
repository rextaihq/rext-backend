from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class CodeBlock(BaseModel):
    language: str = Field(description="Programming language.")
    code: str = Field(description="The source code or markup.")
    explanation: str = Field(description="Explanation of the code block.")


class TutorialStep(BaseModel):
    heading: str = Field(description="Tutorial step heading.")
    description: str = Field(description="Detailed step instructions.")
    code_blocks: Optional[List[CodeBlock]] = Field(default_factory=list, description="Associated code examples.")


class TutorialGeneratedContent(BaseGeneratedContent):
    tutorial_steps: List[TutorialStep] = Field(description="Practical learning steps.")
    prerequisites: Optional[List[str]] = Field(default_factory=list, description="Prerequisite knowledge or tools.")
    tutorial_difficulty: Literal["Beginner", "Intermediate", "Advanced"] = "Beginner"
    environment_needed: Optional[str] = Field(description="Necessary tools, software, or credentials.")
