from __future__ import annotations

import operator

from typing_extensions import Annotated, Literal, Optional, TypedDict


class CodeSnippet(TypedDict):
    language: str
    description: str
    difficulty: Literal["Easy", "Medium", "Hard"]


class TutorialStep(TypedDict):
    title: str
    description: str
    code_suggestions: Optional[list[CodeSnippet]]


class TutorialSection(TypedDict):
    heading: str
    heading_level: Literal["H2", "H3"]
    description: str
    steps: list[TutorialStep]


class TutorialOutline(TypedDict):
    title: str
    slug_suggestion: str
    brief: str

    # Prerequisite Strategy
    focus_keyphrase: str
    keywords_to_include: list[str]
    difficulty: Literal["Beginner", "Intermediate", "Advanced"]
    environment_setup: Optional[str]

    # Structure
    sections: list[TutorialSection]

    # Images/Diagrams Planning
    image_suggestions: list[str]

    # Links Planning
    link_suggestions: list[str]

    # Schema
    schema_type: Literal["HowTo", "TechArticle", "Article"]

    # Content Strategy
    target_audience: list[str]
    tone: str
    target_word_count: int

    # Workflow fields
    status: Literal["approved", "rejected", "reviewing"]
    rejected_reason: Annotated[Optional[str], operator.add]
