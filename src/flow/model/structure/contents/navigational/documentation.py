from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class DocumentationGeneratedContent(BaseGeneratedContent):
    topic_or_module: Optional[str] = Field(default=None, description="The topic or module.")
    intended_audience_technical_level: Optional[str] = Field(default=None, description="Technical level of reader.")
    prerequisites_needed: Optional[List[str]] = Field(default=None, description="What the user must know.")
    includes_code_snippets: Optional[bool] = Field(default=False)
