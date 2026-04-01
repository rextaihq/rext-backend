from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class DocumentationGeneratedContent(BaseGeneratedContent):
    topic_or_module: str = Field(description="The topic or module.")
    intended_audience_technical_level: str = Field(description="Technical level of reader.")
    prerequisites_needed: Optional[List[str]] = Field(description="What the user must know.")
    includes_code_snippets: bool = Field(default=False)
