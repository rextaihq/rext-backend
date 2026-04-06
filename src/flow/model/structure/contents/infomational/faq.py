from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.contents.base import BaseGeneratedContent


class FAQItem(BaseModel):
    question: str = Field(description="The question to answer.")
    answer: str = Field(description="Clear and concise answer optimized for search snippets.")
    is_pillar: Optional[bool] = Field(default=False)


class FAQGeneratedContent(BaseGeneratedContent):
    faq_items: Optional[List[FAQItem]] = Field(default_factory=list, description="List of question and answer pairs.")
    authoritative_source_citations: Optional[List[str]] = Field(default_factory=list, description="Authoritative sources for this FAQ.")
    related_topics_to_explore: List[str] = Field(default_factory=list, description="Related topics to link from the FAQ.")
