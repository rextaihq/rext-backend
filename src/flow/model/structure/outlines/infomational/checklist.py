from typing import List, Optional, Literal
from pydantic import BaseModel, Field, conlist


class ChecklistItem(BaseModel):
    """An individual actionable item in the checklist."""
    label: str = Field(description="The checklist item text.")
    context: Optional[str] = Field(description="Brief explanation of why this item is necessary.")
    difficulty: Literal["Easy", "Medium", "Hard"] = "Easy"


class ChecklistSection(BaseModel):
    heading: str = Field(description="Section heading (e.g., 'Phase 1', 'Preparation').")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="Overview of this checklist phase.")
    items: conlist(ChecklistItem, min_length=2, max_length=15)


class ChecklistOutline(BaseModel):
    title: str = Field(description="SEO-optimized checklist title starting with the focus keyphrase.")
    slug_suggestion: str = Field(
        pattern=r"^[a-z0-9-]+$",
        description="Suggested URL slug."
    )
    brief: str = Field(description="Main objective and the specific process the checklist covers.")
    
    # Context
    focus_keyphrase: str = Field(
        description="The primary action/process the checklist follows."
    )
    keywords_to_include: conlist(str, min_length=2)
    
    # Structure
    sections: conlist(ChecklistSection, min_length=2, max_length=10)
    
    # Checklist Value Proposition
    total_items: Optional[int] = Field(description="Total number of checklist items in the complete article.")
    estimated_time: Optional[str] = Field(description="Total estimated time to complete all items.")
    
    # Images/Icons Planning
    image_suggestions: List[str] = Field(
        description="Suggested header image or specific icons for phases."
    )
    
    # Links Planning
    link_suggestions: List[str] = Field(
        description="Suggested internal and outbound links."
    )
    
    # Schema
    schema_type: Literal["Article", "HowTo"] = Field(
        default="Article",
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
