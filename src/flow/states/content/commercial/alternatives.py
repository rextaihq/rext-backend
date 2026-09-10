from __future__ import annotations

from typing_extensions import Optional

from src.flow.states.content.base import BaseFinalContent


class AlternativesContentState(BaseFinalContent, total=False):
    primary_entity: str
    reasons_for_alternatives: list[str]
    total_alternatives_to_list: int
    best_overall_alternative: Optional[str]
