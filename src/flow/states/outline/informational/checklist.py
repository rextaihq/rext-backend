from __future__ import annotations

import operator

from typing_extensions import Annotated, Literal, Optional, TypedDict


class ChecklistItem(TypedDict):
    label: str
    context: Optional[str]
    difficulty: Literal["Easy", "Medium", "Hard"]


class ChecklistSection(TypedDict):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    items: list[ChecklistItem]


class ChecklistOutline(TypedDict):
    title: str
    slug_suggestion: str
    brief: str

    # Context
    focus_keyphrase: str
    keywords_to_include: list[str]

    # Structure
    sections: list[ChecklistSection]

    # Checklist Value Proposition
    total_items: Optional[int]
    estimated_time: Optional[str]

    # Images/Icons Planning
    image_suggestions: list[str]

    # Links Planning
    link_suggestions: list[str]

    # Schema
    schema_type: Literal["Article", "HowTo"]

    # Content Strategy
    target_audience: list[str]
    tone: str
    target_word_count: int

    # Workflow fields
    status: Literal["approved", "rejected", "reviewing"]
    rejected_reason: Annotated[Optional[str], operator.add]
