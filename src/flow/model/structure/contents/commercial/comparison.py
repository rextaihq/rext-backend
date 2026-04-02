from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class ComparisonSection(BaseModel):
    comparison_criteria: List[str] = Field(description="Aspects being compared.")
    details: str = Field(description="The actual comparison text.")


class ComparisonGeneratedContent(BaseGeneratedContent):
    compared_entities: List[str] = Field(description="The items being compared.")
    winner_declaration: Optional[bool] = Field(default=False)
    comparison_table_included: bool = Field(default=True)
    comparison_sections: List[ComparisonSection] = Field(description="Detailed comparison sections.")
