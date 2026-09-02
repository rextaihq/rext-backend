from typing import List, Optional

from pydantic import Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class DemoPageGeneratedContent(BaseGeneratedContent):
    product_name: Optional[str] = Field(default=None, description="The enterprise product.")
    booking_tool_integration: Optional[str] = Field(
        default=None, description="Tool integrated for booking."
    )
    what_to_expect: Optional[List[str]] = Field(
        default_factory=list, description="Expectations during demo."
    )
    qualifying_questions: Optional[List[str]] = Field(default=None, description="Questions asked.")
