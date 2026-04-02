from __future__ import annotations
from typing_extensions import TypedDict, Literal, Optional, Annotated
import operator


class FAQItem(TypedDict):
    question: str
    answer_brief: str
    detailed_answer: Optional[str]


class FAQSection(TypedDict):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    items: list[FAQItem]


class FAQOutline(TypedDict):
    title: str
    slug_suggestion: str
    brief: str
    
    # Context
    focus_keyphrase: str
    keywords_to_include: list[str]
    
    # Structure
    sections: list[FAQSection]
    
    # Support Strategy
    contact_instruction: Optional[str]
    
    # Images Planning
    image_suggestions: list[str]
    
    # Links Planning
    link_suggestions: list[str]
    
    # Schema
    schema_type: Literal["FAQPage", "Article"]
    
    # Content Strategy
    target_audience: list[str]
    tone: str
    target_word_count: int

    # Workflow fields
    status: Literal["approved", "rejected", "reviewing"]
    rejected_reason: Annotated[Optional[str], operator.add]
