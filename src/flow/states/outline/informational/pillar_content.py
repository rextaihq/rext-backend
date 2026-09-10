from __future__ import annotations

import operator

from typing_extensions import Annotated, Literal, Optional, TypedDict


class PillarSection(TypedDict):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    key_points: list[str]
    subtopic_cluster: Optional[list[str]]
    facts: Optional[list[dict]]


class PillarContentOutline(TypedDict):
    title: str
    slug_suggestion: str
    brief: str

    # Topic Authority Strategy
    focus_keyphrase: str
    keywords_to_include: list[str]
    related_clusters: list[str]

    # Structure
    sections: list[PillarSection]
    faqs: Optional[list[str]]

    # Images Planning
    image_suggestions: list[dict]

    # Links Planning
    link_suggestions: list[dict]

    # Schema
    schema_type: Literal["Article", "WebPage", "FAQPage"]

    # Content Strategy
    target_audience: list[str]
    tone: str
    target_word_count: int

    # Workflow fields
    status: Literal["approved", "rejected", "reviewing"]
    rejected_reason: Annotated[Optional[str], operator.add]
