from __future__ import annotations

import operator

from typing_extensions import Annotated, Literal, Optional, TypedDict


class Resource(TypedDict):
    title: str
    url: Optional[str]
    description: str
    category: Optional[str]
    pros: Optional[list[str]]


class ResourceSection(TypedDict):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    resources: list[Resource]


class ResourceListOutline(TypedDict):
    title: str
    slug_suggestion: str
    brief: str

    # Selection Criteria Strategy
    focus_keyphrase: str
    keywords_to_include: list[str]
    selection_criteria: str

    # Structure
    sections: list[ResourceSection]

    # Images/Graphics Planning
    image_suggestions: list[str]

    # Links Planning
    link_suggestions: list[str]

    # Schema
    schema_type: Literal["ItemList", "Article", "WebPage"]

    # Content Strategy
    target_audience: list[str]
    tone: str
    target_word_count: int

    # Workflow fields
    status: Literal["approved", "rejected", "reviewing"]
    rejected_reason: Annotated[Optional[str], operator.add]
