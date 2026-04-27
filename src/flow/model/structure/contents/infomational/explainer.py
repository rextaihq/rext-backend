from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ExplainerConcept(BaseModel):
    term: str = Field(description="Term or concept.")
    definition: str = Field(description="Clear and concise definition.")
    examples: Optional[List[str]] = Field(default_factory=list, description="Examples of this concept.")


class ExplainerGeneratedContent(BaseGeneratedContent):
    key_concepts: Optional[List[ExplainerConcept]] = Field(default_factory=list, description="Core concepts explained.")
    visual_diagram_context: Optional[str] = Field(default=None, description="What a diagram should show to illustrate the concepts.")
