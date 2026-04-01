from __future__ import annotations
from typing_extensions import TypedDict, Optional
from src.flow.states.content.base import BaseFinalContent


class SubtopicCluster(TypedDict):
    topic: str
    link_suggestion: Optional[str]
    context: str


class PillarContent(BaseFinalContent):
    subtopic_clusters: list[SubtopicCluster]
    table_of_contents: Optional[list[str]]
    comprehensive_checklist_included: Optional[bool]
