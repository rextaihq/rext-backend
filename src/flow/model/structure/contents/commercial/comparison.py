from typing import List, Optional

from pydantic import BaseModel, Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class ComparisonSection(BaseModel):
    comparison_criteria: List[str] = Field(
        default_factory=list, description="Aspects being compared."
    )
    details: str = Field(description="The actual comparison text.")


class ComparisonGeneratedContent(BaseGeneratedContent):
    compared_entities: Optional[List[str]] = Field(
        default_factory=list, description="The items being compared."
    )
    winner_declaration: Optional[bool] = Field(default=False)
    comparison_table_included: Optional[bool] = Field(default=True)
    comparison_sections: Optional[List[ComparisonSection]] = Field(
        default_factory=list, description="Detailed comparison sections."
    )
