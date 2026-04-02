from __future__ import annotations
from typing_extensions import TypedDict, Literal, Optional, Annotated
import operator


class Step(TypedDict):
    title: str
    description: str
    tools_needed: Optional[list[str]]


class HowToSection(TypedDict):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    key_points: list[str]
    steps: Optional[list[Step]]


class HowToGuideOutline(TypedDict):
    title: str
    slug_suggestion: str
    brief: str
    
    # Keyphrase Strategy
    focus_keyphrase: str
    keywords_to_include: list[str]
    
    # Prerequisite Info
    total_time: Optional[str]
    difficulty: Literal["Beginner", "Intermediate", "Advanced"]
    tools_needed: list[str]
    
    # Structure
    sections: list[HowToSection]
    faqs: Optional[list[str]]
    
    # Images Planning
    image_suggestions: list[dict] # Simplified for common parts if preferred, sticking to models' structure
    
    # Links Planning
    link_suggestions: list[dict]
    
    # Schema
    schema_type: Literal["HowTo", "Article"]
    
    # Content Strategy
    target_audience: list[str]
    tone: str
    target_word_count: int

    # Workflow fields
    status: Literal["approved", "rejected", "reviewing"]
    rejected_reason: Annotated[Optional[str], operator.add]
