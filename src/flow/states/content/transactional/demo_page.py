from __future__ import annotations
from typing_extensions import Optional
from src.flow.states.content.base import BaseFinalContent


class DemoPageContentState(BaseFinalContent, total=False):
    product_name: str
    booking_tool_integration: str
    what_to_expect: list[str]
    qualifying_questions: Optional[list[str]]
