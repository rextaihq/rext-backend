from typing import List, Optional, Literal

from pydantic import Field, conlist

from src.flow.model.structure.content_types import ContentType
from src.flow.model.structure.outlines.strict import StrictModel


class FAQItem(StrictModel):
    """An individual question and answer pair."""
    question: str = Field(description="The question to answer.")
    answer_brief: str = Field(description="Brief, clear answer optimized for search snippets.")
    detailed_answer: Optional[str] = Field(description="Detailed explanation if needed.")


class FAQSection(StrictModel):
    heading: str = Field(description="FAQ category (e.g., 'Pricing', 'Security').")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="Overview of the questions in this category.")
    items: conlist(FAQItem, min_length=2, max_length=10)


class FAQOutline(StrictModel):
    content_type: ContentType = Field(
        description="Canonical content type slug. Must match the requested content_type."
    )
    title: str = Field(description="SEO-optimized FAQ title (e.g., '[Focus Keyphrase] FAQ').")
    slug_suggestion: str = Field(
        pattern=r"^[a-z0-9-]+$",
        description="Suggested URL slug."
    )
    brief: str = Field(description="The primary objective and the audience for this FAQ.")
    
    # Context
    focus_keyphrase: str = Field(
        description="The primary term, brand, or service the FAQ covers."
    )
    keywords_to_include: conlist(str, min_length=1)
    
    # Structure
    sections: conlist(FAQSection, min_length=1, max_length=10)
    
    # Support Strategy
    contact_instruction: Optional[str] = Field(description="How to reach out if someone has a question not in this FAQ.")
    
    # Images Planning
    image_suggestions: List[str] = Field(
        description="Suggested icons or illustrations (min 1)."
    )
    
    # Links Planning
    link_suggestions: List[str] = Field(
        description="Suggested internal links (e.g., 'Contact Us', 'Documentation')."
    )
    
    # Schema
    schema_type: Literal["FAQPage", "Article"] = Field(
        default="FAQPage",
        description="Primary schema.org type."
    )
    
    # Content Strategy
    target_audience: List[str]
    tone: Literal[
    "Professional", "Conversational", "Authoritative", "Friendly", 
    "Encouraging", "Neutral", "Persuasive", "Analytical", 
    "Direct", "Action-oriented", "Trustworthy", "Urgent"
    ]
    target_word_count: int = Field(ge=500, le=3000)
