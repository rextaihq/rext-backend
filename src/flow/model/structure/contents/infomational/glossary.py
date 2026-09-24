from typing import List, Optional

from pydantic import BaseModel, Field

from src.flow.model.structure.contents.base import BaseGeneratedContent


class GlossaryDefinition(BaseModel):
    term: str = Field(description="Term or phrase.")
    definition: str = Field(description="The formal definition.")
    related_terms: Optional[List[str]] = Field(
        default_factory=list, description="Equivalent or related terms."
    )


class GlossaryGeneratedContent(BaseGeneratedContent):
    glossary_definitions: Optional[List[GlossaryDefinition]] = Field(
        default_factory=list, description="Definition mapping used in the content."
    )
    alphabetical_sort: Optional[bool] = Field(default=True)
    industry_domain: Optional[str] = Field(
        default=None,
        description="The sector or knowledge field (e.g., 'Physics', 'Digital Marketing').",
    )
