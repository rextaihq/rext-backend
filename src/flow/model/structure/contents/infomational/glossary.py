from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class GlossaryDefinition(BaseModel):
    term: str = Field(description="Term or phrase.")
    definition: str = Field(description="The formal definition.")
    related_terms: Optional[List[str]] = Field(default_factory=list, description="Equivalent or related terms.")


class GlossaryGeneratedContent(BaseGeneratedContent):
    glossary_definitions: List[GlossaryDefinition] = Field(description="Definition mapping used in the content.")
    alphabetical_sort: bool = True
    industry_domain: Optional[str] = Field(description="The sector or knowledge field (e.g., 'Physics', 'Digital Marketing').")
