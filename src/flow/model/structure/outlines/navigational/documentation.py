from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class DocumentationOutline(BaseOutline):
    """Outline for technical documentation or user manuals."""
    topic_or_module: str = Field(description="The specific topic or module being documented.")
    intended_audience_technical_level: str = Field(description="e.g., 'Beginner', 'Advanced Developer'.")
    prerequisites_needed: Optional[List[str]] = Field(description="What the user must know or have before proceeding.")
    includes_code_snippets: bool = Field(default=False, description="Whether code blocks are required in the documentation.")
