from __future__ import annotations
from typing_extensions import Optional, TypedDict
from src.flow.states.content.base import BaseFinalContent


class ProsConsSectionState(TypedDict, total=False):
    pros: list[str]
    cons: list[str]
    details: str


class ProsConsContentState(BaseFinalContent, total=False):
    entity_name: str
    overall_sentiment: Optional[str]
    final_recommendation: Optional[str]
    pros_cons_sections: list[ProsConsSectionState]
