from __future__ import annotations
from typing_extensions import TypedDict, Literal, Optional, Annotated
import operator


class Fact(TypedDict, total=False):
    text: str
    source_url: Optional[str]


class ImageSuggestion(TypedDict):
    description: str
    alt_text_template: str
    section: str


class LinkSuggestion(TypedDict):
    anchor_text: str
    link_type: Literal["internal", "outbound"]
    context: str
    section: str


class Section(TypedDict):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    key_points: list[str]
    questions_to_answer: Optional[list[str]]
    snippet_target: Optional[bool]
    search_intent: Literal["informational", "commercial"]
    suggested_word_count: Optional[int]
    include_keyphrase_in_heading: bool
    facts: Optional[list[Fact]]


class BlogOutline(TypedDict):
    title: str
    slug_suggestion: str
    brief: str
    
    # Keyphrase Strategy
    focus_keyphrase: str
    keywords_to_include: list[str]
    
    # Structure
    sections: list[Section]
    faqs: Optional[list[str]]
    key_facts: Optional[list[Fact]]
    
    # Images Planning
    image_suggestions: list[ImageSuggestion]
    
    # Links Planning
    link_suggestions: list[LinkSuggestion]
    
    # Schema
    schema_type: Literal["Article", "HowTo", "FAQPage", "BlogPosting"]
    
    # Content Strategy
    target_audience: list[str]
    tone: str
    target_word_count: int

    # Workflow fields
    status: Literal["approved", "rejected", "reviewing"]
    rejected_reason: Annotated[Optional[str], operator.add]
