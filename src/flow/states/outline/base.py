from __future__ import annotations
from typing_extensions import TypedDict, Literal, Optional

class ImageSuggestionState(TypedDict):
    description: str
    alt_text_template: str
    section: str

class LinkSuggestionState(TypedDict):
    anchor_text: str
    link_type: Literal["internal", "outbound"]
    context: str
    section: str

class FactState(TypedDict):
    text: str

class SectionState(TypedDict, total=False):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    key_points: list[str]
    questions_to_answer: Optional[list[str]]
    snippet_target: Optional[bool]
    search_intent: Literal["informational", "commercial", "navigational", "transactional"]
    suggested_word_count: Optional[int]
    include_keyphrase_in_heading: bool
    facts: Optional[list[FactState]]

class BaseOutlineState(TypedDict, total=False):
    title: str
    slug_suggestion: str
    brief: str
    focus_keyphrase: str
    keywords_to_include: list[str]
    sections: list[SectionState]
    faqs: Optional[list[str]]
    key_facts: Optional[list[FactState]]
    image_suggestions: list[ImageSuggestionState]
    link_suggestions: list[LinkSuggestionState]
    schema_type: Literal["Article", "HowTo", "FAQPage", "BlogPosting", "Product", "Review"]
    target_audience: list[str]
    tone: Literal[
        "Professional",
        "Conversational",
        "Authoritative",
        "Friendly",
        "Encouraging",
        "Neutral",
        "Persuasive",
        "Analytical",
        "Direct",
        "Action-oriented",
        "Trustworthy",
        "Urgent"
    ]
    target_word_count: int
