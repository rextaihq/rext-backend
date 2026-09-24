from __future__ import annotations

from typing_extensions import Optional, TypedDict

from src.flow.states.content.base import BaseFinalContent


class ExplainerConcept(TypedDict):
    term: str
    definition: str
    examples: Optional[list[str]]


class ExplainerContent(BaseFinalContent):
    key_concepts: list[ExplainerConcept]
    visual_diagram_context: Optional[str]
