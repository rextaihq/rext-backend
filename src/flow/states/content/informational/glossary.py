from __future__ import annotations

from typing_extensions import Optional, TypedDict

from src.flow.states.content.base import BaseFinalContent


class GlossaryDefinition(TypedDict):
    term: str
    definition: str
    related_terms: Optional[list[str]]


class GlossaryContent(BaseFinalContent):
    glossary_definitions: list[GlossaryDefinition]
    alphabetical_sort: bool = True
    industry_domain: Optional[str]
