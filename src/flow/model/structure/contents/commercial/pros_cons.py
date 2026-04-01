from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ProsConsSection(BaseModel):
    pros: List[str] = Field(description="List of positive aspects.")
    cons: List[str] = Field(description="List of negative aspects.")
    details: str = Field(description="Explanation of these pros and cons.")


class ProsConsGeneratedContent(BaseGeneratedContent):
    entity_name: str = Field(description="The subject being discussed.")
    overall_sentiment: Optional[str] = Field(description="Overall sentiment.")
    final_recommendation: Optional[str] = Field(description="Who this is best suited for.")
    pros_cons_sections: List[ProsConsSection] = Field(description="Detailed pros and cons sections.")
