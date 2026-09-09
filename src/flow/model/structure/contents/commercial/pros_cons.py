from typing import List, Optional

from pydantic import BaseModel, Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class ProsConsSection(BaseModel):
    pros: List[str] = Field(default_factory=list, description="List of positive aspects.")
    cons: List[str] = Field(default_factory=list, description="List of negative aspects.")
    details: str = Field(description="Explanation of these pros and cons.")


class ProsConsGeneratedContent(BaseGeneratedContent):
    entity_name: Optional[str] = Field(default=None, description="The subject being discussed.")
    overall_sentiment: Optional[str] = Field(default=None, description="Overall sentiment.")
    final_recommendation: Optional[str] = Field(
        default=None, description="Who this is best suited for."
    )
    pros_cons_sections: Optional[List[ProsConsSection]] = Field(
        default_factory=list, description="Detailed pros and cons sections."
    )
