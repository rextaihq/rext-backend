from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class DemoPageOutline(BaseOutline):
    """Outline for a 'Book a Demo' or 'Request Demo' page."""
    product_name: str = Field(description="The enterprise or complex product.")
    booking_tool_integration: str = Field(description="E.g., 'Calendly', 'HubSpot'.")
    what_to_expect: List[str] = Field(description="What happens during the demo call.")
    qualifying_questions: Optional[List[str]] = Field(description="Questions asked in the form.")
