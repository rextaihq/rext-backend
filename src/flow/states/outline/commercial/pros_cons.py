from __future__ import annotations

from typing_extensions import Optional

from src.flow.states.outline.base import BaseOutlineState, SectionState


class ProsConsSectionState(SectionState, total=False):
    pros: list[str]
    cons: list[str]


class ProsConsOutlineState(BaseOutlineState, total=False):
    entity_name: str
    overall_sentiment: Optional[str]
    final_recommendation: Optional[str]
    sections: list[ProsConsSectionState]
