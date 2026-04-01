from __future__ import annotations
from typing_extensions import Optional, TypedDict
from src.flow.states.outline.base import BaseOutlineState, SectionState


class ComparisonSectionState(SectionState, total=False):
    comparison_criteria: list[str]


class ComparisonOutlineState(BaseOutlineState, total=False):
    compared_entities: list[str]
    winner_declaration: Optional[bool]
    comparison_table_included: bool
    sections: list[ComparisonSectionState]
