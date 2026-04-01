from typing import List, Optional
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section


class ProsConsSection(Section):
    """Specifically for pros and cons lists."""
    pros: List[str] = Field(description="List of positive aspects.")
    cons: List[str] = Field(description="List of negative aspects.")


class ProsConsOutline(BaseOutline):
    """Outline for content highlighting the pros and cons of an entity."""
    entity_name: str = Field(description="The subject being discussed.")
    overall_sentiment: Optional[str] = Field(description="Is it generally positive or negative?")
    final_recommendation: Optional[str] = Field(description="Who this is best suited for.")
    sections: List[ProsConsSection] = Field(description="Detailed pros and cons sections.")
