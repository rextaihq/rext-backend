from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ExplainerConcept(BaseModel):
    term: str = Field(description="Term or concept.")
    definition: str = Field(description="Clear and concise definition.")
    examples: Optional[List[str]] = Field(default_factory=list, description="Examples of this concept.")


class ExplainerGeneratedContent(BaseGeneratedContent):
    key_concepts: List[ExplainerConcept] = Field(description="Core concepts explained.")
    visual_diagram_context: Optional[str] = Field(description="What a diagram should show to illustrate the concepts.")
