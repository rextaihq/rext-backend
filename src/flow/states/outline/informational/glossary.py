from __future__ import annotations
from typing_extensions import TypedDict, Literal, Optional, Annotated
import operator


class GlossaryEntry(TypedDict):
    term: str
    definition: str
    examples: Optional[list[str]]
    related_terms: Optional[list[str]]


class GlossarySection(TypedDict):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    entries: list[GlossaryEntry]


class GlossaryOutline(TypedDict):
    title: str
    slug_suggestion: str
    brief: str
    
    # Context
    focus_keyphrase: str
    keywords_to_include: list[str]
    
    # Structure
    sections: list[GlossarySection]
    
    # Navigation/A-Z Strategy
    alphabetical_navigation: bool
    
    # Images Planning
    image_suggestions: list[str]
    
    # Links Planning
    link_suggestions: list[str]
    
    # Schema
    schema_type: Literal["Article", "DefinedTermSet", "WebPage"]
    
    # Content Strategy
    target_audience: list[str]
    tone: str
    target_word_count: int

    # Workflow fields
    status: Literal["approved", "rejected", "reviewing"]
    rejected_reason: Annotated[Optional[str], operator.add]
