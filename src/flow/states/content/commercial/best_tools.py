from __future__ import annotations

from typing_extensions import Optional

from src.flow.states.content.base import BaseFinalContent


class BestToolsContentState(BaseFinalContent, total=False):
    category_name: str
    total_tools_to_list: int
    ranking_criteria: list[str]
    top_pick_declaration: Optional[bool]
