from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class DemoPageGeneratedContent(BaseGeneratedContent):
    product_name: str = Field(description="The enterprise product.")
    booking_tool_integration: str = Field(description="Tool integrated for booking.")
    what_to_expect: List[str] = Field(description="Expectations during demo.")
    qualifying_questions: Optional[List[str]] = Field(description="Questions asked.")
