from __future__ import annotations

import operator

from typing_extensions import Annotated, Literal, Optional, TypedDict


class ResultMetric(TypedDict):
    metric_name: str
    result_value: str
    context: Optional[str]


class CaseStudySection(TypedDict):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    key_highlights: list[str]
    results: Optional[list[ResultMetric]]


class CaseStudyOutline(TypedDict):
    title: str
    slug_suggestion: str
    brief: str

    # Context
    focus_keyphrase: str
    keywords_to_include: list[str]
    client: str

    # Structure
    sections: list[CaseStudySection]

    # Visual Storytelling
    image_suggestions: list[str]

    # Links Planning
    link_suggestions: list[str]

    # Schema
    schema_type: Literal["Article", "NewsArticle"]

    # Content Strategy
    target_audience: list[str]
    tone: str
    target_word_count: int

    # Workflow fields
    status: Literal["approved", "rejected", "reviewing"]
    rejected_reason: Annotated[Optional[str], operator.add]
