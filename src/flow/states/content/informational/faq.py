from __future__ import annotations
from typing_extensions import TypedDict, Optional
from src.flow.states.content.base import BaseFinalContent


class FAQItem(TypedDict):
    question: str
    answer: str
    is_pillar: bool = False


class FAQContent(BaseFinalContent):
    faq_items: list[FAQItem]
    authoritative_source_citations: Optional[list[str]]
    related_topics_to_explore: list[str]
