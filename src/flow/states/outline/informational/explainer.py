from __future__ import annotations
from typing_extensions import TypedDict, Literal, Optional, Annotated
import operator


class KeyConcept(TypedDict):
    term: str
    definition: str
    examples: Optional[list[str]]


class ExplainerSection(TypedDict):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    key_points: list[str]
    concepts: Optional[list[KeyConcept]]


class ExplainerOutline(TypedDict):
    title: str
    slug_suggestion: str
    brief: str
    
    # Keyphrase Strategy
    focus_keyphrase: str
    keywords_to_include: list[str]
    
    # Structure
    sections: list[ExplainerSection]
    faqs: Optional[list[str]]
    
    # Images/Diagrams Planning
    image_suggestions: list[dict]
    
    # Links Planning
    link_suggestions: list[dict]
    
    # Schema
    schema_type: Literal["Article", "HowTo", "FAQPage"]
    
    # Content Strategy
    target_audience: list[str]
    tone: str
    target_word_count: int

    # Workflow fields
    status: Literal["approved", "rejected", "reviewing"]
    rejected_reason: Annotated[Optional[str], operator.add]
