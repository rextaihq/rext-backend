from __future__ import annotations

from typing_extensions import Optional, TypedDict

from src.flow.states.content.base import BaseFinalContent


class ComparisonSectionState(TypedDict, total=False):
    comparison_criteria: list[str]
    details: str


class ComparisonContentState(BaseFinalContent, total=False):
    compared_entities: list[str]
    winner_declaration: Optional[bool]
    comparison_table_included: bool
    comparison_sections: list[ComparisonSectionState]
